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

import gc
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
# import pyRAPL
import psutil
import time
import threading
import subprocess
import queue
import concurrent.futures

#from save_measurements import save

# pyRAPL.setup()

logging.basicConfig(level=logging.INFO)

IN_K3S = os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token")
print(f"IN_K3S: {IN_K3S}")

app = Flask(__name__)

# Files for running evaluation tests
STAGE3_TEST2_FILE = "stage3_test2.csv"

@app.route('/health')
def health():
    print("Health check received")
    return {'status': 'ok'}

# Set the random seed for reproducibility
torch.random.manual_seed(0)

# INPUT_LAYER_URL = "http://situational_awareness:6502/process_user_question"
# SA_URL = "http://127.0.0.1:6502/process_extracted_texts"
SA_URL = "http://situational-awareness-gpu:6502/process_extracted_texts"

# ---------------------

#os.environ["CUDA_VISIBLE_DEVICES"] = "" # FOR TESTING. COMMENT OUT IF WANT TO USE GPU.

if torch.cuda.is_available():
    print("Using GPU:", torch.cuda.get_device_name(0))
else:
    print("Using CPU")


#define_model = "phi"
#define_model = "gemma"
define_model = "llama2"

print(f'MODEL: {define_model}')


generation_args = None
pipe = None


if define_model == "phi":
    try:
        model_path = "/models/phi3"
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto"   # ← loads directly to GPU
        )
        tokenizer = AutoTokenizer.from_pretrained(model_path)

        pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto"   # ← also needed here so the pipeline respects GPU
        )

        generation_args = {
            "max_new_tokens": 300,
            "return_full_text": False,
            "temperature": 0.5,
            "do_sample": True,
            "top_p": 0.9,
        }

        # Confirm device placement
        print(f"Model loaded on: {next(model.parameters()).device}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        print(f"GPU name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'}")
    except Exception as e:
        logging.warning(f"Failed to load model: {e}")

    # Define the prompt template for the assistant
    # prompt_template = """
    # <|system|>
    # You are an expert assistant. 
    # You must follow these rules strictly:
    # - Only use the information in the context provided.
    # - If the answer is not fully contained in the context, reply exactly: "I don't know."
    # - Never use outside knowledge, assumptions, or speculation.
    # - Always respond in the same language as the question.
    # <|end|>

    # <|user|>
    # Context: {context}
    # Question: {question}
    # <|end|>

    # <|assistant|>
    # """

    # prompt_template = """
    # <|system|>
    # You are an expert assistant.
    # Use ONLY the following information to answer the question.
    # If insufficient, respond exactly: "I don't know."
    # Never use external knowledge.
    # <|end|>

    # <|user|>
    # Image extracted information:
    # {image_context}

    # RAG context:
    # {context}

    # Question:
    # {question}
    # <|end|>

    # <|assistant|>
    # """

    prompt_template = """
    <|system|>
    Use only the following information to answer the question.
    If insufficient, respond exactly: "I don't know."
    <|end|>

    <|user|>
    Image extracted information:
    {image_context}

    RAG context:
    {context}

    Question:
    {question}
    <|end|>

    <|assistant|>
    """

elif define_model == "gemma":
    try:
        model_path = "/models/gemma"
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")   #NOTE: GPU testing

        tokenizer = AutoTokenizer.from_pretrained(model_path)

        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",   # ← handles GPU placement automatically
#            device_map="cuda:0"          # force to GPU 0
        )

        print(f"Model hf_device_map: {model.hf_device_map}")
        print(f"Model loaded on: {next(model.parameters()).device}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        print(f"GPU name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'}")
        
    except Exception as e:
        logging.warning(f"Failed to load Gemma model: {e}")

    # prompt_template = """<start_of_turn>user
    # Use only the following information to answer the question.
    # If insufficient, respond exactly: "I don't know."

    # Image extracted information:
    # {image_context}

    # RAG context:
    # {context}

    # Question:
    # {question}
    # <end_of_turn>
    # <start_of_turn>model
    # """

    prompt_template = """
    You are an expert assistant. Follow these rules strictly:

    1. Use ONLY the information provided below.
    2. Combine information from both the image and the RAG context when answering.
    3. If the answer is not fully supported by the provided information, respond: "I don't know."
    4. Do NOT use outside knowledge or assumptions.

    Image information:
    {image_context}

    RAG context:
    {context}

    Question:
    {question}

    Answer:
    """


elif define_model == "llama2":
    try:
        model_path = "/models/llama2_chat"
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            low_cpu_mem_usage=True,
            device_map="auto"
        )

        prompt_template = ""

        # Confirm device placement
        print(f"Model loaded on: {next(model.parameters()).device}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        print(f"GPU name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'}")
    except Exception as e:
        logging.warning(f"Failed to load Llama2 model: {e}")


# Initialize the prompt with template
PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context", "question", "image_context"]
)


