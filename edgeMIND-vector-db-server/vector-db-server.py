from flask import Flask, request, jsonify
from datetime import datetime
import faiss
import json
from sentence_transformers import SentenceTransformer
import numpy as np
import os
import socket

app = Flask(__name__)

index_file_path = 'multimodal_faiss_index.index'
metadata_file_path = 'topic_metadata_with_names.txt'

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


def choose_server(output_format):
    match output_format:
        case "text":
            return {"server_ip": "llm_query_server_text", "server_port": 6000}
        case "audio":
            return {"server_ip": "llm_query_server_audio", "server_port": 6001}
        case _:
            return {"server_ip": "llm_query_server_text", "server_port": 6000}


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


        msg = "Data stored successfully."
        print(msg)
        return jsonify({"status": "success", "message": msg})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/query', methods=['POST'])
def query_data():
    try:
        data = request.json
        query_text = data['message']
        output_format = data['output']

        index = load_faiss_index(index_file_path)
        metadata = load_metadata(metadata_file_path)

        results = search_faiss_index(query_text, index, metadata, embedding_function)

        if results:
            retrieved_texts = "\n".join([
                f"**Topic**: {r['topic']}\n**Timestamp**: {r['timestamp']}\n**Text**: {r['text']}\n"
                for r in results[:3]
            ])
            response = retrieved_texts
        else:
            response = ""

        llm_server = choose_server(output_format)
        payload = json.dumps({"query": query_text, "results": response})

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((llm_server['server_ip'], llm_server['server_port']))
            s.sendall(payload.encode('utf-8'))

        return jsonify({"status": "success", "results": results})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)