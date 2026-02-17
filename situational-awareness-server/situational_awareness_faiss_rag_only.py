""" Module for forwarding the processed data to the vector database

This module is responsible for vectorizing the extracted and tokenized data, and forwarding it to the vector database.

How this module works:
...
"""

import numpy as np
import lda
from sklearn.feature_extraction.text import CountVectorizer
from datetime import datetime
import json
import faiss
from sentence_transformers import SentenceTransformer
import requests
import logging
import time
import threading
import pyRAPL
import psutil
import base64

logging.basicConfig(level=logging.INFO)

TAG = "situational_awareness_faiss:  "

# VECTOR_DB_URL = "http://127.0.0.1:8000/store"
VECTOR_DB_URL = "http://vector-db:8000/store"

file_path = './Pre_processed_text.txt'

# Initialize the embedding model
embedding_function = SentenceTransformer('all-mpnet-base-v2')

#----------------------------------------------------------------------------------------------------------------------------

def encode_embedding(vec: np.ndarray) -> str:
    """
    Encode a NumPy float32 vector into Base64 string.
    """
    return base64.b64encode(vec.tobytes()).decode("utf-8")


def send_new_data_to_database(documents, database):
    global temp_index, temp_topics, perm_index, perm_topics

    chunks = get_chunks(documents)

    # Decide which topic memory to use
    if database == "temp":
        topic_names = temp_topics
        topic_index = temp_index
    else:
        topic_names = perm_topics
        topic_index = perm_index

    # Assign topics
    results, topic_names, topic_index = create_topics(chunks, topic_names, topic_index)

    # Save updated SA topic memory
    if database == "temp":
        temp_topics = topic_names
        temp_index = topic_index
    else:
        perm_topics = topic_names
        perm_index = topic_index

    # Build new flat payload
    payload = {
        "database": database,
        "chunks": results
    }

    # Send to Vector DB
    try:
        response = requests.post(VECTOR_DB_URL, json=payload)
        response.raise_for_status()
        print(f"{TAG} Data successfully sent to the vector database. Status: {response.status_code}")

    except requests.RequestException as e:
        logging.error(f"{TAG} Failed to send data: {e}")


def create_topics(chunks, topic_names, topic_index):
    """
    Assign topics to chunks based on existing topic embeddings.
    If a chunk does not fit any existing topic (distance > threshold),
    a new topic is created using LDA.
    """

    threshold = 1.4
    results = []

    # Embed chunks
    chunk_embeddings = embedding_function.encode(chunks, convert_to_numpy=True).astype("float32")

    # Case: no topics yet → all chunks are outliers → create new topics by LDA
    if not topic_names or topic_index is None:
        return create_new_topics_for_all(chunks, chunk_embeddings)

    # Prepare lists for outliers (chunks that don't match any topic)
    outliers_text = []
    outliers_emb = []

    # Assign chunks to old topics or mark them as outliers
    for chunk, emb in zip(chunks, chunk_embeddings):

        distances, indices = topic_index.search(emb.reshape(1, -1), k=1)
        best_distance = distances[0][0]
        best_topic_idx = indices[0][0]

        if best_distance < threshold:
            # Existing topic
            topic_name = topic_names[best_topic_idx]

            results.append({
                "topic": topic_name,
                "text": chunk,
                "embedding_b64": encode_embedding(emb)
            })
        else:
            outliers_text.append(chunk)
            outliers_emb.append(emb)

    # If no outliers → return results
    if not outliers_text:
        return results, topic_names, topic_index

    # Create topics for outliers
    new_entries, updated_topic_names, updated_topic_index = handle_outliers(outliers_text, outliers_emb, topic_names, topic_index)

    # Add new topic-chunks to result list
    results.extend(new_entries)

    return results, updated_topic_names, updated_topic_index


