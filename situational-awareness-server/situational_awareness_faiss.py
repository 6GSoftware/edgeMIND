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

VECTOR_DB_URL = "http://vector_db_server:8000/store"
VECTOR_DB_URL2 = "http://127.0.0.1:8000/store2"

#VECTOR_DB_STORE_TO_TEMP_URL = "http://vector_db_server:8000/store-to-tmp"

file_path = './Pre_processed_text.txt'

# Initialize the embedding model
embedding_function = SentenceTransformer('all-mpnet-base-v2')

#----------------------------------------------------------------------------------------------------------------------------

def send_new_data_to_database(documents):
    # Split the new data into chunks
    chunks = get_chunks(documents)

    #metadata = do_topic_modeling(chunks)
    all_chunks = create_topics(chunks)
    metadata = create_metadata_for_text_chunks(all_chunks)
    
    try:
        response = requests.post(VECTOR_DB_URL, json={"metadata": metadata})
        response.raise_for_status()
        logging.info(f"{TAG} Data successfully sent to the vector database. Status: {response.status_code}")
    except requests.RequestException as e:
        logging.info(f"{TAG} Failed to send data: {e}")


def send_new_data_to_database2(documents):
    global index, topic_names

    # Split the new data into chunks
    chunks = get_chunks(documents)

    existing_topics, new_topics = create_topics2(chunks)

    # Build payload for vector DB
    payload = {
        "new_topics": new_topics,
        "existing_topics": existing_topics
    }

    try:
        response = requests.post(VECTOR_DB_URL2, json=payload)
        response.raise_for_status()

        if new_topics:
            topic_labels = [t["topic"] for t in new_topics]
            embeddings = np.array([t["topic_embeddings"] for t in new_topics], dtype="float32")

            if index is None:
                dim = embeddings.shape[1]
                index = faiss.IndexFlatL2(dim)

            index.add(embeddings)
            topic_names.extend(topic_labels)

        logging.info(f"{TAG} Data successfully sent to the vector database. Status: {response.status_code}")
    except requests.RequestException as e:
        logging.error(f"{TAG} Failed to send data: {e}")


def create_metadata_for_text_chunks(all_chunks):
    """
    Create a list that contains all metadata for all the text chunks extracted from the uploaded file.
    """
    # Prepare metadata to send to the vector database
    metadata = []
    timestamp = datetime.now().isoformat()

    # Generate embeddings and collect metadata for each chunk
    for chunk_text, topic_name in all_chunks:
        # Generate embedding for each TOPIC!!!
        embedding = embedding_function.encode([topic_name]).astype('float16')[0]

        # Store the metadata with the topic name
        metadata.append({
            "timestamp": timestamp,
            "topic": topic_name,  # Store the topic name here
            "text": chunk_text,
            "embedding": embedding.tolist()  # Convert numpy array to list for JSON serialization
        })

    return metadata


def create_topics(data):
    """
    Check if the new data matches any existing topics. If not, create new topics for those chunks.
    """

    # Transform new chunks to a document-term matrix with the initial vectorizer
    X = initial_vectorizer.transform(data)

    topic_word = initial_model.topic_word_

    # Calculate the propability of a topic suiting a chunk
    topic_scores_matrix = X @ topic_word.T

    # Add a tiny epsilon to avoid division by zero if any row is all zeros
    epsilon = 1e-12

    row_sums = topic_scores_matrix.sum(axis=1) + epsilon
    topic_probs_matrix = topic_scores_matrix / row_sums[:, np.newaxis]
    #logging.info(f"{TAG} the topic_probs_matrix is: {np.matrix(topic_probs_matrix)}\n")

    fitting_chunks = []
    outliers = []

    # Calculate which are the topics that suit best for each chunk
    best_topic_indices = topic_probs_matrix.argmax(axis=1)  # Best topic per chunk <- index of the topic
    #logging.info(f"{TAG} the best topic indices: {best_topic_indices}")
    # Get the score of the best fitting topic per chunk
    best_topic_scores = topic_probs_matrix.max(axis=1)      # Best topic score per chunk <- best score
    #logging.info(f"{TAG} the best topic scores per chunk: {best_topic_scores}")

    threshold = 0.5

    # Determine which chunks should be assigned an existing topic and which ones should be generated a new topic
    for idx, score in enumerate(best_topic_scores):
        if score > threshold:
            topic_name = initial_topic_names[best_topic_indices[idx]]
            #fitting_chunks.append((chunks[idx], topic_name))
            outliers.append(data[idx])
        else:
            outliers.append(data[idx])

    if outliers:
        # Vectorizer for outliers
        new_vectorizer, new_model, new_topic_names = vectorize(outliers, 1)

        doc_topic = new_model.doc_topic_

        # Set the best matching topics for outliers
        for i, chunk in enumerate(outliers):
            top_topic_idx = doc_topic[i].argmax()
            top_topic_name = new_topic_names[top_topic_idx]
            outliers[i] = (chunk, top_topic_name)

    # Combine chunks
    all_chunks = fitting_chunks + outliers

    return all_chunks


