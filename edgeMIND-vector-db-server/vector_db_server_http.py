import faiss
import json
import logging
#from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from flask import Flask, request

logger = logging.getLogger(__name__)

app = Flask(__name__)

DB_SERVER_IP = "---"

index_file_path = 'multimodal_faiss_index.index'
metadata_file_path = 'topic_metadata_with_names.txt'


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
    ...


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