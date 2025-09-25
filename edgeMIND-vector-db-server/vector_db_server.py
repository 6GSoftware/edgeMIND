from flask import Flask, request, jsonify
import faiss
import json
import logging
from sentence_transformers import SentenceTransformer
import numpy as np
import os

logger = logging.getLogger(__name__)

app = Flask(__name__)

embedding_function = SentenceTransformer('all-mpnet-base-v2')

PERMANENT_METADATA_FILE_PATH = 'topic_metadata_with_names.json'
PERMANENT_INDEX_FILE_PATH = 'multimodal_faiss_index.index'

TEMP_METADATA_FILE_PATH = 'temp_metadata.json'
TEMP_INDEX_FILE_PATH  = 'temp_index.index'

data_from_last_uploaded_file = []

def load_metadata(file_path):
    """Load metadata from a file."""
    metadata = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            metadata.append(json.loads(line.strip()))  # Parse JSON lines
    return metadata


def load_metadata2(file_path):
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_faiss_index(index_file_path):
    if not os.path.exists(index_file_path) or os.path.getsize(index_file_path) == 0:
        return None
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
            #"topic": result_entry["topic"],
            "timestamp": result_entry["timestamp"],
            #"distance": distances[0][i]
        })
    
    return results


def search_faiss_index2(query_text, index, metadata, k=1):
    """Search FAISS index for the closest topic."""

    # Do the actual search to the faiss index
    query_embedding = embedding_function.encode([query_text]).astype('float32')  # Generate query embedding
    distances, indices = index.search(query_embedding, k)  # Retrieve top-k results
    
    results = []
    for i, idx in enumerate(indices[0]):
        if idx == -1:
            continue

        topic_entry = metadata[idx]
        chunks = topic_entry.get("chunks", [])

        results.append({
            "topic": topic_entry["topic"],
            "chunks": chunks,
            # "distance": float(distances[0][i])
        })

    return results


def store_data(metadata, metadata_file_path, index_file_path):
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

    return msg


@app.route('/store_to_tmp', methods=['POST'])
def store_to_tmp():
    temp_index_file_path = 'temp_faiss_index.index'
    temp_metadata_file_path = 'temp_metadata.txt'

    logging.info("storing data to temporary database...")

    try:
        data = request.json
        metadata = data["metadata"]
        metadata = [metadata]
        msg = store_data(metadata, temp_metadata_file_path, temp_index_file_path)

        logging.info("data successfully stored!")

        return jsonify({"status": "success", "message": msg})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/store', methods=['POST'])
def store_to_db():

    try:
        data = request.json
        metadata = data["metadata"]
        msg = store_data(metadata, PERMANENT_METADATA_FILE_PATH, PERMANENT_INDEX_FILE_PATH)
        
        return jsonify({"status": "success", "message": msg})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/store2', methods=['POST'])
def store():
    global data_from_last_uploaded_file
    data_from_last_uploaded_file = []

    metadata = load_metadata2(PERMANENT_METADATA_FILE_PATH)
    index = load_faiss_index(PERMANENT_INDEX_FILE_PATH)

    data = request.json
    new_topics = data.get("new_topics", [])
    existing_topics = data.get("existing_topics", [])

    # Handle new topics
    for topic in new_topics:
        topic_name = topic["topic"]
        topic_embedding = np.array(topic["topic_embeddings"], dtype="float32").reshape(1, -1)
        chunks = topic["chunks"]

        metadata.append({"topic": topic_name, "chunks": chunks})

        for c in chunks:
            if "text" in c:
                data_from_last_uploaded_file.append(c["text"])

        if index is None:
            dim = topic_embedding.shape[-1]
            index = faiss.IndexFlatL2(dim)
        index.add(topic_embedding)
    
    # Handle existing topics
    for topic in existing_topics:
        topic_indx = topic["topic_indx"]
        chunks = topic["chunks"]

        if 0 <= topic_indx < len(metadata):
            metadata[topic_indx]["chunks"].extend(chunks)

            for c in chunks:
                if "text" in c:
                    data_from_last_uploaded_file.append(c["text"])
        else:
            return jsonify({
                "status": "error",
                "message": f"Invalid topic index {topic_indx}"
            }), 400

    # Save metadata + index to disk
    save_metadata(metadata, PERMANENT_METADATA_FILE_PATH)
    if index is not None:
        faiss.write_index(index, PERMANENT_INDEX_FILE_PATH)

    return jsonify({"status": "success", "message": "Data stored"})
    

@app.route('/search', methods=['POST'])
def search_database():
    try:
        request_data = request.get_json()
        question = request_data['question']
        logging.info(f"Received: {question}")

        #results = f"Your question was: {question}"

        # Load faiss index, metadata and embedding function every time a new client is connected
        index = load_faiss_index(PERMANENT_INDEX_FILE_PATH)
        metadata = load_metadata(PERMANENT_METADATA_FILE_PATH)
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


@app.route('/search2', methods=['POST'])
def search_database2():
    try:
        request_data = request.get_json()
        question = request_data['question']
        logging.info(f"Received: {question}")

        #results = f"Your question was: {question}"

        # Load faiss index, metadata and embedding function every time a new client is connected
        index = load_faiss_index(PERMANENT_INDEX_FILE_PATH)
        metadata = load_metadata2(PERMANENT_METADATA_FILE_PATH)
        #embedding_function = load_embedding_function()

        results = search_faiss_index2(question, index, metadata, 1)
        logging.info("Result from searching the faiss index:\n", results)

        #result_list = [result['text'] for result in results]
        #result_string = str(result_list)
        #logging.info(f"The result as a string: {result_string}\n")

        result_as_json = json.dumps(str(results))
        #result_as_json = json.dumps(result_string)

        return jsonify({"status": "success", "message": result_as_json})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/get_topics', methods=['GET', 'POST'])
def get_topics():
    if not os.path.exists(PERMANENT_METADATA_FILE_PATH):
        return jsonify({"status": "error", "message": "No metadata file found."}), 400

    try:
        metadata = load_metadata2(PERMANENT_METADATA_FILE_PATH)
        topics = [entry["topic"] for entry in metadata]

        return jsonify({"status": "success", "topics": topics})
    except:
        return jsonify({"status": "error", "message": "Could not read topics"}), 500


def save_metadata(metadata, file_path):
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("[\n")
        for i, obj in enumerate(metadata):
            line = "  " + json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
            if i < len(metadata) - 1:
                line += ","
            f.write(line + "\n")
        f.write("]\n")


@app.route('/get_data_from_last_uploaded_file', methods=['GET', 'POST'])
def get_data_from_last_uploaded_file():
    if data_from_last_uploaded_file:
        return jsonify({"data": data_from_last_uploaded_file}), 200
    else:
        return jsonify({"error": "No files have been uploaded yet!"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)