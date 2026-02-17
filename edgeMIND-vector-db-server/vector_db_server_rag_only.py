from flask import Flask, request, jsonify
import faiss
import json
import logging
from sentence_transformers import SentenceTransformer
import numpy as np
import os
import time
import requests
# import pyRAPL
import psutil
import base64

IN_K3S = os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token")
print(f"IN_K3S: {IN_K3S}")

def encode_embedding(vec: np.ndarray) -> str:
    """
    Encode a NumPy float32 vector into Base64 string.
    """
    return base64.b64encode(vec.tobytes()).decode("utf-8")


def decode_embedding(b64_str: str) -> np.ndarray:
    """
    Decode a Base64 string back into a NumPy float32 vector.
    """
    arr = np.frombuffer(base64.b64decode(b64_str), dtype=np.float32)
    return arr

# pyRAPL.setup()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

embedding_function = SentenceTransformer('all-mpnet-base-v2')

TAG = "vector_db:  "

if IN_K3S == False:
    PERMANENT_METADATA_FILE_PATH = 'permanent_metadata2.json'
    TEMP_METADATA_FILE_PATH = 'temp_metadata2.json'
else:
    PERMANENT_METADATA_FILE_PATH = "permanent_metadata2.json"
    TEMP_METADATA_FILE_PATH = "temp_metadata2.json"

# PERMANENT_INDEX_FILE_PATH = 'multimodal_faiss_index.index'
# TEMP_INDEX_FILE_PATH  = 'temp_index.index'

data_from_last_uploaded_file = []

def load_metadata2(file_path):
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@app.route("/health")
def health():
    return {"status": "ok"}, 200


# def load_faiss_index(index_file_path):
#     if not os.path.exists(index_file_path) or os.path.getsize(index_file_path) == 0:
#         return None
#     return faiss.read_index(index_file_path)


@app.route("/store", methods=["POST"])
def store():
    global permanent_metadata, permanent_index
    global temp_metadata, temp_index

    data = request.get_json()

    chunks = data.get("chunks", [])
    database = data.get("database", "permanent")

    if not chunks:
        return jsonify({"status": "error", "message": "No chunks provided"}), 400

    # Select database
    if database == "temp":
        metadata = temp_metadata
        index = temp_index
        metadata_path = TEMP_METADATA_FILE_PATH
    else:
        metadata = permanent_metadata
        index = permanent_index
        metadata_path = PERMANENT_METADATA_FILE_PATH

    vectors = []

    # Add chunks & vectors
    for ch in chunks:
        metadata.append(ch)

        vec = decode_embedding(ch["embedding_b64"])
        vectors.append(vec)

    vectors_np = np.vstack(vectors).astype("float32")

    # If index doesn't exist yet → create it
    if index is None:
        dim = len(vectors_np[0])
        index = faiss.IndexFlatL2(dim)

    index.add(vectors_np)

    # Save metadata
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Update globals
    if database == "temp":
        temp_metadata = metadata
        temp_index = index
    else:
        permanent_metadata = metadata
        permanent_index = index

    return jsonify({"status": "success", "added": len(chunks)})


@app.route('/get_topics', methods=['GET', 'POST'])
def get_topics():
    request_data = request.get_json(silent=True) or {}
    database = request_data.get('database', '')

    if database == "temp":
        metadata_path = TEMP_METADATA_FILE_PATH
    else:
        metadata_path = PERMANENT_METADATA_FILE_PATH

    if not os.path.exists(metadata_path):
        return jsonify({"status": "error", "message": "No metadata file found."}), 400

    try:
        metadata = load_metadata2(metadata_path)
        
        # Get unique topics
        topics = sorted(list({entry["topic"] for entry in metadata}))
        
        return jsonify({"status": "success", "topics": topics}), 200
    
    except Exception as e:
        logging.error(f"Failed to read topics: {e}")
        return jsonify({"status": "error", "message": "Could not read topics"}), 500


def save_metadata(metadata, file_path):
    """
    Save metadata to a file as standard JSON using json.dump.
    """
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


@app.route('/get_data_from_last_uploaded_file', methods=['GET', 'POST'])
def get_data_from_last_uploaded_file():
    if data_from_last_uploaded_file:
        return jsonify({"data": data_from_last_uploaded_file}), 200
    else:
        return jsonify({"error": "No files have been uploaded yet!"}), 404



@app.route("/search", methods=["POST"])
def search():
    global permanent_metadata, permanent_index
    global temp_metadata, temp_index

    req = request.get_json()

    # Determine database
    database = req.get("database", "permanent")
    if database == "temp":
        metadata = temp_metadata
        index = temp_index
    else:
        metadata = permanent_metadata
        index = permanent_index

    if index is None or len(metadata) == 0:
        return jsonify({"status": "error", "message": "database is empty"}), 400

    # ---- Option 1: Text query ----
    question = req.get("question")
    if question:
        # Embed text just like the old server
        query_vec = embedding_function.encode([question]).astype("float32")
        print(f"SEARCH TEXT QUERY: {question}")
    else:
        # ---- Option 2: Embedding query ----
        emb_b64 = req.get("embedding_b64")
        if emb_b64 is None:
            return jsonify({
                "status": "error", 
                "message": "Provide either 'question' or 'embedding_b64'."
            }), 400

        query_vec = decode_embedding(emb_b64).reshape(1, -1)

    # Run FAISS search
    distances, indices = index.search(query_vec, k=4)

    # Build results — only texts, old format compatible
    permanent_chunks = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx == -1:
            continue

        entry = metadata[idx]
        permanent_chunks.append(entry["text"])

    return jsonify({
        "permanent_chunks": permanent_chunks,
        "temp_chunks": []
    })


def init_store(metadata_path):
    """
    Loads flat metadata list and builds a single FAISS index
    containing all chunk embeddings.
    """
    metadata = load_metadata2(metadata_path)

    # No metadata -> empty state
    if not metadata:
        return [], None

    # Determine embedding dimension from first entry
    first_vec = decode_embedding(metadata[0]["embedding_b64"])
    dim = len(first_vec)

    # Build FAISS index
    index = faiss.IndexFlatL2(dim)

    # Decode and add all vectors
    vectors = []
    for entry in metadata:
        emb = decode_embedding(entry["embedding_b64"])
        vectors.append(emb)

    vectors_np = np.vstack(vectors).astype("float32")
    index.add(vectors_np)

    return metadata, index


permanent_metadata, permanent_index = init_store(PERMANENT_METADATA_FILE_PATH)
temp_metadata, temp_index = init_store(TEMP_METADATA_FILE_PATH)

# permanent_metadata, permanent_topic_index, permanent_chunk_indices = init_store(PERMANENT_METADATA_FILE_PATH)
# temp_metadata, temp_topic_index, temp_chunk_indices = init_store(TEMP_METADATA_FILE_PATH)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)