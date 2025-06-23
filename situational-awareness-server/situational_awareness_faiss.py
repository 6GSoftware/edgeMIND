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

logging.basicConfig(level=logging.INFO)

TAG = "situational_awareness_faiss:  "
VECTOR_DB_URL = "http://vector_db_server:8000/store"

MONITOR_URL = "http://host.docker.internal:5006/status"

file_path = './Pre_processed_text.txt'

# Initialize the embedding model
embedding_function = SentenceTransformer('all-mpnet-base-v2')


def send_new_data_to_database(documents):
    """
    Check if the new data matches any existing topics. If not, create new topics for those chunks.
    Finally, forward the processed data to the vector database.
    """

    # Split the new data into chunks
    chunks = get_chunks(documents)

    # Transform new chunks to a document-term matrix with the initial vectorizer
    X = initial_vectorizer.transform(chunks)

    topic_word = initial_model.topic_word_

    # Calculate the propability of a topic suiting a chunk
    topic_scores_matrix = X @ topic_word.T

    # Add a tiny epsilon to avoid division by zero if any row is all zeros
    epsilon = 1e-12

    row_sums = topic_scores_matrix.sum(axis=1) + epsilon
    topic_probs_matrix = topic_scores_matrix / row_sums[:, np.newaxis]
    #logging.info(f"{TAG} the topic_probs_matrix is: {np.matrix(topic_probs_matrix)}\n")

    fitting_chunks = []
    outliners = []

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
            outliners.append(chunks[idx])
        else:
            outliners.append(chunks[idx])



    if outliners:
        # Vectorizer for outliers
        new_vectorizer, new_model, new_topic_names = vectorize(outliners, 1)

        doc_topic = new_model.doc_topic_

        # Set the best matching topics for outliers
        for i, chunk in enumerate(outliners):
            top_topic_idx = doc_topic[i].argmax()
            top_topic_name = new_topic_names[top_topic_idx]
            outliners[i] = (chunk, top_topic_name)

    # Combine chunks
    all_chunks = fitting_chunks + outliners

    # Prepare metadata to send to the vector database
    metadata = []
    timestamp = datetime.now().isoformat()

    # Generate embeddings and collect metadata for each chunk
    embeddings = []
    for chunk_text, topic_name in all_chunks:
        # Generate embedding for each chunk
        embedding = embedding_function.encode([chunk_text]).astype('float16')[0]

        # Collect embeddings and metadata
        embeddings.append(embedding)  # Store the embedding for FAISS

        # Store the metadata with the topic name
        metadata.append({
            "timestamp": timestamp,
            "topic": topic_name,  # Store the topic name here
            "text": chunk_text,
            "embedding": embedding.tolist()  # Convert numpy array to list for JSON serialization
        })

    try:
        res = requests.post(MONITOR_URL, json={
            "state": "stop",
            "service-name": "situational_awareness_server"
        }, timeout=2)
        logging.info(f"Started monitoring: {res.json()}")
    except Exception as e:
        logging.warning(f"Monitoring service not available: {e}")

    try:
        response = requests.post(VECTOR_DB_URL, json={"metadata": metadata})
        response.raise_for_status()
        logging.info(f"{TAG} Data successfully sent to the vector database. Status: {response.status_code}")
    except requests.RequestException as e:
        logging.info(f"{TAG} Failed to send data: {e}")


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
        topic_names.append(topic_name)  # Store the topic name

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

initial_vectorizer, initial_model, initial_topic_names = init_model()