# NOTE: For GPU testing
# ================================================================================
# A single-item queue for inference jobs
_inference_queue = queue.Queue()

def _inference_worker():
    """Single thread that owns the GPU model and processes requests one at a time."""
    while True:
        future, fn, args, kwargs = _inference_queue.get()
        try:
            result = fn(*args, **kwargs)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)

# Start the worker thread once, when the service starts
_worker_thread = threading.Thread(target=_inference_worker, daemon=True)
_worker_thread.start()

def run_inference(fn, *args, **kwargs):
    """Submit an inference job and block until it completes."""
    future = concurrent.futures.Future()
    _inference_queue.put((future, fn, args, kwargs))
    return future.result()  # blocks the Flask worker thread until done
# ===============================================================================


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
    print(f"Generated text before cleanup: {generated_text}")
    # Clean any remaining extra spaces or special characters
    filtered_text = clean_text(filtered_text)
    print(f"Generated text after cleanup: {filtered_text}")
    # Remove timestamps (e.g., "Timestamp 20241016T095658.722410")
    filtered_text = re.sub(r"Timestamp\s+\d{8}T\d{6}\.\d+", "", filtered_text)

    # Remove repetitive "Topic text" sections if they occur multiple times
    filtered_text = re.sub(r"Topic text.*?(?=\bTimestamp|\n|$)", "", filtered_text)

    # Remove any extra spaces introduced by the cleanup
    filtered_text = re.sub(r"\s+", " ", filtered_text).strip()
    print(f"Final filtered text: {filtered_text}")

    return filtered_text


def query_phi(generation_args, pipe, db_query_result, user_question, image_context):
    """Handle a connected client: \n
    - receive query from the client and send it to the vector database server.
    - receive response from the vector database server. Send the response and the user query to the LLM.
    - get a generated response from the LLm and send it back to the client.
    - finally, close client socket connection."""

    logging.info("DB_QUERY_RESULT:")
    logging.info(db_query_result)

    # Prepare response for the client
    if db_query_result:
        message = PROMPT.format(
            context=db_query_result,
            question=user_question,
            image_context=image_context
        )
    else:
        return ""
    
    logging.info(f"Prompt: {message}")

    # Generate output using the text generation model
    final_generated_text = ""
    try:
        output = None
        with torch.no_grad():
            output = pipe(message, **generation_args)
        generated_text = output[0]['generated_text']
        logging.info(f"Generated response before cleanup: {generated_text}")

        # Filter out the retrieved texts from the generated response
        #final_generated_text = filter_generated_text(generated_text, response)
        final_generated_text = filter_generated_text(generated_text, db_query_result)
        logging.info(f"Final generated response: {final_generated_text}")
    finally:
        # Clean up inference artifacts after every run, model stays loaded
        del output
        gc.collect()

    return final_generated_text


@app.route('/process_query', methods=['POST'])
def process_query():
    start_time = time.time()
    print("DEBUG: processing the user query...")
#    global ram_values, disk_values, vram_values, monitoring_ram, monitoring_disk, monitoring_vram

    run_id = str(uuid.uuid4())
    user_question = ""
    #retrieval_n = 3    # NOTE: this is for model adaptability tests

#    monitoring_ram = True
#    monitoring_disk = True
#    monitoring_vram = True
#    t = threading.Thread(target=monitor_usage, args=(0,), daemon=True)
#    t.start()

    # start_sa_monitoring_SA()

    file = request.files.get('file')

    if file:
        print("DEBUG: File received")
        if not file.mimetype.startswith("image/"):
            return jsonify({'message': 'File is not an image'}), 400

        user_question = request.form.get('question')
        print(f"DEBUG: user_question from form: {user_question}")

    else:
        print("DEBUG: No file received")
        json_data = request.get_json(silent=True)
        print(f"JSON data received: {json_data}")
        if json_data:
            user_question = json_data.get('question')
            #retrieval_n = json_data.get('n')    # NOTE: FOR MODEL ADAPTABILITY TESTS
            print(f"DEBUG: user_question from JSON: {user_question}")

    if not user_question:
        return jsonify({'message': 'No question provided'}), 400
    
