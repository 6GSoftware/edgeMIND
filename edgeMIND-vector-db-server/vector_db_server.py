from flask import Flask, request, jsonify
import faiss
import json
import logging
from sentence_transformers import SentenceTransformer
import numpy as np
import os
import time
import requests
import pyRAPL
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

pyRAPL.setup()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

embedding_function = SentenceTransformer('all-mpnet-base-v2')

TAG = "vector_db:  "

if IN_K3S == False:
    PERMANENT_METADATA_FILE_PATH = 'permanent_metadata.json'
    TEMP_METADATA_FILE_PATH = 'temp_metadata.json'
else:
    PERMANENT_METADATA_FILE_PATH = "/results2/metadata/permanent_metadata.json"
    TEMP_METADATA_FILE_PATH = "/results2/metadata/temp_metadata.json"

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


@app.route('/store', methods=['POST'])
def store():
    global data_from_last_uploaded_file
    global permanent_metadata, permanent_topic_index, permanent_chunk_indices
    global temp_metadata, temp_topic_index, temp_chunk_indices

    data_from_last_uploaded_file = []

    data = request.get_json()

    run_id = data.get("run_id", "")

    start_time = time.time()

    meter = pyRAPL.Measurement(f"vector_db_{run_id}")
    meter.begin()

    new_topics = data.get("new_topics", [])
    existing_topics = data.get("existing_topics", [])
    database = data.get("database", "")

    if database == "temp":
        metadata = temp_metadata
        topic_index = temp_topic_index
        chunk_indices = temp_chunk_indices
        metadata_path = TEMP_METADATA_FILE_PATH
    else:
        metadata = permanent_metadata
        topic_index = permanent_topic_index
        chunk_indices = permanent_chunk_indices
        metadata_path = PERMANENT_METADATA_FILE_PATH


    # --- Handle new topics ---
    for topic in new_topics:
        topic_name = topic["topic"]
        chunks = topic["chunks"]

        # Encode topic embedding
        topic_vec = embedding_function.encode([topic_name], convert_to_numpy=True)[0].astype("float32")  # CHANGED
        topic_vec_b64 = encode_embedding(topic_vec)  # NEW

        # Encode chunk embeddings
        chunk_texts = [c["text"] for c in chunks]  # CHANGED
        chunk_vecs = embedding_function.encode(chunk_texts, convert_to_numpy=True).astype("float32")  # CHANGED

        dim = chunk_vecs.shape[1]
        chunk_index = faiss.IndexFlatL2(dim)
        chunk_index.add(chunk_vecs)
        chunk_indices.append(chunk_index)

        # Build metadata entry with Base64 embeddings
        topic_entry = {  # NEW
            "topic": topic_name,
            "topic_embedding_b64": topic_vec_b64,  # NEW
            "chunks": []  # NEW
        }  # NEW

        for text, vec in zip(chunk_texts, chunk_vecs):  # NEW
            topic_entry["chunks"].append({  # NEW
                "text": text,
                "embedding_b64": encode_embedding(vec)  # NEW
            })  # NEW
            data_from_last_uploaded_file.append(text)

        metadata.append(topic_entry)  # CHANGED (now includes embeddings)

        # Add topic embedding to FAISS index
        if topic_index is None:
            topic_index = faiss.IndexFlatL2(topic_vec.shape[0])
        topic_index.add(topic_vec.reshape(1, -1))

    # --- Handle existing topics ---
    for topic in existing_topics:
        topic_indx = topic["topic_indx"]
        chunks = topic["chunks"]

        if 0 <= topic_indx < len(metadata):
            new_texts = [c["text"] for c in chunks]  # NEW
            new_vecs = embedding_function.encode(new_texts, convert_to_numpy=True).astype("float32")  # NEW

            # Append new chunks with Base64 embeddings
            for text, vec in zip(new_texts, new_vecs):  # NEW
                metadata[topic_indx]["chunks"].append({  # NEW
                    "text": text,
                    "embedding_b64": encode_embedding(vec)  # NEW
                })  # NEW
                data_from_last_uploaded_file.append(text)

            # Add embeddings to FAISS chunk index
            if chunk_indices[topic_indx] is None:
                dim = new_vecs.shape[1]
                chunk_indices[topic_indx] = faiss.IndexFlatL2(dim)
            chunk_indices[topic_indx].add(new_vecs)
        else:
            return jsonify({
                "status": "error",
                "message": f"Invalid topic index {topic_indx}"
            }), 400

    # Save updated metadata with Base64 embeddings
    save_metadata(metadata, metadata_path)  # CHANGED

    # Update global variables
    if database == "temp":
        temp_metadata = metadata
        temp_topic_index = topic_index
        temp_chunk_indices = chunk_indices
    else:
        permanent_metadata = metadata
        permanent_topic_index = topic_index
        permanent_chunk_indices = chunk_indices

    return jsonify({"status": "success", "message": "Data stored"})


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
        topics = [entry["topic"] for entry in metadata]
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



