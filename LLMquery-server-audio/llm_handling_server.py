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
import base64
from io import BytesIO
import json
import torch
#from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from langchain.prompts import PromptTemplate
#from diffusers import StableDiffusionPipeline
#from diffusers import LCMScheduler, AutoPipelineForText2Image
from diffusers import StableDiffusionXLPipeline
from datetime import datetime
import socket
#import re
import requests
import logging
from flask import Flask, request, jsonify
import threading

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

#-------------------------------------------------------------------------------------------------

# Set the random seed for reproducibility
torch.random.manual_seed(0)

VECTOR_DB_URL = "http://vector-db-server:8000/search"

# Define the prompt template for the assistant
prompt_template = """
{question} , high quality. Context: {context}
"""

# Initialize the prompt with template
PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context", "question"]
)

#---------------------------------------------------------------------------------------------------

# Test 3
#pipe = StableDiffusionXLPipeline.from_pretrained("segmind/SSD-1B", torch_dtype=torch.float16, use_safetensors=True, variant="fp16")
#pipe = pipe.to("cuda")

pipe = StableDiffusionXLPipeline.from_pretrained("segmind/Segmind-Vega", torch_dtype=torch.float16, use_safetensors=True, variant="fp16")
pipe.to("cuda")
pipe.enable_sequential_cpu_offload()

@app.route("/generate-image", methods=["POST"])
def generate_image():
    """Initialize the server. \n
        Create and start the http server. \n
        Start listening for client connections."""

    try:
        data = request.get_json()
        user_question = data.get("question")

        if not user_question:
            return jsonify({"status": "error", "message": "No question provided"}), 400
        
        logging.info(f"Received from client: {user_question}")

        # Test 1
        '''
        model = "runwayml/stable-diffusion-v1-5"

        # Load and set up the text-to-image generation model
        pipe = StableDiffusionPipeline.from_pretrained(
            pretrained_model_name_or_path=model,
            torch_dtype=torch.float32
        ).to("cpu")

        pipe.set_progress_bar_config(disable=False)
        '''

        # Test 2
        '''
        model_id = "stabilityai/stable-diffusion-xl-base-1.0"
        adapter_id = "latent-consistency/lcm-lora-sdxl"

        pipe = AutoPipelineForText2Image.from_pretrained(model_id, torch_dtype=torch.float32)
        pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
        pipe.to("cpu")

        # load and fuse lcm lora
        pipe.load_lora_weights(adapter_id)
        pipe.fuse_lora()
        '''

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

        if response.status_code != 200:
            return jsonify({"status": "error", "message": "Vector DB error"}), 500

        response_data = response.json()
        if response_data.get('status') == 'error':
            return jsonify({"status": "error", "message": response_data.get('message')}), 500

        db_result = response_data['message']

        if db_result:
            # Format prompt for image generation
            prompt = PROMPT.format(context=db_result, question=user_question)

            # Counting the words for testing...
            prompt_word_count = len(prompt.split())
            logging.info(f"The word count of the prompt is {prompt_word_count}")

            # Generate image
            #image = pipe(prompt=prompt, num_inference_steps=15).images[0]
            # disable guidance_scale by passing 0
            #image = pipe(prompt=prompt, num_inference_steps=5, guidance_scale=0).images[0]
            # Generate (PIL) image
            neg_prompt = "(worst quality, low quality, 3d, 2d, painting, cartoons, sketch)"
            image = pipe(prompt, negative_prompt=neg_prompt, num_inference_steps=25).images[0]  # NOTE: original num_inference_steps=25

            if image:
                # Save image to in-memory buffer
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                buffer.seek(0)

                # Send the generated image to the client
                encoded_img_string = base64.b64encode(buffer.read()).decode('utf-8')
                return jsonify({"status": "success", "message": encoded_img_string}), 200
            else:
                return jsonify({"status": "error", "message": "Image generation failed"}), 500

        return jsonify({
            "status": "error",
            "message": "I couldn't find relevant information for your query. Could you provide more details?"
        }), 200

    except Exception as e:
        logging.exception("Exception in /generate-image")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)