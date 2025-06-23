from flask import Flask, request
import os
import threading
import socket
import logging
import requests

logging.basicConfig(level=logging.INFO)

from pdf_processing import process_pdf_files

HOST = "situational_awareness_server"
PORT = 6500

TAG = "pdf_service: "

BASE_DIRECTORY = "./"
PDF_DIRECTORY = os.path.join(BASE_DIRECTORY, "pdfs/")
os.makedirs(PDF_DIRECTORY, exist_ok=True)

MONITOR_URL = "http://host.docker.internal:5006/status"

app = Flask(__name__)

def process_file(**kwargs):
    file_name = kwargs.get('file_name')

    # Extract text from the file and save the exracted text to appropriate file.
    logging.info(f"{TAG} Processing PDF file...")
    processed_file_content = process_pdf_files(file_name)

    try:
        res = requests.post(MONITOR_URL, json={
            "state": "stop",
            "service-name": "pdf-service"
        }, timeout=2)
        logging.info(f"Started monitoring: {res.json()}")
    except Exception as e:
        logging.warning(f"Monitoring service not available: {e}")

    send_to_extracted_text_processing(processed_file_content)

def save_file(file_name, file):
    """Save the uploaded file to an appropriate directory"""

    # Determine file type and set the appropriate directory
    directory = PDF_DIRECTORY

    if directory is None:
        logging.info("Unknown file type. Skipping file.")
        return 'Unknown filetype'

    # Create full file path
    file_path = os.path.join(directory, file_name)

    # Save received file to appropriate folder
    file.save(f"{file_path}")
    logging.info(f"{TAG} File saved successfully at: {file_path}")

    return 'File uploaded and saved successfully'


@app.route('/upload_pdf', methods=['POST'])
def upload_file():
    """Handle http POST request from the client and receive a file."""

    try:
        res = requests.post(MONITOR_URL, json={
            "state": "start",
            "service-name": "pdf-service"
        })
        logging.info("Started monitoring:", res.json())
    except Exception as e:
        logging.info("Failed to start monitoring:", e)

    if 'file' not in request.files:
        return {'message': 'No file part'}, 400

    file = request.files['file']
    if file.filename == '':
        return {'message': 'No selected file'}, 400
    
    file_name = file.filename

    # Save the uploaded file
    response_message = save_file(file_name, file)

    # Process the file in another thread
    thread = threading.Thread(target=process_file, kwargs={
                    'file_name': file_name})
    thread.start()

    # Send a response message to the mobile app
    return {'message': response_message}, 200


def send_to_extracted_text_processing(processed_file_content):
    try:
        url = "http://situational_awareness_server:6501/process_extracted_texts"

        payload = {"data": processed_file_content}

        response = requests.post(url, json=payload)

        if response.ok:
            logging.info(f"{TAG} Response from the processor: {response.json()}")
        else:
            logging.error(f"{TAG} Failed to send data: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"{TAG} Connection failed: {e}")


#if __name__ == '__main__':
#    app.run(host="0.0.0.0", port=5004)