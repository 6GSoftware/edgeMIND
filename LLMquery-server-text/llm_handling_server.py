"""
This module is the edgeMIND user query processing server. This module:
    > prepares everything that is needed for processing queries sent to the server by users. This includes: loading
      the generation model and the tokenizer, defining the prompt template, and initializing the prompt.
    > exposes an HTTP endpoint to receive a query from a client.
    > sends the query to the edgeMIND vector database management server.
    > receives a response from the vector database and passes it along with the user query to an LLM for generation.
    > sends the generated response back to the user.
    > forwards the generated response to the situational awareness module for further processing.
"""

import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from langchain.prompts import PromptTemplate
from datetime import datetime
import re
import requests
from flask import Flask, request, jsonify
import logging
import os
import uuid
import pyRAPL
import psutil
import time
import threading

from save_measurements import save

pyRAPL.setup()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

@app.route('/health')
def health():
    return {'status': 'ok'}

# Set the random seed for reproducibility
torch.random.manual_seed(0)

# INPUT_LAYER_URL = "http://situational_awareness:6501/process_user_question"

# SA_URL = "http://127.0.0.1:6501/process_extracted_texts"
SA_URL = "http://situational-awareness:6501/process_extracted_texts"

# ---------------------

os.environ["CUDA_VISIBLE_DEVICES"] = "" # FOR TESTING. REMOVE IF WANT TO USE GPU.

try:
    model_path = "./saved_LLM_model"
    model = AutoModelForCausalLM.from_pretrained(model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)

    generation_args = {
        "max_new_tokens": 500,
        "return_full_text": False,
        "temperature": 0.5,
        "do_sample": True,
    }
except :
    logging.warning(f"Failed to load model.")

if torch.cuda.is_available():
    print("Using GPU:", torch.cuda.get_device_name(0))
else:
    print("Using CPU")


# Define the prompt template for the assistant
prompt_template = """
<|system|>
You are an expert assistant. 
You must follow these rules strictly:
- Only use the information in the context provided.
- If the answer is not fully contained in the context, reply exactly: "I don't know."
- Never use outside knowledge, assumptions, or speculation.
- Always respond in the same language as the question.
<|end|>

<|user|>
Context: {context}
Question: {question}
<|end|>

<|assistant|>
"""

# Initialize the prompt with template
PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context", "question"]
)


def clean_text(text):
    """Remove extra spaces and special characters, except periods."""
    # Remove special characters but keep periods
    cleaned_text = re.sub(r"[^a-zA-Z0-9\s.]", "", text)
    
    # Remove extra spaces
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    
    return cleaned_text


def filter_generated_text(generated_text, retrieved_texts):
    """Filter out the retrieved texts and remove timestamps or unwanted patterns."""
    # Remove the retrieved texts from the generated response
    filtered_text = generated_text.replace(retrieved_texts, "").strip()

    # Clean any remaining extra spaces or special characters
    filtered_text = clean_text(filtered_text)

    # Remove timestamps (e.g., "Timestamp 20241016T095658.722410")
    filtered_text = re.sub(r"Timestamp\s+\d{8}T\d{6}\.\d+", "", filtered_text)

    # Remove repetitive "Topic text" sections if they occur multiple times
    filtered_text = re.sub(r"Topic text.*?(?=\bTimestamp|\n|$)", "", filtered_text)

    # Remove any extra spaces introduced by the cleanup
    filtered_text = re.sub(r"\s+", " ", filtered_text).strip()

    return filtered_text


def query_llm(generation_args, pipe, db_query_result, user_question):
    """Handle a connected client: \n
    - receive query from the client and send it to the vector database server.
    - receive response from the vector database server. Send the response and the user query to the LLM.
    - get a generated response from the LLm and send it back to the client.
    - finally, close client socket connection."""

    # Prepare response for the client
    if db_query_result:
        message = PROMPT.format(context=db_query_result, question=user_question)
    else:
        return ""
    
    logging.info(f"Prompt: {message}")

    # Generate output using the text generation model
    output = pipe(message, **generation_args)
    generated_text = output[0]['generated_text']
    logging.info(f"Generated response before cleanup: {generated_text}")

    # Filter out the retrieved texts from the generated response
    #final_generated_text = filter_generated_text(generated_text, response)
    final_generated_text = filter_generated_text(generated_text, db_query_result)
    logging.info(f"Final generated response: {final_generated_text}")

    return final_generated_text


