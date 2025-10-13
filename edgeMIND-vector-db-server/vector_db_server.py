from flask import Flask, request, jsonify
import faiss
import json
import logging
from sentence_transformers import SentenceTransformer
import numpy as np
import os

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

embedding_function = SentenceTransformer('all-mpnet-base-v2')

PERMANENT_METADATA_FILE_PATH = 'permanent_metadata.json'
TEMP_METADATA_FILE_PATH = 'temp_metadata.json'

# PERMANENT_INDEX_FILE_PATH = 'multimodal_faiss_index.index'
# TEMP_INDEX_FILE_PATH  = 'temp_index.index'

data_from_last_uploaded_file = []

def load_metadata2(file_path):
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


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

    data = request.json
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

    # Handle new topics
    for topic in new_topics:
        topic_name = topic["topic"]
        chunks = topic["chunks"]

        clean_chunks = [{"text": c["text"]} for c in chunks]

        metadata.append({"topic": topic_name, "chunks": clean_chunks})

        # Topic embedding
        topic_embedding = embedding_function.encode([topic_name], convert_to_numpy=True).astype("float32")

        if topic_index is None:
            dim = topic_embedding.shape[-1]
            topic_index = faiss.IndexFlatL2(dim)
        topic_index.add(topic_embedding)

        # Chunk embedding
        chunk_texts = [c["text"] for c in chunks]
        chunk_embs = embedding_function.encode(chunk_texts, convert_to_numpy=True).astype("float32")

        dim = chunk_embs.shape[1]
        chunk_index = faiss.IndexFlatL2(dim)
        chunk_index.add(chunk_embs)
        chunk_indices.append(chunk_index)

        for c in chunks:
            data_from_last_uploaded_file.append(c["text"])
    
    # Handle existing topics
    for topic in existing_topics:
        topic_indx = topic["topic_indx"]
        chunks = topic["chunks"]

        if 0 <= topic_indx < len(metadata):
            clean_chunks = [{"text": c["text"]} for c in chunks]
            metadata[topic_indx]["chunks"].extend(clean_chunks)

            # Chunk embeddings
            new_texts = [c["text"] for c in chunks]
            new_embs = embedding_function.encode(new_texts, convert_to_numpy=True).astype("float32")

            if chunk_indices[topic_indx] is None:
                dim = new_embs.shape[1]
                chunk_indices[topic_indx] = faiss.IndexFlatL2(dim)
            chunk_indices[topic_indx].add(new_embs)

            for c in chunks:
                data_from_last_uploaded_file.append(c["text"])
        else:
            return jsonify({
                "status": "error",
                "message": f"Invalid topic index {topic_indx}"
            }), 400

    # Save metadata
    save_metadata(metadata, metadata_path)

    # Update globals so in-memory state matches
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

        logging.info(f"Received question: {question}")

        # Encode the query
        query_emb = embedding_function.encode([question]).astype("float32")

        threshold = 1.0

        permanent_results = []
        if permanent_topic_index is not None and permanent_metadata:
            # Find the best matching permanent topic
            _, topic_indices = permanent_topic_index.search(query_emb, k=1)
            best_topic_idx = int(topic_indices[0][0])

            # Search inside the chosen permanent topic's chunks
            chunk_distances, chunk_idxs = permanent_chunk_indices[best_topic_idx].search(query_emb, k=3)

            for i, idx in enumerate(chunk_idxs[0]):

                logging.info(f"Chunk: {permanent_metadata[best_topic_idx]["chunks"][idx]["text"]}")
                logging.info(f"Distance: {chunk_distances[0][i] }")
                logging.info("")

                             
                if idx == -1 or chunk_distances[0][i] > threshold:
                    continue
                try:
                    permanent_results.append(permanent_metadata[best_topic_idx]["chunks"][idx]["text"])
                except Exception as e:
                    logging.error(f"Failed to fetch permanent chunk idx={idx}: {e}")

        temp_results = []
        if temp_topic_index is not None and temp_metadata:

            # Find the best matching temp topic
            _, topic_indices = temp_topic_index.search(query_emb, k=1)
            best_topic_idx = int(topic_indices[0][0])

            # Search inside the chosen temp topic's chunks
            chunk_distances, chunk_idxs = temp_chunk_indices[best_topic_idx].search(query_emb, k=3)

            for i, idx in enumerate(chunk_idxs[0]):
                if idx == -1 or chunk_distances[0][i] > threshold:
                    continue
                try:
                    temp_results.append(temp_metadata[best_topic_idx]["chunks"][idx]["text"])
                except Exception as e:
                    logging.error(f"Failed to fetch temp chunk idx={idx}: {e}")

        payload = {
            "permanent_chunks": permanent_results,
            "temp_chunks": temp_results
        }

        logging.info(f"Payload: {payload}")

        return jsonify(payload), 200
    
    except Exception as e:
        logging.error(f"Error in search: {e}")
        return jsonify({"message": str(e)}), 500
        

def init_store(metadata_path):
    """
    Initialize metadata list, topic index, and chunk indices
    from given metadata (topics + chunks).
    """
    metadata = load_metadata2(metadata_path)

    if not metadata:
        return [], None, []

    # Topics 
    topic_names = [entry["topic"] for entry in metadata]
    if not topic_names:
        return metadata, None, []

    # Compute topic embeddings in one batch
    topic_embeddings = embedding_function.encode(
        topic_names, convert_to_numpy=True
    ).astype("float32")

    dim = topic_embeddings.shape[1]
    topic_index = faiss.IndexFlatL2(dim)
    topic_index.add(topic_embeddings)

    # Chunks 
    chunk_indices = []
    for topic in metadata:
        chunks = topic.get("chunks", [])
        if not chunks:
            chunk_indices.append(None)
            continue

        # Collect all texts in this topic
        chunk_texts = [c["text"] for c in chunks]

        # Compute embeddings
        chunk_embs = embedding_function.encode(
            chunk_texts, convert_to_numpy=True
        ).astype("float32")

        dim = chunk_embs.shape[1]
        chunk_index = faiss.IndexFlatL2(dim)
        chunk_index.add(chunk_embs)
        chunk_indices.append(chunk_index)

    return metadata, topic_index, chunk_indices

permanent_metadata, permanent_topic_index, permanent_chunk_indices = init_store(PERMANENT_METADATA_FILE_PATH)

temp_metadata, temp_topic_index, temp_chunk_indices = init_store(TEMP_METADATA_FILE_PATH)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)