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
from threading import Lock

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Set the random seed for reproducibility
torch.random.manual_seed(0)

# Define the prompt template for the assistant
prompt_template = """
{question} , high quality. Context: {context}
"""

# Initialize the prompt with template
PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context", "question"]
)

## Test 3
#pipe = DiffusionPipeline.from_pretrained("segmind/SSD-1B", torch_dtype=torch.float32)
#pipe = pipe.to("cpu")

# Test 4: with GPU
pipe = StableDiffusionXLPipeline.from_pretrained("segmind/SSD-1B", torch_dtype=torch.float16, use_safetensors=True, variant="fp16")
pipe.to("cuda")

lock = Lock()


@app.route("/generate", methods=["POST"])
def generate_image():
    try:
        data = request.get_json()
        user_question = data.get("question")
        db_results = data.get("db")

        if not user_question or not db_results:
            return jsonify({"status": "error", "message": "No question or database results provided"}), 400

        logging.info(f"Received from client: {user_question} and {db_results}")

        # Format prompt for image generation
        prompt = PROMPT.format(context=db_results, question=user_question)

        # Counting the words for testing...
        prompt_word_count = len(prompt.split())
        logging.info(f"The word count of the prompt is {prompt_word_count}")

        with lock:
            # Generate image
            result = pipe(prompt, num_inference_steps=30, negative_prompt="text, cartoon, missing parts, poor quality")
            logging.info("Image generation done, but we don't know yet if there is an image or not")
            image = result.images[0]
            logging.info("Image generation successful!")
            if not image:
                return jsonify({"status": "error", "message": "No image"})
            image.save("./output.png")      #TODO: send generated image to the mobile app

        return jsonify({"status": "success", "message": "Image was created!"}), 200
    except Exception as e:
        logging.error(f"Exception in image generation: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7400)