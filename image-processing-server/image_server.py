from flask import Flask, request, jsonify
import os
import time
import logging
import requests
import uuid
import sys
from PIL import Image
from multiprocessing import Process

IN_K3S = os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token")

POD_NAME = os.getenv("POD_NAME", "unknown-pod")
NODE_NAME = os.getenv("NODE_NAME", "unknown-node")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = Flask(__name__)

from image_processing import process_image_files

TAG = "image_service: "

SA_URL = "http://situational-awareness:6501/process_extracted_texts"

BASE_DIRECTORY = "./"
IMAGE_DIRECTORY = os.path.join(BASE_DIRECTORY, "Pictures/")
os.makedirs(IMAGE_DIRECTORY, exist_ok=True)


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route('/upload_image', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return {'message': 'No file part'}, 400

    file = request.files['file']
    if file.filename == '':
        return {'message': 'No selected file'}, 400

    file_name = file.filename

    # Save the uploaded file
    response_message = save_file(file_name, file)

    p = Process(
        target=process_file,
        kwargs={
            "file_name": file_name,
            "start_time": time.time(),
            "run_id": str(uuid.uuid4())
        }
    )
    p.start()

    # Send a response message to the mobile app
    return jsonify({
        "pod": POD_NAME,
        "node": NODE_NAME,
        "msg": "Image uploaded!"
    }), 200


def process_file(**kwargs):
    file_name = kwargs.get('file_name')

    # Extract text from the file and save the exracted text to appropriate file.
    logging.info(f"{TAG} Processing image file...")
    processed_file_content = process_image_files(filename=file_name)

    logging.info(f"{TAG} The content of the processed file is now: {processed_file_content}")

    payload = {"data": processed_file_content}

    try:
        logging.info(f"{TAG} Sending extracted text to SA service at {SA_URL}...")
        response = requests.post(SA_URL, json=payload)
        response.raise_for_status()
        sa_result = response.json()

        logging.info(f"{TAG} Response from SA service: {sa_result}")

    except Exception as e:
        logging.error(f"{TAG} Failed to communicate with SA service: {e}")
        sa_result = {}

    print("SA RESULTS: ")
    print(sa_result)

    logging.info(f"{TAG} Data sent to Situational Awareness and measuring server!\n")

    return


@app.route('/process_user_image', methods=['POST'])
def process_user_image():

    #caller = request.form.get("caller")
    image_file = request.files.get("file")

    generated_name = f"img_{uuid.uuid4().hex[:8]}"

    pil_image = Image.open(image_file.stream)

    processed_file_content = process_image_files(image=pil_image, filename=generated_name)

    # Send a response message to the mobile app
    return jsonify(processed_file_content), 200


def save_file(file_name, file):
    """Save the uploaded file to an appropriate directory"""

    # Determine file type and set the appropriate directory
    directory = IMAGE_DIRECTORY

    if directory is None:
        logging.info("Unknown file type. Skipping file.")
        return 'Unknown filetype'

    # Create full file path
    file_path = os.path.join(directory, file_name)

    # Save received file to appropriate folder
    file.save(f"{file_path}")
    logging.info(f"{TAG} File saved successfully at: {file_path}")

    return 'File uploaded and saved successfully!!'


def send_to_extracted_text_processing(processed_file_content, run_id):
    try:

        payload = {"data": processed_file_content,
                   "run_id": run_id}

        response = requests.post(SA_URL, json=payload)

        if response.ok:
            logging.info(f"{TAG} Response from the processor: {response.json()}")
        else:
            logging.error(f"{TAG} Failed to send data: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"{TAG} Connection failed: {e}")


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5002, threaded=True)