#    files = { 
#        "file": (file.filename, file.stream, file.mimetype)
#    }
#
#    data = {
#        "caller": "llm-service",
#    }
#
#    
#    resp = requests.post(
#        "http://image-service:5002/process_user_image",
#        files=files,
#        data=data
#    )
#
#    image_context = resp.json()
   

    image_context = []

    # image_cpu_values = resp_json["cpu_values"]

    # print("IMAGE CONTEXT:", image_context)
    # print("IMAGE_CPU_VALUES:", image_cpu_values)

    # return jsonify({'message': resp.json()}), 200

    # user_question = hardcoded_question

    print(f"USER_QUESTION: {user_question}")


    try:

        post_data = {'question': user_question}     # NOTE: add 'n': retrieval_n for model adaptability tests

        # search_url = "http://127.0.0.1:8000/search"
        search_url = "http://vector-db-gpu:8001/search"
        
        response = requests.post(search_url, json=post_data)

        if response.status_code != 200:
            return jsonify({'message': f"Vector DB error: {response.text}"}), response.status_code

        response_as_json = response.json()
        print(f"Return :{response_as_json}")

        # Parse chunks
        permanent_chunks = response_as_json.get("permanent_chunks", [])
        #temp_chunks = response_as_json.get("temp_chunks", [])
        all_chunks = permanent_chunks # + temp_chunks

        print(f"PERMANENT CHUNKS: {permanent_chunks}")
        print(f"CHUNKS AMOUNT: {len(permanent_chunks)}")
        #print(f"TEMP CHUNKS: {temp_chunks}")

        # if not all_chunks:
        #     return jsonify({'message': "No related info found for your question."}), 200

        # Form chunks for LLM
        db_result = "\n".join([f"{i+1}. {chunk}" for i, chunk in enumerate(all_chunks)])

        print(f"\nDB_RESULS: {db_result}\n")

        # return jsonify({'message': "OK"}), 200

        # user_question = "what is the color of the car?"
        # db_result = "1. Car has two doors.\n2. Car is white."

        # NOTE: GPU testing
        if define_model == "gemma":
            llm_result = run_inference(query_gemma, db_result, user_question, image_context, max_new_tokens=300)
        elif define_model == "phi":
            llm_result = run_inference(query_phi, generation_args, pipe, db_result, user_question, image_context)
        elif define_model == "llama2":
            llm_result = run_inference(query_llama2, db_result, user_question, image_context, max_new_tokens=300) #265

        # llm_result = "The color of the keyboard is black with white letters."

        print(f"LLM RESULT :{llm_result}")

        if not llm_result:
            llm_result = "I couldn't find relevant information for your query. Could you provide more details?"

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

#        monitoring_ram = False
#        monitoring_disk = False
#        monitoring_vram = False
#
#        t.join()

        # image_result = {
        #     "cpu_values": resp_json["cpu_values"],
        #     "ram_values": resp_json.get("ram_values", []),
        #     "result": resp_json["result"]
        # }

        # save(image_result, cpu_values, ram_values, duration, run_id, prompt, mode, define_model, user_question, permanent_chunks)

        end_time = time.time()
        elapsed = end_time - start_time

        node_name = os.environ.get("NODE_NAME", "NA")

        return jsonify({
            "message": llm_result,
            "db_result": db_result,
            "duration": elapsed,
            "node_name": node_name
        }), 200

    except Exception as e:
        logging.error(f"Error in process_query: {e}")
        return jsonify({'message': str(e)}), 500



def query_gemma(context, question, image_context, max_new_tokens=300):  #256, 512
    prompt = PROMPT.format(context=context, question=question, image_context=image_context)
    logging.info(f"Gemma prompt: {prompt}")

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    try:
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.5,
                top_p=0.9,
                pad_token_id=tokenizer.eos_token_id
            )
    except Exception as e:
        import traceback
        logging.error(f"Error in model.generate():\n{traceback.format_exc()}")
        raise

    logging.info(f"Response generated!")

    raw_output = tokenizer.decode(output[0], skip_special_tokens=True)
    return extract_answer(raw_output)



def extract_answer(text):
    """
    Extract only the model's answer after 'Answer:' and clean it.
    Handles variations like capitalization, punctuation and lists.
    """
    # Split using flexible regex for variations like "Answer :", "ANSWER-", "answer:"
    parts = re.split(r"(?i)answer\s*[:\-–]\s*", text, maxsplit=1)
    if len(parts) < 2:
        return text.strip()
    
    answer = parts[1].strip()
    
    # Stop at the next prompt section if the model repeated the template
    # (e.g. if it hallucinated a new "Context:" or "Question:" block)
    answer = re.split(r"(?i)\n\s*(context|question|instruction|system)\s*[:\-–]", answer)[0]
    
    # Remove wrapping quotes, bullets, markdown junk from the very first line only
    answer = re.sub(r'^[\-\*\•\·]+\s*', '', answer)
    answer = answer.strip(" \"'`")
    
    return answer.strip()


