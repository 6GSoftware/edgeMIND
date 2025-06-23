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

import json
import torch
from langchain.prompts import PromptTemplate
from diffusers import DiffusionPipeline
from datetime import datetime
import requests
import logging
from flask import Flask, request, jsonify
import io
import base64

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

#-------------------------------------------------------------------------------------------------

# Set the random seed for reproducibility
torch.random.manual_seed(0)

#VECTOR_DB_URL = "http://localhost:8000/search" # Use in testing outside container
VECTOR_DB_URL = "http://vector_db_server:8000/search"

MONITOR_URL = "http://host.docker.internal:5006/status"

model_path = "./saved_LLM_model"

# Define the prompt template for the assistant
prompt_template = """
{question} , high quality. Context: {context}
"""

# Initialize the prompt with template
PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context", "question"]
)

# Test 3
pipe = DiffusionPipeline.from_pretrained("segmind/SSD-1B", torch_dtype=torch.float32)
pipe = pipe.to("cpu")

@app.route("/generate-image", methods=["POST"])
def generate_image():

    try:
        res = requests.post(MONITOR_URL, json={
            "state": "start",
            "service-name": "llm_query_server_audio"
        })
        logging.info("Started monitoring:", res.json())
    except Exception as e:
        logging.info("Failed to start monitoring:", e)

    try:
        data = request.get_json()
        user_question = data.get("question")

        if not user_question:
            return jsonify({"status": "error", "message": "No question provided"}), 400
        
        logging.info(f"Received from client: {user_question}")

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

            image = pipe(prompt, num_inference_steps=50).images[0]  # NOTE: original num_inference_steps=25

            try:
                res = requests.post(MONITOR_URL, json={
                    "state": "stop",
                    "service-name": "llm_query_server_audio"
                }, timeout=2)
                logging.info(f"Started monitoring: {res.json()}")
            except Exception as e:
                logging.warning(f"Monitoring service not available: {e}")

            # Send the generated image to the mobile app
            if image:
                image.save("./output.png")  # Save image to disk for now
                # In addition, send the image to the mobile app: convert image to base64
                buffered = io.BytesIO()
                image.save(buffered, format="PNG")  # or JPEG for smaller size
                image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                return jsonify({"status": "success", "image": image_base64})
            else:
                return jsonify({"status": "error", "message": "Image generation failed"}), 500

        return jsonify({
            "status": "error",
            "message": "I couldn't find relevant information for your query. Could you provide more details?"
        }), 200

    except Exception as e:
        logging.exception("Exception in /generate-image")
        return jsonify({"status": "error", "message": str(e)}), 500


#if __name__ == '__main__':
#    threading.Thread(target=start_server, daemon=True).start()
#    app.run(host='0.0.0.0', port=6001)