@app.route('/search', methods=['POST'])
def search():
    try:
        request_data = request.get_json()
        question = request_data.get('question', '')

        if not question:
            return jsonify({"status": "error", "message": "No question provided"}), 400

        print(f"Received question: {question}")

        # Encode the query
        query_emb = embedding_function.encode([question]).astype("float32")

        threshold = 1.5

        permanent_results = []
        if permanent_topic_index is not None and permanent_metadata:

            # Find the best matching permanent topic
            _, topic_indices = permanent_topic_index.search(query_emb, k=1)
            best_topic_idx = int(topic_indices[0][0])

            # Search inside the chosen permanent topic's chunks
            chunk_distances, chunk_idxs = permanent_chunk_indices[best_topic_idx].search(query_emb, k=3)

            for i, idx in enumerate(chunk_idxs[0]):

                if idx == -1:
                    continue  # FAISS placeholder for "no result"

                chunk_text = permanent_metadata[best_topic_idx]['chunks'][idx]['text']
                distance = float(chunk_distances[0][i])

                print("\n----- PERMANENT RESULT -----")
                print(f"PERM CHUNK: {chunk_text}")
                print(f"PERM DISTANCE: {distance}")
                print("----------------------------\n")

                if distance > threshold:
                    continue

                permanent_results.append(chunk_text)


        temp_results = []
        if temp_topic_index is not None and temp_metadata:

            # Find the best matching temp topic
            _, topic_indices = temp_topic_index.search(query_emb, k=1)
            best_topic_idx = int(topic_indices[0][0])

            # Search inside the chosen temp topic's chunks
            chunk_distances, chunk_idxs = temp_chunk_indices[best_topic_idx].search(query_emb, k=3)

            for i, idx in enumerate(chunk_idxs[0]):

                print(f"IDXS: {idx}")

                if idx == -1:
                    continue  # FAISS placeholder

                chunk_text = temp_metadata[best_topic_idx]['chunks'][idx]['text']
                distance = float(chunk_distances[0][i])

                print("\n------- TEMP RESULT -------")
                print(f"TEMP CHUNK: {chunk_text}")
                print(f"TEMP DISTANCE: {distance}")
                print("---------------------------\n")

                if distance > threshold:
                    continue

                temp_results.append(chunk_text)


        payload = {
            "permanent_chunks": permanent_results,
            "temp_chunks": temp_results
        }

        logging.info(f"Payload: {payload}")

        return jsonify(payload), 200
    
    except Exception as e:
        logging.error(f"Error in search: {e}")
        return jsonify({"message": str(e)}), 500


# @app.route('/search', methods=['POST'])
# def search():
#     try:
#         request_data = request.get_json()
#         question = request_data.get('question', '')

#         if not question:
#             return jsonify({"status": "error", "message": "No question provided"}), 400

#         logging.info(f"Received question: {question}")

#         # Encode the query
#         query_emb = embedding_function.encode([question]).astype("float32")

#         threshold = 1.0

