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

logging.basicConfig(level=logging.INFO)

TAG = "situational_awareness_faiss:  "

# VECTOR_DB_URL = "http://vector_db_server:8000/store"
VECTOR_DB_URL = "http://127.0.0.1:8000/store"

file_path = './Pre_processed_text.txt'

# Initialize the embedding model
embedding_function = SentenceTransformer('all-mpnet-base-v2')

#----------------------------------------------------------------------------------------------------------------------------


def send_new_data_to_database(documents, database):
    global perm_index, perm_topics, temp_index, temp_topics

    if database == "temp":
        db_index = temp_index
        db_topics = temp_topics
    else:
        db_index = perm_index
        db_topics = perm_topics

    # Split the new data into chunks
    chunks = get_chunks(documents)

    existing_topics, new_topics, db_index, db_topics = create_topics(chunks, db_index, db_topics)

    if database == "temp":
        temp_index, temp_topics = db_index, db_topics
    else:
        perm_index, perm_topics = db_index, db_topics

    # Build payload for vector DB
    payload = {
        "new_topics": new_topics,
        "existing_topics": existing_topics,
        "database": database
    }

    try:
        response = requests.post(VECTOR_DB_URL, json=payload)
        response.raise_for_status()
        logging.info(f"{TAG} Data successfully sent to the vector database. Status: {response.status_code}")

    except requests.RequestException as e:
        logging.error(f"{TAG} Failed to send data: {e}")


def create_topics(chunks, db_index, topic_names):
    """
    Check if the new data matches any existing topics. 
    """

    existing_topics = []
    outliers = []
    new_topics = []
    threshold = 1.4

    chunk_embeddings = embedding_function.encode(
        chunks, convert_to_numpy=True
    ).astype("float32")

    # If no topics exist yet, treat all chunks as outliers
    if not topic_names or db_index is None:
        outliers = list(zip(chunks, chunk_embeddings))
    else:
        # Compare each chunk to the FAISS index (existing topics)
        for chunk, emb in zip(chunks, chunk_embeddings):
            distances, indices = db_index.search(emb.reshape(1, -1), k=1)

            best_distance = distances[0][0]
            best_idx = indices[0][0]

            print(f'BEST:{best_distance}')

            if best_distance < threshold:
                topic_entry = next((t for t in existing_topics if t["topic_indx"] == best_idx), None)
                if topic_entry is not None:
                    topic_entry["chunks"].append({"text": chunk, "embedding": emb.tolist()})
                else:
                    existing_topics.append({
                        "topic_indx": int(best_idx),
                        "chunks": [{"text": chunk, "embedding": emb.tolist()}]
                    })
            else:
                outliers.append((chunk, emb))

    # Handle outliers
    if outliers:
        outlier_texts = [chunk for chunk, _ in outliers]

        topic_count = max(1, len(outliers) // 10)  # number of new topics to generate
        vectorizer, lda_model, lda_topic_names = vectorize(outlier_texts, topic_count)
        doc_topic = lda_model.doc_topic_

        for i, (chunk, emb) in enumerate(outliers):
            top_topic_idx = doc_topic[i].argmax()
            topic_name = lda_topic_names[top_topic_idx]

            # Skip if topic already exists
            if topic_name in topic_names:
                existing_idx = topic_names.index(topic_name)
                existing_topics.append({
                    "topic_indx": existing_idx,
                    "chunks": [{"text": chunk, "embedding": emb.tolist()}]
                })
                continue

            # Create new topic and update memory
            topic_emb = embedding_function.encode([topic_name]).astype("float32")[0]
            new_topics.append({
                "topic": topic_name,
                "topic_embeddings": topic_emb.tolist(),
                "chunks": [{"text": chunk, "embedding": emb.tolist()}]
            })

            # --- Update FAISS + topic list ---
            if db_index is None:
                dim = topic_emb.shape[0]
                db_index = faiss.IndexFlatL2(dim)

            db_index.add(np.array([topic_emb]))
            topic_names.append(topic_name)

    return existing_topics, new_topics, db_index, topic_names


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
    model = lda.LDA(n_topics=topic_count, n_iter=1500, random_state=1)
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

url = "http://127.0.0.1:8000/get_topics"

def fetch_topics(database_name):
    try:
        response = requests.post(url, json={"database": database_name}, timeout=5)
        response.raise_for_status()
        data = response.json()

        topic_names = data.get("topics", [])
        logging.info(f"{database_name} topics: {topic_names}")

        if not topic_names:
            logging.warning(f"No topics found for {database_name}")
            return [], None, None
        
        # Create embeddings and FAISS index
        topic_embeddings = embedding_function.encode(topic_names).astype("float32")
        dimension = topic_embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(topic_embeddings)

        logging.info(f"{database_name} embeddings shape: {topic_embeddings.shape}")

        return topic_names, topic_embeddings, index
    
    except Exception as e:
        logging.error(f"Error fetching {database_name} topics: {e}")
        return None, None, None
    

while True:
    try:
        perm_topics, perm_embeddings, perm_index = fetch_topics("permanent")

        if perm_topics is not None:
            logging.info("Successfully fetched topics from permanent database.")
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
            logging.info("Successfully fetched topics from temp database.")
            break
        else:
            logging.warning("No topics found in database. Retrying in 3s...")
            time.sleep(3)

    except Exception as e:
        logging.warning(f"Vector DB not ready ({e}), retrying in 3s...")
        time.sleep(3)