def create_new_topics_for_all(chunks, chunk_embeddings):
    topic_count = max(1, len(chunks) // 10)

    vectorizer, lda_model, lda_topic_names = vectorize(chunks, topic_count)
    doc_topic = lda_model.doc_topic_

    topic_names = []
    topic_vectors = []

    results = []

    for i, (chunk, emb) in enumerate(zip(chunks, chunk_embeddings)):
        top_topic_idx = doc_topic[i].argmax()
        topic_name = lda_topic_names[top_topic_idx]

        # Add new topic to memory if not present
        if topic_name not in topic_names:
            topic_names.append(topic_name)
            topic_vector = embedding_function.encode([topic_name]).astype("float32")[0]
            topic_vectors.append(topic_vector)

        results.append({
            "topic": topic_name,
            "text": chunk,
            "embedding_b64": encode_embedding(emb)
        })

    # Build FAISS index
    dim = len(topic_vectors[0])
    topic_index = faiss.IndexFlatL2(dim)
    topic_index.add(np.vstack(topic_vectors).astype("float32"))

    return results, topic_names, topic_index


def handle_outliers(outliers_text, outliers_emb, topic_names, topic_index):
    topic_count = max(1, len(outliers_text) // 10)

    vectorizer, lda_model, lda_topic_names = vectorize(outliers_text, topic_count)
    doc_topic = lda_model.doc_topic_

    new_entries = []

    for i, (chunk, emb) in enumerate(zip(outliers_text, outliers_emb)):
        top_topic_idx = doc_topic[i].argmax()
        topic_name = lda_topic_names[top_topic_idx]

        # New topic created
        if topic_name not in topic_names:
            topic_names.append(topic_name)
            topic_vector = embedding_function.encode([topic_name]).astype("float32")[0]
            topic_index.add(topic_vector.reshape(1, -1))

        new_entries.append({
            "topic": topic_name,
            "text": chunk,
            "embedding_b64": encode_embedding(emb)
        })

    return new_entries, topic_names, topic_index


def get_chunks(documents):
    chunks = []
    for doc in documents:
        # Define a function to chunk text before assigning topics
        doc_chunks = create_chunks(doc.strip())
        chunks.extend(doc_chunks)  # Add all chunks from this document to the overall chunk list
    return chunks


def create_chunks(text, chunk_size=500, chunk_overlap=20):
    """Chunk the input text into smaller segments."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - chunk_overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def vectorize(chunks, topic_count):
    """
    Vectorize chunks, fit LDA topic model, and extract topic names.
    """

    vectorizer = CountVectorizer(stop_words='english')

    X = vectorizer.fit_transform(chunks)  # Use chunks for topic modeling

    # Fit the LDA model using the chunks
    model = lda.LDA(n_topics=topic_count, n_iter=300, random_state=1)
    model.fit(X)

    vocab = vectorizer.get_feature_names_out()

    n_top_words = 8
    topic_names = []
    topic_word = model.topic_word_

    for i, topic_dist in enumerate(topic_word):
        # Get the top words for the topic
        topic_words = np.array(vocab)[np.argsort(topic_dist)][:-(n_top_words+1):-1]
        topic_name = " ".join(topic_words)
        topic_names.append(topic_name)

    return vectorizer, model, topic_names

# def init_model():
#     """
#     Initialize the topic model by reading existing data,
#     chunking it, and fitting a vectorizer and LDA model.
#     """
#     with open(file_path, 'r') as file:
#         documents = file.readlines()
#     chunks = get_chunks(documents)
#     return vectorize(chunks, 50)

# initial_vectorizer, initial_model, initial_topic_names = init_model()

#-------------------------------------------

# Initialize FAISS index from existing topics:
# fetch topics for vector DB, encode them, and build the index


temp_topics = None
perm_topics = None

temp_embeddings = None
perm_embeddings = None

temp_index = None
perm_index = None

# url = "http://127.0.0.1:8000/get_topics"
url = "http://vector-db:8000/get_topics"


def fetch_topics(database_name):
    try:
        response = requests.post(url, json={"database": database_name}, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        topic_names = data.get("topics", [])

        print(f"{database_name} topics fetched from vector-db: {topic_names}")

        if not topic_names:
            return [], None, None

        # Create embeddings for topics
        topic_embeddings = embedding_function.encode(topic_names).astype("float32")

        # Build FAISS index
        dim = topic_embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(topic_embeddings)

        print(f"{database_name} embeddings shape: {topic_embeddings.shape}")

        return topic_names, topic_embeddings, index

    except Exception as e:
        logging.error(f"Error fetching topics: {e}")
        return [], None, None
    

while True:
    try:
        perm_topics, perm_embeddings, perm_index = fetch_topics("permanent")

        if perm_topics is not None:
            print("Successfully fetched topics from permanent database.")
            break
        else:
            logging.warning("No topics found in database. Retrying in 3s...")
            time.sleep(3)

    except Exception as e:
        logging.warning(f"Vector DB not ready ({e}), retrying in 3s...")
        time.sleep(3)

while True:
    try:
        temp_topics, temp_embeddings, temp_index = fetch_topics("temp")

        if temp_topics is not None:
            print("Successfully fetched topics from temp database.")
            break
        else:
            logging.warning("No topics found in database. Retrying in 3s...")
            time.sleep(3)

    except Exception as e:
        logging.warning(f"Vector DB not ready ({e}), retrying in 3s...")
        time.sleep(3)