#         permanent_results = []
#         if permanent_topic_index is not None and permanent_metadata:
#             # Find the best matching permanent topic
#             _, topic_indices = permanent_topic_index.search(query_emb, k=1)
#             best_topic_idx = int(topic_indices[0][0])

#             # Search inside the chosen permanent topic's chunks
#             chunk_distances, chunk_idxs = permanent_chunk_indices[best_topic_idx].search(query_emb, k=3)

#             for i, idx in enumerate(chunk_idxs[0]):

#                 logging.info("")

#                 print(f"PERM CHUNK: {permanent_metadata[best_topic_idx]['chunks'][idx]['text']}")
#                 print(f"PERM DISTANCE: {chunk_distances[0][i]}")

#                 logging.info("")
                             
#                 if idx == -1 or chunk_distances[0][i] > threshold:
#                     continue
#                 try:
#                     permanent_results.append(permanent_metadata[best_topic_idx]["chunks"][idx]["text"])
#                 except Exception as e:
#                     logging.error(f"Failed to fetch permanent chunk idx={idx}: {e}")

#         temp_results = []
#         if temp_topic_index is not None and temp_metadata:

#             # Find the best matching temp topic
#             _, topic_indices = temp_topic_index.search(query_emb, k=1)
#             best_topic_idx = int(topic_indices[0][0])

#             # Search inside the chosen temp topic's chunks
#             chunk_distances, chunk_idxs = temp_chunk_indices[best_topic_idx].search(query_emb, k=3)

#             for i, idx in enumerate(chunk_idxs[0]):

#                 logging.info("")

#                 print(f"TEMP CHUNK: {temp_metadata[best_topic_idx]['chunks'][idx]['text']}")
#                 print(f"TEMP DISTANCE: {chunk_distances[0][i]}")

#                 logging.info("")

#                 if idx == -1 or chunk_distances[0][i] > threshold:
#                     continue
#                 try:
#                     temp_results.append(temp_metadata[best_topic_idx]["chunks"][idx]["text"])
#                 except Exception as e:
#                     logging.error(f"Failed to fetch temp chunk idx={idx}: {e}")

#         payload = {
#             "permanent_chunks": permanent_results,
#             "temp_chunks": temp_results
#         }

#         logging.info(f"Payload: {payload}")

#         return jsonify(payload), 200
    
#     except Exception as e:
#         logging.error(f"Error in search: {e}")
#         return jsonify({"message": str(e)}), 500
        

def init_store(metadata_path):
    """
    Initialize metadata list, topic index, and chunk indices
    from given metadata file with Base64-encoded embeddings.
    """
    metadata = load_metadata2(metadata_path)

    # If no metadata file exists or it's empty, return empty structures
    if not metadata:
        return [], None, []

    # If Base64 embeddings don't exist yet (old format), return metadata only
    if "topic_embedding_b64" not in metadata[0]:
        return metadata, None, []

    # Determine embedding dimensionality from the first topic
    first_vec = decode_embedding(metadata[0]["topic_embedding_b64"])
    dim = len(first_vec)

    # Build FAISS topic index
    topic_embeddings = np.vstack([decode_embedding(t["topic_embedding_b64"]) for t in metadata])
    topic_index = faiss.IndexFlatL2(dim)
    topic_index.add(topic_embeddings)

    # Build FAISS chunk indices for each topic
    chunk_indices = []
    for topic in metadata:
        chunks = topic.get("chunks", [])
        if not chunks or "embedding_b64" not in chunks[0]:
            chunk_indices.append(None)
            continue

        chunk_embs = np.vstack([decode_embedding(c["embedding_b64"]) for c in chunks])
        idx = faiss.IndexFlatL2(dim)
        idx.add(chunk_embs)
        chunk_indices.append(idx)

    return metadata, topic_index, chunk_indices


permanent_metadata, permanent_topic_index, permanent_chunk_indices = init_store(PERMANENT_METADATA_FILE_PATH)

temp_metadata, temp_topic_index, temp_chunk_indices = init_store(TEMP_METADATA_FILE_PATH)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)