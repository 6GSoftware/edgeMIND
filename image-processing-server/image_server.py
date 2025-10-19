from flask import Flask, request
import os
import threading
import socket
import time
import logging
import requests
import multiprocessing as mp
import uuid
import pyRAPL

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

from image_processing import process_image_files

pyRAPL.setup()

HOST = "situational_awareness_server"

TAG = "image_service: "

MEASURE_URL = "http://127.0.0.1:5030/measure"

SA_URL = "http://127.0.0.1:6501/process_extracted_texts"
# SA_URL = "http://situational_awareness_server:6501/process_extracted_texts"

BASE_DIRECTORY = "./"
IMAGE_DIRECTORY = os.path.join(BASE_DIRECTORY, "Pictures/")
os.makedirs(IMAGE_DIRECTORY, exist_ok=True)

app = Flask(__name__)

def process_file(**kwargs):
    file_name = kwargs.get('file_name')
    start_time = kwargs.get('start_time')
    run_id = kwargs.get('run_id')
    meter = kwargs.get('meter')


    # Extract text from the file and save the exracted text to appropriate file.
    logging.info(f"{TAG} Processing image file...")
    # processed_file_content = process_image_files(file_name)
    
    # Example data for debugging
    processed_file_content = """Response for picture1234.jpg:
    - The image shows a hand holding a white mug with a black floral pattern.
    - The mug has a handle on the right side.
    - Tällastäpä tuolla joukossa ei oo sitten ollenkaan.
    - There is a shadow cast by the mug on the wall.
    - Eika tammosta.
    - The mug is being held in a way that suggests it is being presented or shown off.
    - There are no other objects or people visible in the image."""

    logging.info(f"{TAG} The content of the processed file is now: {processed_file_content}")

    threading.Thread(target=send_to_extracted_text_processing, args=(processed_file_content, run_id)).start()

    # Send timing to the measuring server
    report_to_measuring_server(start_time, run_id, meter)

    logging.info(f"{TAG} Data sent to Situational Awareness and measuring server!\n")


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
    start_time = time.time()
    run_id = str(uuid.uuid4())

    meter = pyRAPL.Measurement(f"image_service_{run_id}")
    meter.begin()

    if 'file' not in request.files:
        return {'message': 'No file part'}, 400

    file = request.files['file']
    if file.filename == '':
        return {'message': 'No selected file'}, 400

    file_name = file.filename

    # Save the uploaded file
    response_message = save_file(file_name, file)

    # Process the file in another thread
    # thread = threading.Thread(target=process_file, kwargs={
    #                 'file_name': file_name,
    #                 'start_time': start_time,
    #                 'run_id': run_id
    #                 })
    # thread.start()

    process_file(file_name=file_name, start_time=start_time, run_id=run_id, meter=meter)

    # Send a response message to the mobile app
    return {'message': response_message}, 200


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


def report_to_measuring_server(start_time, run_id, meter):
    """Report total processing duration to the measurement server."""
    try:
        end_time = time.time()
        meter.end()
        duration = end_time - start_time

        energy_pkg = sum(meter.result.pkg) / 1_000_000
        energy_dram = sum(meter.result.dram) / 1_000_000
        energy_joules = energy_pkg + energy_dram

        payload = {
            "run_id": run_id,
            "service": "image_service",
            "duration": duration,
            "start_time": start_time,
            "end_time": end_time,
            "energy_joules": energy_joules
        }

        response = requests.post(MEASURE_URL, json=payload)

        if response.ok:
            logging.info(f"{TAG} Measurement reported successfully: {response.json()}")
        else:
            logging.error(f"{TAG} Failed to report measurement: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"{TAG} Could not contact measuring server: {e}")

#if __name__ == "__main__":
#    mp.set_start_method("spawn", force=True)
#    app.run(host="0.0.0.0", port=5002)

if __name__ == '__main__':
   app.run(host="0.0.0.0", port=5002, threaded=True)