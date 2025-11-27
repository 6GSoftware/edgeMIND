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
import sys
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = Flask(__name__)

from image_processing import process_image_files
from save_measurements import save

TAG = "image_service: "

SA_MONITOR_URL = "http://situational-awareness:6501/start_monitoring"
SA_URL = "http://situational-awareness:6501/process_extracted_texts"

BASE_DIRECTORY = "./"
IMAGE_DIRECTORY = os.path.join(BASE_DIRECTORY, "Pictures/")
os.makedirs(IMAGE_DIRECTORY, exist_ok=True)


def process_file(**kwargs):
    global cpu_values, ram_values, monitoring_ram, monitoring_cpu

    file_name = kwargs.get('file_name')
    start_time = kwargs.get('start_time')
    run_id = kwargs.get('run_id')
    meter = kwargs.get('meter')
    monitor_thread = kwargs.get('monitor_thread')

    # Extract text from the file and save the exracted text to appropriate file.
    logging.info(f"{TAG} Processing image file...")
    processed_file_content = process_image_files(file_name)

    # Example data for debugging
    # processed_file_content = """Response for picture1234.jpg:
    # - The image shows a hand holding a white mug with a black floral pattern.
    # - Juuh elikkä joo eli juu.
    # - Tällastäpä tuolla joukossa ei oo sitten ollenkaan.
    # - There is a shadow cast by the mug on the wall.
    # - Eika tammosta.
    # - The mug is being held in a way that suggests it is being presented or shown off.
    # - There are no other objects or people visible in the image."""

    # total = 0.0
    # for i in range(30_000_000):
    #     total += i ** 0.5

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

    # monitor_thread.join()

    end_time = time.time()
    meter.end()
    duration = end_time - start_time

    monitoring_ram = False
    monitoring_cpu = False

    energy_pkg = sum(meter.result.pkg) / 1_000_000
    energy_dram = sum(meter.result.dram or []) / 1_000_000
    energy_joules = energy_pkg + energy_dram

    print("SA RESULTS: ")
    print(sa_result)

    save(sa_result, cpu_values, ram_values, energy_joules, duration, run_id)

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

    return 'File uploaded and saved successfully!!'


@app.route('/upload_image', methods=['POST'])
def upload_file():
    global monitoring_ram, monitoring_cpu

    start_time = time.time()
    run_id = str(uuid.uuid4())

    # --- Start energy measurement ---
    meter = pyRAPL.Measurement(f"image_service_{run_id}")
    meter.begin()

    monitoring_ram = True
    monitoring_cpu = True

    t = threading.Thread(target=monitor_usage, args=(0,), daemon=True)
    t.start()

    start_sa_monitoring_SA()

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

    process_file(file_name=file_name, start_time=start_time, run_id=run_id, meter=meter, monitor_thread=t)

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

pyRAPL.setup()

monitoring_cpu = False
monitoring_ram = False

cpu_values = []
ram_values = []

try:
    with open("/data/memory_usage_gb.txt") as f:
        mem_usage = float(f.read().strip())
        print(f"Memory usage: {mem_usage}")
except Exception as e:
    mem_usage = None
    print("Failed to read memory usage: ", e)


@app.route("/health")
def health():
    return {"status": "ok"}, 200


def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(power_labels) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"


def monitor_usage(interval=0):
    global cpu_values, ram_values
    global monitoring_ram, monitoring_cpu

    cpu_values.clear()
    ram_values.clear()

    last_print_time = time.time()
    cpu = 0.0

    while monitoring_ram or monitoring_cpu:
        if monitoring_ram:
            used_mem = fetch_used_memory()
            ram_values.append(used_mem)
            # mem = psutil.virtual_memory()
            # used_mem = mem.total - mem.available - mem_usage
            # ram_values.append(used_mem)
        else:
            used_mem = None

        if monitoring_cpu:
            cpu = psutil.cpu_percent(interval=0)
            cpu_values.append(cpu)

        print(f"used_mem:{used_mem}")
        print(f"CPU:{cpu}")


        time.sleep(interval)


def fetch_used_memory():
    cmd = (
        "crictl --config=/dev/null "
        "--runtime-endpoint unix:///run/k3s/containerd/containerd.sock "
        "stats --output=table | "
        "awk 'NR>1 && $4 != \"\" {"
        "val=$4;"
        "gsub(/[^0-9.]/, \"\", val);"
        "if ($4 ~ /KiB/) sum+=val*1024;"
        "else if ($4 ~ /MiB|MB/) sum+=val*1024*1024;"
        "else if ($4 ~ /GiB|GB/) sum+=val*1024*1024*1024;"
        "} END { printf \"%.2f\", sum/1024/1024; }'"
    )

    try:
        output = subprocess.check_output(cmd, shell=True, text=True, timeout=5).strip()
        if not output:
            return 0.0
        return float(output)
    except subprocess.TimeoutExpired:
        print("crictl stats timeout – skipped this cycle")
        return 0.0
    except subprocess.CalledProcessError as e:
        print(f"crictl stats failed: {e}")
        return 0.0
    except ValueError:
        print(f"Could not parse memory output: {output!r}")
        return 0.0


def start_sa_monitoring_SA():
    try:
        response = requests.post(SA_MONITOR_URL)
        response.raise_for_status()
        logging.info("Successfully started CPU/RAM monitoring in SA service.")
    except Exception as e:
        logging.error(f"Failed to start monitoring in SA service: {e}")



if __name__ == '__main__':
    # mp.set_start_method("spawn", force=True)
    # monitoring_cpu = True
    # monitoring_ram = True
    # threading.Thread(target=monitor_usage, args=(3.0,), daemon=True).start()
    app.run(host="0.0.0.0", port=5002, threaded=True)
