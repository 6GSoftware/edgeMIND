import json
import torch
#from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from langchain.prompts import PromptTemplate
#from diffusers import StableDiffusionPipeline
#from diffusers import LCMScheduler, AutoPipelineForText2Image
from diffusers import DiffusionPipeline
import requests
import logging
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

#-------------------------------------------------------------------------------------------------

# Set the random seed for reproducibility
torch.random.manual_seed(0)

VECTOR_DB_URL = "http://vector-db:8000/search"

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

#---------------------------------------------------------------------------------------------------

# Test 3
pipe = DiffusionPipeline.from_pretrained("segmind/SSD-1B", torch_dtype=torch.float32)
pipe = pipe.to("cpu")

@app.route("/generate-image", methods=["POST"])
def generate_image():
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

            # Generate image
            image = pipe(prompt, num_inference_steps=50).images[0]

            # Send the generated image to the user
            if image:
                # TODO: Connect to the input processing layer
                image.save("./output.png")
                return jsonify({"status": "success", "message": "Image was created!"})
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
    app.run(host='0.0.0.0', port=6001)