def create_topics2(chunks):
    global index, topic_names

    """
    Check if the new data matches any existing topics. 
    """

    existing_topics = []
    outliers = []
    new_topics = []

    threshold = 1.4

    # If no topics exist yet, treat all chunks as outliers
    if not topic_names or index is None:
        outliers = chunks
    else:
        # Encode all chunks into embeddings in one batch
        chunk_embeddings = embedding_function.encode(
            chunks, convert_to_numpy=True
        ).astype("float32")

        # Compare each chunk to the FAISS index (existing topics)
        for chunk, emb in zip(chunks, chunk_embeddings):
            emb = emb.reshape(1, -1)
            distances, indices = index.search(emb, k=1)

            best_distance = distances[0][0]
            best_idx = indices[0][0]

            print(f'BEST:{best_distance}')

            if best_distance < threshold:
                topic_entry = next((t for t in existing_topics if t["topic_indx"] == best_idx), None)
                if topic_entry is not None:
                    topic_entry["chunks"].append({"text": chunk})
                else:
                    existing_topics.append({
                        "topic_indx": int(best_idx),
                        "chunks": [{"text": chunk}]
                    })
            else:
                outliers.append(chunk)

    # Handle outliers
    if outliers:
        topic_count = topic_count = max(1, len(outliers) // 10)  # number of new topics to generate
        vectorizer, lda_model, lda_topic_names = vectorize(outliers, topic_count)
        doc_topic = lda_model.doc_topic_

        for i, chunk in enumerate(outliers):
            top_topic_idx = doc_topic[i].argmax()
            topic_name = lda_topic_names[top_topic_idx]

            # Get embedding for this topic name
            new_topic_emb = embedding_function.encode([topic_name]).astype("float32")

            # Group chunks under the same topic if already exists
            topic_entry = next((t for t in new_topics if t["topic"] == topic_name), None)
            if topic_entry is not None:
                topic_entry["chunks"].append({"text": chunk})
            else:
                new_topics.append({
                    "topic": topic_name,
                    "topic_embeddings": new_topic_emb[0].tolist(),
                    "chunks": [{"text": chunk}]
                })

    return existing_topics, new_topics


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


def init_model():
    """
    Initialize the topic model by reading existing data,
    chunking it, and fitting a vectorizer and LDA model.
    """
    with open(file_path, 'r') as file:
        documents = file.readlines()
    chunks = get_chunks(documents)
    return vectorize(chunks, 50)

# initial_vectorizer, initial_model, initial_topic_names = init_model()

#-------------------------------------------

# Initialize FAISS index from existing topics:
# fetch topics for vector DB, encode them, and build the index
topic_embeddings = None
dimension = None
index = None
topic_names = []

url = "http://127.0.0.1:8000/get_topics"


while True:
    try:
        response = requests.get(url)
        data = response.json()

        topics = data.get("topics", [])

        if topics:
            logging.info(f"Topics: {topics}")

            topic_names = [t for t in topics if isinstance(t, str) and t.strip()]
            if not topic_names:
                logging.error("No valid topics found after filtering")
            else:
                topic_embeddings = embedding_function.encode(topic_names).astype("float32")
                logging.info(f"Embeddings shape: {topic_embeddings.shape}")

                # Build FAISS index
                dimension = topic_embeddings.shape[1]
                index = faiss.IndexFlatL2(dimension)
                index.add(topic_embeddings)

            break
        else:
            logging.error("No topics found in API response")
            break
    except Exception as e:
        logging.warning(f"Vector DB not ready ({e}), retrying in 3s...")
        time.sleep(3)


# def user_question(query_text, k=3):
#     global unique_topics, index 

#     """
#     Compare a user query to the topic names and return the best matches.
#     """

#     if unique_topics is None:
#         raise ValueError("unique_topics must be provided")

#     # generate embedding for query
#     query_embedding = embedding_function.encode([query_text]).astype('float32')

#     # search in FAISS index
#     distances, indices = index.search(query_embedding, k)

#     # collect results
#     results = []
#     for i, idx in enumerate(indices[0]):
#         results.append({
#             "topic": unique_topics[idx],
#             "distance": float(distances[0][i])
#         })

#     print(f"\nUser query: {query_text}")
#     for r in results:
#         print(f"- {r['topic']} (distance={r['distance']:.4f})")

#     return results