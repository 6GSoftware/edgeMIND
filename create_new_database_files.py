""" Module for initializing and creating the database files.
The data in the Pre_processed_text.txt file is used as the base for the database files.
"""

import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import numpy as np
import lda
from sklearn.feature_extraction.text import CountVectorizer
from datetime import datetime
import json
import faiss
from sentence_transformers import SentenceTransformer
import logging

import torch
print(torch.cuda.is_available())

logging.basicConfig(level=logging.INFO)

TAG = "situational_awareness_faiss:  "
VECTOR_DB_URL = "http://vector_db_server:8000/store"

MONITOR_URL = "http://host.docker.internal:5006/status"

file_path = './situational-awareness-server/Pre_processed_text.txt'
output_file_path = './topic_metadata_with_names.txt'

# Initialize the embedding model
embedding_function = SentenceTransformer('all-mpnet-base-v2', device='cpu')


def send_new_data_to_database():
    
    with open(file_path, 'r') as file:
        documents = file.readlines()
    
    # Split the new data into chunks
    chunks = get_chunks(documents)

    # Prepare metadata to send to the vector database
    metadata = []
    timestamp = datetime.now().isoformat()

    # Generate embeddings and collect metadata for each chunk
    embeddings = []
    for chunk in chunks:
        # Generate embedding for each chunk
        embedding = embedding_function.encode([chunk]).astype('float16')[0]

        # Collect embeddings and metadata
        embeddings.append(embedding)  # Store the embedding for FAISS

        # Store the metadata with the topic name
        metadata.append({
            "timestamp": timestamp,
            #"topic": None,  # Store the topic name here
            "text": chunk,
            "embedding": embedding.tolist()  # Convert numpy array to list for JSON serialization
        })

    # Step 11: Save FAISS index using the embeddings
    dimension = embeddings[0].shape[0]  # Embedding dimension size
    index = faiss.IndexFlatL2(dimension)  # Create a FAISS index using L2 distance
    index.add(np.array(embeddings))  # Add embeddings to FAISS index

    # Save FAISS index to a file
    faiss.write_index(index, 'multimodal_faiss_index.index')

    # Step 12: Save metadata to a text file in JSON format
    with open(output_file_path, 'w') as f:
        for entry in metadata:
            f.write(json.dumps(entry) + '\n')  # Write each entry as a JSON string

    print(f"{TAG} FAISS index saved and metadata has been saved to '{output_file_path}' with {len(metadata)} entries.")


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

#initial_vectorizer, initial_model, initial_topic_names = init_model()
send_new_data_to_database()