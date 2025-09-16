from flask import Flask, request, jsonify
import faiss
import json
import logging
from sentence_transformers import SentenceTransformer
import numpy as np
import os
import base64

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

app = Flask(__name__)

embedding_function = SentenceTransformer('all-mpnet-base-v2')

@app.route('/fetch_topics', methods=['GET'])
def fetch_data():
    main_metadata_file_path = 'topic_metadata_with_names.txt'

    try:
        topics = set()
        with open(main_metadata_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    topic = entry.get("topic")
                    if topic:
                        topics.add(topic)
                except json.JSONDecodeError:
                    continue

        unique_topics = sorted(topics)

        return jsonify({
            "status": "success",
            "topics": unique_topics
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



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


def store_data(metadata, metadata_file_path, index_file_path, file_type=None):

    if file_type == "image":
        new_image_id = get_next_image_id(metadata_file_path)
        for entry in metadata:
            entry["image_id"] = new_image_id
        logging.info(f"Assigned image_id={new_image_id} to {len(metadata)} entries")

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


@app.route('/store-to-tmp', methods=['POST'])
def store_to_tmp():
    temp_index_file_path = 'temp_faiss_index.index'
    temp_metadata_file_path = 'temp_metadata.txt'

    try:
        data = request.json
        metadata = data["metadata"]
        file_type = data.get("file_type")

        new_image_id = None
        for entry in metadata:
            if file_type == "image":
                # Only generate once per batch of image entries
                if new_image_id is None:
                    new_image_id = get_next_image_id(temp_metadata_file_path)
                entry["image_id"] = new_image_id 

        msg = store_data(metadata, temp_metadata_file_path, temp_index_file_path, file_type)

        return jsonify({"status": "success", "message": msg})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    

def get_next_image_id(metadata_file_path: str) -> int:
    max_id = 0
    if os.path.exists(metadata_file_path):
        with open(metadata_file_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if "image_id" in entry and isinstance(entry["image_id"], int):
                        max_id = max(max_id, entry["image_id"])
                except json.JSONDecodeError:
                    continue
    return max_id + 1



@app.route('/store', methods=['POST'])
def store_to_db():
    main_index_file_path = 'multimodal_faiss_index.index'
    main_metadata_file_path = 'topic_metadata_with_names.txt'

    try:
        data = request.json
        metadata = data["metadata"]
        file_type = data.get("file_type")
        msg = store_data(metadata, main_metadata_file_path, main_index_file_path, file_type)
        
        return jsonify({"status": "success", "message": msg})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    


# @app.route('/search', methods=['POST'])
# def search_database():
#     main_index_file_path = 'multimodal_faiss_index.index'
#     main_metadata_file_path = 'topic_metadata_with_names.txt'

#     try:
#         request_data = request.get_json()
#         question = request_data['question']
#         logging.info(f"Received: {question}")

#         #results = f"Your question was: {question}"

#         # Load faiss index, metadata and embedding function every time a new client is connected
#         index = load_faiss_index(main_index_file_path)
#         metadata = load_metadata(main_metadata_file_path)
#         #embedding_function = load_embedding_function()

#         results = search_faiss_index(question, index, metadata, embedding_function)
#         logging.info("Result from searching the faiss index:\n", results)

#         #result_list = [result['text'] for result in results]
#         #result_string = str(result_list)
#         #logging.info(f"The result as a string: {result_string}\n")

#         result_as_json = json.dumps(str(results))
#         #result_as_json = json.dumps(result_string)

#         return jsonify({"status": "success", "message": result_as_json})

#     except Exception as e:
#         return jsonify({"status": "error", "message": str(e)}), 500




@app.route('/search', methods=['POST'])
def search_database():
    main_index_file_path = 'multimodal_faiss_index.index'
    main_metadata_file_path = 'topic_metadata_with_names.txt'



    try:
        request_data = request.get_json()
        question = request_data['question']
        logging.info(f"Received: {question}")

        #results = f"Your question was: {question}"


        

        # Load faiss index, metadata and embedding function every time a new client is connected
        index = load_faiss_index(main_index_file_path)



        metadata = load_metadata(main_metadata_file_path)
        #embedding_function = load_embedding_function()



        results = search_faiss_index(question, index, metadata, embedding_function)


        logging.info(f"Result from searching the faiss index: {results}")

        #result_list = [result['text'] for result in results]
        #result_string = str(result_list)
        #logging.info(f"The result as a string: {result_string}\n")

        result_as_json = json.dumps(str(results))
        #result_as_json = json.dumps(result_string)

        return jsonify({"status": "success", "message": result_as_json})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/search_latest_image', methods=['POST'])
def search_latest_image():
    metadata_file_path = 'topic_metadata_with_names.txt'

    if not os.path.exists(metadata_file_path):
        return jsonify({"status": "error", "message": "No metadata file"}), 404

    with open(metadata_file_path, 'r', encoding='utf-8') as f:
        metadata = [json.loads(line.strip()) for line in f if line.strip()]

    # Find the largest image_id
    max_image_id = max(
        (entry.get("image_id", -1) for entry in metadata if "image_id" in entry),
        default=-1
    )
    if max_image_id == -1:
        return jsonify({"status": "error", "message": "No image_id found"}), 404

    latest_chunks = [entry for entry in metadata if entry.get("image_id") == max_image_id]

    # Convert chunks into a string
    message = "\n".join(entry["text"] for entry in latest_chunks)

    return jsonify({
        "status": "ok",
        "message": message
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)