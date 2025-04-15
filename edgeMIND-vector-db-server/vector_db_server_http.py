import faiss
import json
import logging
#from pydantic import BaseModel
import numpy as np
from sentence_transformers import SentenceTransformer
from flask import Flask, request

logger = logging.getLogger(__name__)

app = Flask(__name__)

DB_SERVER_IP = "---"

index_file_path = 'multimodal_faiss_index.index'
metadata_file_path = 'topic_metadata_with_names.txt'


def write_to_faiss_index(embeddings, metadata):
    # Load FAISS index
    index = load_faiss_index(index_file_path)
    # Get embedding dimension size
    new_dimension = embeddings[0].shape[0]
    # Get index dimension size
    index_dimension = index.d

    # If FAISS index could not be loaded, create a new one
    if not index:
        index = faiss.IndexFlatL2(new_dimension)  # Create a FAISS index using L2 distance

    # Save FAISS index using the embeddings
    index.add(np.array(embeddings))  # Add embeddings to FAISS index

    # Save FAISS index to a file
    faiss.write_index(index, 'multimodal_faiss_index.index')

    # Step 12: Save metadata to a text file in JSON format
    with open(metadata_file_path, 'a') as f:
        for entry in metadata:
            f.write(json.dumps(entry) + '\n')  # Write each entry as a JSON string

    print(f"FAISS index saved and metadata has been saved to '{metadata_file_path}' with {len(metadata)} entries.")


def load_metadata(file_path):
    """Load metadata from a file."""
    metadata = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            metadata.append(json.loads(line.strip()))  # Parse JSON lines
    return metadata


def load_faiss_index(index_file_path):
    """Load the FAISS index."""
    return faiss.read_index(index_file_path)


def load_embedding_function():
    return SentenceTransformer('all-mpnet-base-v2')


def search_faiss_index(query_text, index, metadata, embedding_function, k=3):
    """Search FAISS index for the closest topic."""

    # Do the actual search to the faiss index
    query_embedding = embedding_function.encode([query_text]).astype('float32')  # Generate query embedding
    distances, indices = index.search(query_embedding, k)  # Retrieve top-k results
    
    results = []
    for i, idx in enumerate(indices[0]):
        if idx == -1:  # FAISS returns -1 if no result is found
            continue
        result_entry = metadata[idx]
        results.append({
            "text": result_entry["text"],
            "topic": result_entry["topic"],
            "timestamp": result_entry["timestamp"],
            "distance": distances[0][i]
        })
    
    return results


@app.route('/write', methods=['POST'])
def write_to_database():
    """Write new data to the vector database."""
    request_data = request.get_json()
    embeddings = request_data['embeddings']
    metadata = request_data['metadata']
    print(f"Received:\n{embeddings}\nand\n{metadata}")

    write_to_faiss_index(embeddings, metadata)

    response = "Data received!"

    return {'message': response}, 200


@app.route('/search', methods=['POST'])
def search_database():
    request_data = request.get_json()
    question = request_data['question']
    print(f"Received: {question}")

    #results = f"Your question was: {question}"
    
    # Load faiss index, metadata and embedding function every time a new client is connected
    index = load_faiss_index(index_file_path)
    metadata = load_metadata(metadata_file_path)
    embedding_function = load_embedding_function()
    
    results = search_faiss_index(question, index, metadata, embedding_function)
    print("Result from searching the faiss index:\n", results)

    result_as_json = json.dumps(str(results))

    return {'message': result_as_json}, 200


if __name__ == '__main__':
    app.run(host=DB_SERVER_IP, port=8000)