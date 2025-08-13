from flask import Flask, request, jsonify
from datetime import datetime
import faiss
import json
import logging
from sentence_transformers import SentenceTransformer
import numpy as np
import os

logging.basicConfig(level=logging.INFO)


app = Flask(__name__)

index_file_path = 'multimodal_faiss_index.index'
metadata_file_path = 'topic_metadata_with_names.txt'

DB_SERVER_IP = "0.0.0.0"
DB_SERVER_PORT = 8000

embedding_function = SentenceTransformer('all-mpnet-base-v2')



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


@app.route('/store', methods=['POST'])
def store_data():
    try:
        data = request.json
        metadata = data["metadata"]

        embeddings = np.array([np.array(entry["embedding"], dtype='float32') for entry in metadata])

        with open(metadata_file_path, 'a') as f:
            for entry in metadata:
                f.write(json.dumps(entry) + '\n')

        if os.path.exists(index_file_path):
            index = load_faiss_index(index_file_path)
        else:
            dimension = embeddings[0].shape[0]
            index = faiss.IndexFlatL2(dimension)

        index.add(embeddings)
        faiss.write_index(index, index_file_path)
        logging.info("Wrote new data to faiss index!")


        msg = "Data stored successfully."
        logging.info(msg)
        return jsonify({"status": "success", "message": msg})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    

@app.route('/search', methods=['POST'])
def search_database():
    try:
        request_data = request.get_json()
        question = request_data['question']
        logging.info(f"Received: {question}")

        #results = f"Your question was: {question}"

        # Load faiss index, metadata and embedding function every time a new client is connected
        index = load_faiss_index(index_file_path)
        metadata = load_metadata(metadata_file_path)
        #embedding_function = load_embedding_function()

        results = search_faiss_index(question, index, metadata, embedding_function)
        logging.info("Result from searching the faiss index:\n", results)

        #result_list = [result['text'] for result in results]
        #result_string = str(result_list)
        #logging.info(f"The result as a string: {result_string}\n")

        result_as_json = json.dumps(str(results))
        #result_as_json = json.dumps(result_string)

        return jsonify({"status": "success", "message": result_as_json})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    

#if __name__ == '__main__':
#    app.run(host=DB_SERVER_IP, port=DB_SERVER_PORT)