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

#import os       #NOTE use outside containers
#os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:64,expandable_segments:True" #NOTE use outside containers
import json
import torch
#from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from langchain.prompts import PromptTemplate
#from diffusers import StableDiffusionPipeline
#from diffusers import LCMScheduler, AutoPipelineForText2Image
#from diffusers import DiffusionPipeline
from diffusers import StableDiffusionXLPipeline    # NOTE for GPU
from datetime import datetime
import socket
#import re
import requests
from eco2ai import set_params, Tracker

#-------------------------------------------------------------------------------------------------

# Set the random seed for reproducibility
torch.random.manual_seed(0)

# Server setup
SERVER_IP_MOBILE = "0.0.0.0"  # Use your own IP address
SERVER_PORT_MOBILE = 5001   # NOTE: port 5001 for the image generation server

#SERVER_IP_INPUT_LAYER = "---"
#SERVER_PORT_INPUT_LAYER = 6500

#VECTOR_DB_URL = "http://localhost:8000/search" # Use in testing outside container
VECTOR_DB_URL = "http://vector_db_server:8000/search"

model_path = "./saved_LLM_model"

# Define the prompt template for the assistant
prompt_template = """
{question} , high quality. Context: {context}
"""

#prompt_template = """
#{question}
#"""

# Initialize the prompt with template
PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context", "question"]
)

# For tracking CO2 emissions and energy usage
set_params(
    project_name="text-to-image generation service", 
    experiment_description="generating image based on user question and vector database query results",
    file_name="image_generation_emission2.csv"
)
print("Parameters set for emissions tracking")

#---------------------------------------------------------------------------------------------------

def start_server():
    """Initialize the server. \n
    Create and start the socket server. \n
    Start listening for client connections."""

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

    # Test 3: with CPU
    '''
    pipe = DiffusionPipeline.from_pretrained("segmind/SSD-1B", torch_dtype=torch.float32)
    pipe = pipe.to("cpu")
    '''

    # Test 4: with GPU
    pipe = StableDiffusionXLPipeline.from_pretrained("segmind/SSD-1B", torch_dtype=torch.float16, use_safetensors=True, variant="fp16")
    pipe.to("cuda")

    # Create socket server for the mobile app to connect to
    mobile_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    mobile_server_socket.bind((SERVER_IP_MOBILE, SERVER_PORT_MOBILE))
    mobile_server_socket.listen(5)
    print(f"Server for mobile app is listening on {SERVER_IP_MOBILE}:{SERVER_PORT_MOBILE}")

    while True:
        try:
            # Accept incoming connection from the mobile app
            mobile_socket, mobile_address = mobile_server_socket.accept()
            print(f"Connection established with {mobile_address}")

            tracker = Tracker() # Start tracking...
            print("Start tracking...")
            tracker.start()

            # Get query question from client
            user_question = mobile_socket.recv(1024).decode('utf-8')

            if not user_question:
                print("No data was received.")
                continue    # TODO: check that this works!
            print(f"Received from client: {user_question}")
            now=datetime.now()
            print(now)

            # Data to be sent to the database layer
            post_data = {
                'question': user_question
            }

            # Defining content type for the payload
            headers = {'Content-type': 'application/json'}
            # Post the user question to the vector database server and get the query result as response
            response = requests.post(VECTOR_DB_URL, data=json.dumps(post_data), headers=headers)
            response_as_json = response.json()
            #db_result = response_as_json['message']

            #if response_as_json['status'] == 'error':
            if response_as_json['status'] == 'error':
                response_to_user = f"An error occurred in searching the vector database: {response_as_json['message']}"
                mobile_socket.sendall(response_to_user)
                mobile_socket.close()
                print("Connection closed with the mobile application due to an error")
                continue    # TODO: check that this works!

            db_result = response_as_json['message']

            if db_result:
                # Format prompt for image generation
                prompt = PROMPT.format(context=db_result, question=user_question)

                # Counting the words for testing...
                prompt_word_count = len(prompt.split())
                print(f"The word count of the prompt is {prompt_word_count}")

                # Generate image
                #image = pipe(prompt=prompt, num_inference_steps=15).images[0]
                # disable guidance_scale by passing 0
                #image = pipe(prompt=prompt, num_inference_steps=5, guidance_scale=0).images[0]
                # Generate image

                #torch.cuda.empty_cache()    #NOTE use outside containers, comment out when using containers
                
                image = pipe(
                    prompt,
                    num_inference_steps=50,  # NOTE: original num_inference_steps=25
                    negative_prompt="text, cartoon, missing parts, poor quality",
                ).images[0]
                

                # Send the generated image to the mobile app
                if image:
                    image.save("./output.png")
                    mobile_socket.sendall("Image was created!".encode('utf-8'))
                else:
                    mobile_socket.sendall("Could not create requested image".encode('utf-8'))

            else:
                response = "I couldn't find relevant information for your query. Could you provide more details?"
                mobile_socket.sendall(response.encode('utf-8'))

            mobile_socket.close()
            print("Connection closed with the mobile application")

            # Connect to the input processing layer
            #input_layer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            #input_layer_socket.connect((SERVER_IP_INPUT_LAYER, SERVER_PORT_INPUT_LAYER))
            #
            ## Send the llm query result to the input processing layer for further processing
            #input_layer_socket.send(llm_result.encode('utf-8'))
            #print("LLM result sent to the input layer (text processing and situational awareness)")
            #
            #response = input_layer_socket.recv(1024).decode('utf-8')
            #print(f"Received from the input side: {response}")
            #input_layer_socket.close()
            #print("Connection closed with the input processing layer")


        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            print("Stop tracking")
            tracker.stop()


if __name__ == "__main__":
    start_server()