@app.route('/process_query', methods=['POST'])
def process_query():
    global cpu_values, ram_values, monitoring_ram, monitoring_cpu

    start_time = time.time()
    run_id = str(uuid.uuid4())

    # --- Start energy measurement ---
    meter = pyRAPL.Measurement(f"llm_text_{run_id}")
    meter.begin()

    monitoring_ram = True
    monitoring_cpu = True
    t = threading.Thread(target=monitor_usage, args=(0.1,), daemon=True)
    t.start()

    start_sa_monitoring_SA()

    try:
        user_question = request.json.get('question', '')
        if not user_question:
            return jsonify({'message': 'No question provided'}), 400

        logging.info(f"Received question: {user_question}")

        post_data = {'question': user_question}

        # search_url = "http://127.0.0.1:8000/search"
        search_url = "http://vector-db:8000/search"
        
        response = requests.post(search_url, json=post_data)

        if response.status_code != 200:
            return jsonify({'message': f"Vector DB error: {response.text}"}), response.status_code

        response_as_json = response.json()
        print(f"Return :{response_as_json}")

        # Parse chunks
        permanent_chunks = response_as_json.get("permanent_chunks", [])
        temp_chunks = response_as_json.get("temp_chunks", [])
        all_chunks = permanent_chunks + temp_chunks

        logging.info(f"Permanent chunks: {permanent_chunks}")
        logging.info(f"Temp chunks: {temp_chunks}")

        if not all_chunks:
            return jsonify({'message': "No related info found for your question."}), 200

        # Form chunks for LLM
        db_result = "\n".join([f"{i+1}. {chunk}" for i, chunk in enumerate(all_chunks)])

        # return jsonify({'message': "OK"}), 200

        llm_result = query_llm(generation_args, pipe, db_result, user_question)

        # llm_result = "The color of the keyboard is black with white letters."

        print(f"LLM RESULT :{llm_result}")

        if not llm_result:
            return jsonify({'message': "I couldn't find relevant information for your query. Could you provide more details?"}), 200

        payload = {"data": llm_result, "run_id": run_id}

        try:
            logging.info(f"Sending to {SA_URL}...")
            response = requests.post(SA_URL, json=payload)
            response.raise_for_status()
            sa_result = response.json()

            logging.info(f"Response from SA service: {sa_result}")

        except Exception as e:
            logging.error(f"Failed to communicate with SA service: {e}")
            sa_result = {}

        monitoring_ram = False
        monitoring_cpu = False

        t.join()

        end_time = time.time()
        meter.end()
        duration = end_time - start_time

        energy_pkg = sum(meter.result.pkg) / 1_000_000
        energy_dram = sum(meter.result.dram or []) / 1_000_000
        energy_joules = energy_pkg + energy_dram

        save(sa_result, cpu_values, ram_values, energy_joules, duration, run_id)

        return jsonify({'message': llm_result}), 200

    except Exception as e:
        logging.error(f"Error in process_query: {e}")
        return jsonify({'message': str(e)}), 500


@app.route('/question_about_last_uploaded_file', methods=['POST'])
def question_about_last_uploaded_file():
    try:
        user_question = request.json.get('question', '')
        if not user_question:
            return jsonify({'message': 'No question provided'}), 400

        logging.info(f"Received question: {user_question}")

        # url = "http://127.0.0.1:8000/get_data_from_last_uploaded_file"
        url = "http://vector-db:8000/get_data_from_last_uploaded_file"

        response = requests.get(url)
        response_json = response.json()

        print(response_json)

        if response.status_code == 200:
            return jsonify({
                "message": response_json.get("data")
            }), 200
        else:
            return jsonify({
                "message": response_json.get("error", response.text)
            }), response.status_code

    except Exception as e:
        logging.error(f"Error in question_about_last_uploaded_file: {e}")
        return jsonify({'message': str(e)}), 500


# ---------------

# SA_MONITOR_URL = "http://127.0.0.1:6501/start_monitoring"
SA_MONITOR_URL = "http://situational-awareness:6501/start_monitoring"

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


def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(power_labels) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"


def monitor_usage(interval=0.1):
    global cpu_values, ram_values, monitoring_ram, monitoring_cpu

    cpu_values.clear()
    ram_values.clear()

    last_print_time = time.time()
    cpu = 0.0  # Default value for printing

    while monitoring_ram or monitoring_cpu:
        if monitoring_ram:
            mem = psutil.virtual_memory()
            used_mem = mem.total - mem.available - mem_usage
            ram_values.append(used_mem)
        else:
            used_mem = None

        if monitoring_cpu:
            cpu = psutil.cpu_percent(interval=None)
            cpu_values.append(cpu)

        now = time.time()
        if now - last_print_time >= 1:
            print(f"mem.total:{mem.total}")
            print(f"mem.available:{mem.available}")
            print(f"mem_usage:{mem_usage}")

            # cpu_str = f"{cpu:.2f}%" if monitoring_cpu else "OFF"
            # ram_str = format_bytes(used_mem) if used_mem else "OFF"
            # logging.info(f"CPU: {cpu_str} | RAM: {ram_str}")
            # last_print_time = now

        time.sleep(interval)


def start_sa_monitoring_SA():
    try:
        response = requests.post(SA_MONITOR_URL)
        response.raise_for_status()
        logging.info("Successfully started CPU/RAM monitoring in SA service.")
    except Exception as e:
        logging.error(f"Failed to start monitoring in SA service: {e}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5007, debug=False)