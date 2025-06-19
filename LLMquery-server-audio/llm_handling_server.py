"""
This module is the edgeMIND user query processing server. This module:
    > prepares everything that is needed for processing queries sent to the server by users. This includes: loading
      the generation model and the tokenizer, defining the prompt template and initializing the prompt with the template.
    > starts the web socket server and handles client connections.
    > receives a query from a connected client and sends it forward to the edgeMIND vector database management server.
    > receives a response from the vector database server ands sends that response and the user query to an LLM for
      response generation.
    > sends the generated response back to the user.
"""

#import os
import json
import torch
#from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from langchain.prompts import PromptTemplate
#from diffusers import StableDiffusionPipeline
#from diffusers import LCMScheduler, AutoPipelineForText2Image
#from diffusers import DiffusionPipeline
from diffusers import StableDiffusionXLPipeline
from datetime import datetime
import socket
#import re
import requests
import logging
from flask import Flask, request, jsonify


logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Set the random seed for reproducibility
torch.random.manual_seed(0)

#VECTOR_DB_URL = "http://localhost:8000/search" # Use in testing outside container
VECTOR_DB_URL = "http://vector_db_server:8000/search"

GENERATE_IMAGE_URL = "http://image_generation:7400/generate"

#model_path = "./saved_LLM_model"
#
## Define the prompt template for the assistant
#prompt_template = """
#{question} , high quality. Context: {context}
#"""
#
## Initialize the prompt with template
#PROMPT = PromptTemplate(
#    template=prompt_template,
#    input_variables=["context", "question"]
#)
#
## Test 3
#pipe = DiffusionPipeline.from_pretrained("segmind/SSD-1B", torch_dtype=torch.float32)
#pipe = pipe.to("cpu")
#
## Test 4: with GPU
#pipe = StableDiffusionXLPipeline.from_pretrained("segmind/SSD-1B", torch_dtype=torch.float16, use_safetensors=True, variant="fp16")
#pipe.to("cuda")


def query_database(user_question):
    # Data to be sent to the database layer
    post_data = {
        'question': user_question
    }

    # Defining content type for the payload
    headers = {'Content-type': 'application/json'}
    # Post the user question to the vector database server and get the query result as response
    response = requests.post(VECTOR_DB_URL, data=json.dumps(post_data), headers=headers)
    #response_as_json = response.json()
    #db_result = response_as_json['message']

    return response


@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        data = request.get_json()
        user_question = data.get("question")

        if not user_question:
            return jsonify({"status": "error", "message": "No question provided"}), 400
        
        logging.info(f"Received from client: {user_question}")

        res = query_database(user_question)

        if res.status_code != 200:
            return jsonify({"status": "error", "message": "Vector DB error"}), 500

        response_data = res.json()
        if response_data.get('status') == 'error':
            return jsonify({"status": "error", "message": response_data.get('message')}), 500

        db_result = response_data['message']

        if not db_result:
            logging.info("No results from the database")
            return jsonify({
                "status": "error",
                "message": "I couldn't find relevant information for your query. Could you provide more details?"
            }), 200
        
        response = requests.post(GENERATE_IMAGE_URL, json={'question': user_question, 'db': db_result})
        res_data = response.json()['message']

        if response.status_code == 200:
            return jsonify({'status': 'success','message': res_data}), 200
        else:
            return jsonify({'error': 'generation failed'}), 500
            
        #except Exception as e:
        #    logging.info("Error in Image generation")
        #    return jsonify({"status": "error", "message": "Image generation failed"}), 500
     
    except Exception as e:
        logging.exception("Exception in /generate-image")
        return jsonify({"status": "error", "message": str(e)}), 500


#if __name__ == '__main__':
#    threading.Thread(target=start_server, daemon=True).start()
#    app.run(host='0.0.0.0', port=6001)