def query_llama2(context, question, image_context, max_new_tokens=300): #256

    x = 0

    print("CONTEXT:")
    print(context)
    print("QUESTION:")
    print(question)
    print("IMAGE CONTEXT:")
    print(image_context)
    
    if x == 1:
        llama_prompt = f"""[INST]<<SYS>>
    Use the provided context to answer the question.
    If the context does not contain the answer, say so.
    <</SYS>>

    Context:
    {context}

    Question:
    {question}
    [/INST]
    """
    else:
        llama_prompt = f"""[INST] <<SYS>>
        Use *only* the information below to answer the question.
        If the information is insufficient, respond exactly with: "I don't know."
        Never guess or infer beyond the provided data.
        <</SYS>>

        Image extracted information:
        {image_context}

        RAG context:
        {context}

        Question:
        {question}
        [/INST]
        """


    inputs = tokenizer(llama_prompt, return_tensors="pt")
    
# NOTE: FOR GPU TESTING:
    # Move inputs to the same device as the model
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}
# ----------------------------------------------------------

    output_tokens = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        temperature=0.5,
        do_sample=True,
        top_p=0.9,
    )

    text = tokenizer.decode(output_tokens[0], skip_special_tokens=True)

    # --- Clean output so it contains only the actual answer ---
    # Remove everything before [/INST]
    if "[/INST]" in text:
        text = text.split("[/INST]")[1].strip()

    # Remove filler phrases if they appear
    unwanted_prefixes = [
    ]

    for prefix in unwanted_prefixes:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()

    return text


@app.route('/question_about_last_uploaded_file', methods=['POST'])
def question_about_last_uploaded_file():
    try:
        user_question = request.json.get('question', '')
        if not user_question:
            return jsonify({'message': 'No question provided'}), 400

        logging.info(f"Received question: {user_question}")

        # url = "http://127.0.0.1:8000/get_data_from_last_uploaded_file"
        url = "http://vector-db-gpu:8001/get_data_from_last_uploaded_file"

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

'''
# SA_MONITOR_URL = "http://127.0.0.1:6502/start_monitoring"
SA_MONITOR_URL = "http://situational-awareness-gpu:6502/start_monitoring"

monitoring_cpu = False
monitoring_ram = False

cpu_values = []
ram_values = []

def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(power_labels) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

'''

#def monitor_usage(interval=0):
#    global ram_values, disk_values, vram_values
#    global monitoring_ram, monitoring_disk, monitoring_vram
#
#    ram_values.clear()
#    disk_values.clear()
#    vram_values.clear()
#
#    last_print_time = time.time()
#
#    while monitoring_ram or monitoring_disk or monitoring_vram:
#        if monitoring_ram:
#            used_mem = fetch_used_memory()
#            ram_values.append(used_mem)
#        else:
#            used_mem = None
#
#        if monitoring_disk:
#            disk_usage = psutil.disk_usage('/')
#            disk_values.append(disk_usage.percent)
#
#        if monitoring_vram:
#            vram_usage = fetch_vram_usage()
#            vram_values.append(vram_usage)
#
#        # print(f"used_mem:{used_mem}")
#        # print(f"CPU:{cpu}")
#
#
#        time.sleep(interval)
#
#
#def fetch_used_memory():
#    cmd = (
#        "crictl --config=/dev/null "
#        "--runtime-endpoint unix:///run/k3s/containerd/containerd.sock "
#        "stats --output=table | "
#        "awk 'NR>1 && $4 != \"\" {"
#        "val=$4;"
#        "gsub(/[^0-9.]/, \"\", val);"
#        "if ($4 ~ /KiB/) sum+=val*1024;"
#        "else if ($4 ~ /MiB|MB/) sum+=val*1024*1024;"
#        "else if ($4 ~ /GiB|GB/) sum+=val*1024*1024*1024;"
#        "} END { printf \"%.2f\", sum/1024/1024; }'"
#    )
#
#    try:
#        output = subprocess.check_output(cmd, shell=True, text=True, timeout=5).strip()
#        if not output:
#            return 0.0
#        return float(output)
#    except subprocess.TimeoutExpired:
#        print("crictl stats timeout – skipped this cycle")
#        return 0.0
#    except subprocess.CalledProcessError as e:
#        print(f"crictl stats failed: {e}")
#        return 0.0
#    except ValueError:
#        print(f"Could not parse memory output: {output!r}")
#        return 0.0

'''
def start_sa_monitoring_SA():
    try:
        response = requests.post(SA_MONITOR_URL)
        response.raise_for_status()
        logging.info("Successfully started CPU/RAM monitoring in SA service.")
    except Exception as e:
        logging.error(f"Failed to start monitoring in SA service: {e}")
'''

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5008, debug=False)