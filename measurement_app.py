import docker
import time
from flask import Flask, request
import logging
import threading
#import GPUtil
import psutil
import csv
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

CSV_FILE = "data.csv"

app = Flask(__name__)

monitor_thread = None
stop_event = threading.Event()

save_measurements = True

executing_service = ""
service_PID = -1

def monitor_stats():
    client = docker.from_env()

    while True:

        print("")
        print("------------------------------------")
        print("")

        containers = client.containers.list()
        container_names = [container.name for container in containers]

        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            virtual_mem = psutil.virtual_memory()
            cpu_freq = psutil.cpu_freq()
            cpu_clock_ghz = cpu_freq.current / 1000
            mem_used = virtual_mem.used
            mem_total = virtual_mem.total
            mem_percent = virtual_mem.percent

            mem_used_gb = round(psutil.virtual_memory().used / (1024 ** 3), 2)
            mem_total_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)

            print(f"CPU % (System):   {cpu_percent:.2f}%")
            print(f"Memory (System): {format_bytes(mem_used)} / {format_bytes(mem_total)} ({mem_percent:.2f}%)")

            # GPU
            '''gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                gpu_info_lines = []
                gpu_line = (
                    f"GPU {gpu.id} ({gpu.name}): Load={gpu.load * 100:.2f}%, "
                    f"Mem Used={gpu.memoryUsed / 1024:.2f}GB / {gpu.memoryTotal / 1024:.2f}GB "
                    f"({gpu.memoryUsed / gpu.memoryTotal * 100:.1f}%), "
                    f"{gpu.temperature}°C"
                )
                gpu_info_lines.append(gpu_line)
            else:
                gpu_info_lines = ["GPU: No GPU detected"]

            for gpu_line in gpu_info_lines:
                print(f"{'GPU:':15}{gpu_line}")'''

            if save_measurements:
                timestamp = datetime.now().isoformat(timespec='seconds').replace('T', ' ')

                #gpu_load = gpu.load * 100 if gpus else None
                #gpu_temp = gpu.temperature if gpus else None

                temperatures = get_temperatures()



                file_exists = os.path.isfile(CSV_FILE)
                with open(CSV_FILE, mode="a", newline="") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow([
                            "Timestamp",
                            "PID",
                            "Executing service",
                            #"Running services",
                            "CPU %", "CPU Clock (GHz)",
                            "RAM Used", "RAM Total", "RAM %",
                            #"GPU Load %", "GPU Temp °C",
                            "CPU Temp °C",
                            "SSD Temp °C",
                            "Motherboard Temp °C",
                        ])
                    writer.writerow([
                        timestamp,
                        service_PID,
                        executing_service,
                        #", ".join(container_names),
                        f"{cpu_percent:.1f}", 
                        f"{cpu_clock_ghz:.1f}",
                        f"{mem_used_gb:.1f}",
                        f"{mem_total_gb:.1f}",
                        f"{mem_percent:.1f}",
                        #f"{gpu_load:.1f}" if gpu_load is not None else "N/A",
                        #f"{gpu_temp:.1f}" if gpu_temp is not None else "N/A",
                        f"{temperatures['cpu_temp']:.1f}" if temperatures["cpu_temp"] is not None else "N/A",
                        f"{temperatures['ssd_temp']:.1f}" if temperatures["ssd_temp"] is not None else "N/A",
                        f"{temperatures['mobo_temp']:.1f}" if temperatures["mobo_temp"] is not None else "N/A"
                    ])

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(0.5) 
            

def get_temperatures():
    temps = psutil.sensors_temperatures()
    cpu_temp = None
    ssd_temp = None
    mobo_temp = None

    for chip, entries in temps.items():
        for entry in entries:
            label = entry.label or chip

            # amd cpu
            if chip.lower() == "k10temp" and entry.label and entry.label.strip().lower() == "tctl":
                cpu_temp = entry.current

            # SSD temp
            if not ssd_temp and chip.lower().startswith("nvme") and "composite" in label.lower():
                ssd_temp = entry.current

            # Motherboard temp
            if not mobo_temp:
                if label == "SYSTIN":
                    mobo_temp = entry.current

    if cpu_temp is None:
        coretemps = []
        for chip, entries in temps.items():
            if chip.lower().startswith("coretemp"):
                for entry in entries:
                    if entry.label and entry.label.lower().startswith("core "):
                        coretemps.append(entry.current)
        if coretemps:
            cpu_temp = sum(coretemps) / len(coretemps)

    return {
        "cpu_temp": cpu_temp,
        "ssd_temp": ssd_temp,
        "mobo_temp": mobo_temp
    }


def format_bytes(size, binary=True):
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'] if binary else ['B', 'kB', 'MB', 'GB', 'TB']
    step = 1024 if binary else 1000
    for unit in units:
        if size < step:
            return f"{size:.2f}"
            #return f"{size:.2f}{unit}"
        size /= step
    return f"{size:.2f}"
    #return f"{size:.2f}{units[-1]}"

@app.route('/status', methods=['POST'])
def toggle_recording():
    global executing_service
    global service_PID

    data = request.get_json()
    state = data.get("state")

    if state == "start":
        print(data.get("service-name"))
        print(data.get("service-name"))
        executing_service = data.get("service-name")
        service_PID = random.randint(0, 50)
        return {"status": "OK"}, 200

    elif state == "stop":
        executing_service = ""
        service_PID = -1
        return {"status": "OK"}, 200

    return {"error": "Invalid state"}, 400


if __name__ == '__main__':
    monitor_thread = threading.Thread(target=monitor_stats, daemon=True)
    monitor_thread.start()
    app.run(host="0.0.0.0", port=5006)