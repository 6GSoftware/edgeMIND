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

#from dotenv import load_dotenv
import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from langchain.prompts import PromptTemplate
from datetime import datetime
import socket
import re
import requests
#import os


# Set the random seed for reproducibility
torch.random.manual_seed(0)

# Server setup
SERVER_IP_MOBILE = "---"  # Use your own IP address
SERVER_PORT_MOBILE = 5001

#VECTOR_DB_URL = "http://localhost:6000/search" # Use in testing outside container
VECTOR_DB_URL = "http://vector_db_server:8000/search"
#SERVER_PORT_DB = 6000

#VECTOR_DB_SERVER_IP = "edgemind_vector_db_server"   # Service name
#VECTOR_BD_SERVER_PORT = 8000

model_path = "/mydir/saved_LLM_model"
#model_path = "./saved_LLM_model"   # Use in testing outside container

# Define the prompt template for the assistant
prompt_template = """
<|system|>
 
You are an expert assistant that answers to the user query.
 
You are given some extracted parts relevant to the user query.
 
If you don't know the answer, just say "I don't know." Don't try to make up an answer.
 
It is very important that you ALWAYS answer the question in the same language the question is in. Remember to always do that.
 
Use only the following pieces of context to answer the question at the end.
 
<|end|>
 
<|user|>
 
Context: {context}
 
Question is below. Remember to answer in the same language:
 
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
        message = "I couldn't find relevant information for your query. Could you provide more details?" 

    # Generate output using the text generation model
    output = pipe(message, **generation_args)
    generated_text = output[0]['generated_text']
    print(f"Generated response before cleanup: {generated_text}")

    # Filter out the retrieved texts from the generated response
    #final_generated_text = filter_generated_text(generated_text, response)
    final_generated_text = filter_generated_text(generated_text, db_query_result)
    print(f"Final generated response: {final_generated_text}")

    return final_generated_text


def start_server():
    """Initialize the server. \n
    Create and start the socket server. \n
    Start listening for client connections."""
         
    # Load the embedding model once
    #embedding_function = SentenceTransformer('all-mpnet-base-v2')

    # Load the text generation model and tokenizer
    model = AutoModelForCausalLM.from_pretrained(model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    print("Model loaded successfully!")

    # Create a text generation pipeline
    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
    )

    # Define generation arguments for high-quality responses
    generation_args = {
        "max_new_tokens": 500,
        "return_full_text": False,
        "temperature": 0.5,  # Adjust for more creativity
        "do_sample": True,    # Enable sampling for varied output
    }


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

            # Get query question from client
            user_question = mobile_socket.recv(1024).decode('utf-8')

            if not user_question:
                print("No data was received.")
                return
            print(f"Received from client: {user_question}")
            now=datetime.now()
            print(now)

            # Data to be sent
            post_data = {
                'question': user_question
            }

            # Defining content type for the payload
            headers = {'Content-type': 'application/json'}
            # Post the user question to the vector database server and get the query result as response
            response = requests.post(VECTOR_DB_URL, data=json.dumps(post_data), headers=headers)
            response_as_json = response.json()
            db_result = response_as_json['message']

            # Query the llm
            llm_result = query_llm(generation_args, pipe, db_result, user_question)
            #llm_result = f"The result from the database: {result}"

            # Send the llm query result to the mobile app
            mobile_socket.sendall(llm_result.encode('utf-8'))
            mobile_socket.close()
            print("Connection closed with the mobile application")

        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    start_server()