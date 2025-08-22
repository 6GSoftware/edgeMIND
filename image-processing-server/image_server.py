from flask import Flask, request
import os
import threading
import socket
import time
import logging
import requests
import multiprocessing as mp

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

from image_processing import process_image_files

# HOST = "situational_awareness_server" # For setup before K3s
HOST = "edgemind-situational-awareness-server" # For K3s setup

TAG = "image_service: "

MONITOR_URL = "http://host.docker.internal:5006/status"

BASE_DIRECTORY = "./"
IMAGE_DIRECTORY = os.path.join(BASE_DIRECTORY, "Pictures/")
os.makedirs(IMAGE_DIRECTORY, exist_ok=True)

app = Flask(__name__)


def process_file(**kwargs):
    file_name = kwargs.get('file_name')

    # Extract text from the file and save the exracted text to appropriate file.
    logging.info(f"{TAG} Processing image file...")
    processed_file_content = process_image_files(file_name)
    
    # Example data for debugging
#    processed_file_content = """Response for picture1234.jpg:
#- The image shows a hand holding a white mug with a black floral pattern.
#- The mug has a handle on the right side.
#- The background is a plain, light-colored wall.
#- There is a shadow cast by the mug on the wall.
#- The hand appears to be that of an adult.
#- The mug is being held in a way that suggests it is being presented or shown off.
#- There are no other objects or people visible in the image."""

    '''try:
        res = requests.post(MONITOR_URL, json={
            "state": "stop",
            "service-name": "edgemind-image-service"
        }, timeout=2)
        logging.info(f"Started monitoring: {res.json()}")
    except Exception as e:
        logging.warning(f"Monitoring service not available: {e}")'''

    logging.info(f"{TAG} The content of the processed file is now: {processed_file_content}")
    
    # Process step 3: Process the data that was extracted from the uploaded file:
    # tokenize sentences and save them to appropriate file
    send_to_extracted_text_processing(processed_file_content)
    #processed_file_content = process_extracted_texts(processed_file_content)
    logging.info(f"{TAG} Text tokenized, embeddings created and saved to appropriate file")

    logging.info(f"{TAG} The content of the processed file is now: {processed_file_content}")
    
    # Process step 4:
    #vectorize_and_save_to_vector_db()
    #logging.info(f"{TAG} The texts have been vectorized and saved to the faiss index")
    
    logging.info(f"{TAG} Process complete!\n")


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

    return 'File uploaded and saved successfully'


@app.route('/upload_image', methods=['POST'])
def upload_file():
    """Handle http POST request from the client and receive a file."""

    '''start_time = time.time()
    logging.info("\nSTART TIME: " + str(start_time) + "\n")

    try:
        res = requests.post(MONITOR_URL, json={
            "state": "start",
            "service-name": "edgemind-image-service"
        })
        logging.info("Started monitoring:", res.json())
    except Exception as e:
        logging.info("Failed to start monitoring:", e)'''

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
    


#def send_to_extracted_text_processing(processed_file_content):
#
#    try:
#        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#            s.connect((HOST, PORT))
#            s.sendall(processed_file_content.encode('utf-8'))
#            s.shutdown(socket.SHUT_WR)
#            response = s.recv(1024)
#            logging.info(f"{TAG}Response from the processor: {response.decode('utf-8')}")
#    except Exception as e:
#        logging.info(f"{TAG}Connection failed: {e}")


def send_to_extracted_text_processing(processed_file_content):
    try:
        # url = "http://situational_awareness_server:6501/process_extracted_texts" # For setup before K3s
        url = "http://situational-awareness:6501/process_extracted_texts" # For K3s setup

        payload = {"data": processed_file_content}

        response = requests.post(url, json=payload)

        if response.ok:
            logging.info(f"{TAG} Response from the processor: {response.json()}")
        else:
            logging.error(f"{TAG} Failed to send data: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"{TAG} Connection failed: {e}")


#if __name__ == "__main__":
#    mp.set_start_method("spawn", force=True)
#    app.run(host="0.0.0.0", port=5002)

#if __name__ == '__main__':
#    app.run(host="0.0.0.0", port=5002, threaded=True)