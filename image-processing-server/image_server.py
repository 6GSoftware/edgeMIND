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
import psutil

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
    stop_event = kwargs.get('stop_event')
    monitor_thread = kwargs.get('monitor_thread')
    stats = kwargs.get('stats')

    # Extract text from the file and save the exracted text to appropriate file.
    logging.info(f"{TAG} Processing image file...")
    processed_file_content = process_image_files(file_name)
    
    # Example data for debugging
    # processed_file_content = """Response for picture1234.jpg:
    # - The image shows a hand holding a white mug with a black floral pattern.
    # - The mug has a handle on the right side.
    # - Tällastäpä tuolla joukossa ei oo sitten ollenkaan.
    # - There is a shadow cast by the mug on the wall.
    # - Eika tammosta.
    # - The mug is being held in a way that suggests it is being presented or shown off.
    # - There are no other objects or people visible in the image."""

    logging.info(f"{TAG} The content of the processed file is now: {processed_file_content}")

    # --- STOP CPU/memory monitoring ---
    stop_event.set()
    monitor_thread.join()

    # --- Calculate average CPU/memory usage ---
    avg_cpu = sum(stats["cpu"]) / len(stats["cpu"]) if stats["cpu"] else 0
    avg_mem = sum(stats["mem"]) / len(stats["mem"]) if stats["mem"] else 0
    

    time.sleep(1)

    print(f"{TAG} Average CPU usage: {avg_cpu:.2f}% | Average Memory usage: {avg_mem:.2f}%")

    threading.Thread(target=send_to_extracted_text_processing, args=(processed_file_content, run_id)).start()

    # Send timing to the measuring server
    report_to_measuring_server(start_time, run_id, meter, avg_cpu, avg_mem)

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

    # --- Start energy measurement ---
    meter = pyRAPL.Measurement(f"image_service_{run_id}")
    meter.begin()

    # --- Start CPU/memory monitoring thread ---
    stop_event = threading.Event()
    stats = {"cpu": [], "mem": []}
    monitor_thread = threading.Thread(target=monitor_resources, args=(stop_event, stats))
    monitor_thread.start()

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

    process_file(file_name=file_name, start_time=start_time, run_id=run_id, meter=meter,
                 stop_event=stop_event,monitor_thread=monitor_thread,stats=stats)

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


def report_to_measuring_server(start_time, run_id, meter, avg_cpu, avg_mem):
    """Report total processing duration to the measurement server."""
    try:
        end_time = time.time()
        meter.end()
        duration = end_time - start_time

        energy_pkg = sum(meter.result.pkg) / 1_000_000
        energy_dram = sum(meter.result.dram or []) / 1_000_000
        energy_joules = energy_pkg + energy_dram

        payload = {
            "run_id": run_id,
            "service": "image_service",
            "duration": duration,
            "start_time": start_time,
            "end_time": end_time,
            "energy_joules": energy_joules,
            "avg_cpu": avg_cpu,
            "avg_mem": avg_mem
        }

        response = requests.post(MEASURE_URL, json=payload)

        if response.ok:
            logging.info(f"{TAG} Measurement reported successfully: {response.json()}")
        else:
            logging.error(f"{TAG} Failed to report measurement: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"{TAG} Could not contact measuring server: {e}")


# def monitor_resources(stop_event, stats):
#     """Monitor CPU and memory usage every 0.2 s until stop_event is set."""
#     while not stop_event.is_set():
#         stats["cpu"].append(psutil.cpu_percent(interval=None))
#         stats["mem"].append(psutil.virtual_memory().percent)
#         time.sleep(0.2)

def monitor_resources(stop_event, stats):
    """Monitor this process's CPU and memory usage every 0.2 s until stop_event is set."""
    process = psutil.Process(os.getpid())
    process.cpu_percent(interval=None)  # initial sample

    while not stop_event.is_set():
        # prosessin CPU-käyttö kaikilla ytimillä yhteensä (sama mittakaava kuin htop)
        cpu_usage = process.cpu_percent(interval=None)
        mem_usage = process.memory_percent()  # prosessin oma muistinkäyttö %
        stats["cpu"].append(cpu_usage)
        stats["mem"].append(mem_usage)
        time.sleep(0.2)


#if __name__ == "__main__":
#    mp.set_start_method("spawn", force=True)
#    app.run(host="0.0.0.0", port=5002)

if __name__ == '__main__':
   app.run(host="0.0.0.0", port=5002, threaded=True)