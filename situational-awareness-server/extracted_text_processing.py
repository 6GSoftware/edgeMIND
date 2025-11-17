"""Extracted Data Processing: Sentence Tokenizing

This module is responsible for tokenizing sentences from the extracted data provided by upstream processing services.

How this module works:
- The extracted data is received from upstream services and tokenized using NLTK's sentence tokenizer.
- The cleaned and tokenized sentences are saved to the Pre_processed_text.txt file and forwarded to the
  situational awareness module for topic classification and vectorization.
"""

import json
import nltk
import re
import time
import requests
from situational_awareness_faiss import send_new_data_to_database
import logging
from flask import Flask, request, jsonify
import pyRAPL
import psutil
import threading
import os
import subprocess


pyRAPL.setup()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

TAG = "extracted_text_processing:  "

VECTOR_DB_URL_SEARCH = "http://vector_db:8000/search"
# VECTOR_DB_URL_SEARCH = "http://127.0.0.1:8000/search"

pre_processed_text_file_path = './Pre_processed_text.txt'

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    logging.info("[NLTK] 'punkt' not found. Downloading now...")
    nltk.download('punkt_tab')

def preprocess_sentence(sentence):
    sentence = sentence.lower()  # Convert to lowercase
    sentence = re.sub(r'\s+', ' ', sentence).strip()  # Remove extra spaces
    return sentence


def process_extracted_texts(file_content):
    processed_file_content = ""

    # Tokenize sentences using nltk's sentence tokenizer
    sentences = nltk.tokenize.sent_tokenize(file_content)
    #sentences = nltk.tokenize.sent_tokenize(text_data)

    # Preprocess each sentence: lowercase and remove extra spaces
    cleaned_sentences = [preprocess_sentence(sentence) for sentence in sentences]

    # Save embeddings to a .txt file
    with open(pre_processed_text_file_path, 'a', encoding='utf-8') as output_file:
        for sentence in cleaned_sentences:
            output_file.write(f"{sentence}\n")
            processed_file_content = processed_file_content + f"{sentence}\n"
            #output_file.write(f"Embedding: {np.array2string(embedding, precision=4, separator=',')}\n\n")

    logging.info(f"{TAG} Cleaned sentences saved to {pre_processed_text_file_path}")

    return processed_file_content


@app.route('/process_extracted_texts', methods=['POST'])
def handle_extracted_texts():
    global monitoring_cpu, cpu_values, ram_values

    monitoring_cpu = True

    start_time = time.time()

    try:
        # Extract data from the HTTP request
        data = request.get_json()

        processed_file_contents = data.get("data", "")
        run_id = data.get("run_id", "")

        meter = pyRAPL.Measurement(f"sa_{run_id}")
        meter.begin()

        if not processed_file_contents:
            print(f"{TAG} No data received.")
            return jsonify({"status": "error", "message": "No data received"}), 400

        print(f"{TAG} AFTER: {processed_file_contents}")

        processed_file_contents = process_extracted_texts(processed_file_contents)

        print(f"{TAG} BEFORE: {processed_file_contents}")

        database = "temp"

        send_new_data_to_database([
            line + '\n' for line in processed_file_contents.split('\n') if line.strip()
        ], database)

        stop_monitoring()

        end_time = time.time()
        meter.end()

        energy_pkg = sum(meter.result.pkg) / 1_000_000
        energy_dram = sum(meter.result.dram or []) / 1_000_000
        energy_joules = energy_pkg + energy_dram

        duration = end_time - start_time

        return jsonify({
            "status": "ok",
            "cpu_values": cpu_values,
            "ram_values": ram_values,
            "duration": duration,
            "energy_joules": energy_joules
        })

    except Exception as e:
        print(f"{TAG} Error while processing: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


monitoring_cpu = False
monitoring_ram = False
cpu_values = []
ram_values = []


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


def monitor_usage(interval=3):
    global cpu_values, ram_values, monitoring_ram, monitoring_cpu

    cpu_values.clear()
    ram_values.clear()

    last_print_time = time.time()
    cpu = 0.0  # Default value for printing

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
            cpu = psutil.cpu_percent(interval=None)
            cpu_values.append(cpu)

        now = time.time()
        if now - last_print_time >= 1:
            print(f"used_mem:{used_mem}")

            # cpu_str = f"{cpu:.2f}%" if monitoring_cpu else "OFF"
            # ram_str = format_bytes(used_mem) if used_mem else "OFF"
            # logging.info(f"CPU: {cpu_str} | RAM: {ram_str}")
            last_print_time = now

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


@app.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    global monitoring_ram
    
    monitoring_ram = True
    t = threading.Thread(target=monitor_usage, args=(3,), daemon=True)
    t.start()

    return jsonify({"status": "ok", "message": "RAM monitoring started"}), 200

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    global monitoring_cpu, monitoring_ram

    monitoring_cpu = False
    monitoring_ram = False
    return jsonify({"status": "ok", "message": "Monitoring stopped"}), 200

try:
    with open("/data/memory_usage_gb.txt") as f:
        mem_usage = float(f.read().strip())
        print(f"Memory usage: {mem_usage}")
except Exception as e:
    mem_usage = None
    print("Failed to read memory usage: ", e)

        
if __name__ == "__main__":
    # monitoring = True
    # threading.Thread(target=monitor_usage, args=(0.1,), daemon=True).start()
    monitoring_cpu = True
    monitoring_ram = True
    threading.Thread(target=monitor_usage, args=(3.0,), daemon=True).start()
    app.run(host="0.0.0.0", port=6501, debug=False)