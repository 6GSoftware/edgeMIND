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
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from langchain.prompts import PromptTemplate
from datetime import datetime
import socket
import re
#import os


# Set the random seed for reproducibility
torch.random.manual_seed(0)

# Server setup
LLM_SERVER_IP = "---"  # Use your own IP address
LLM_SERVER_PORT = 5000

VECTOR_DB_SERVER_IP = "edgemind_vector_db_server"   # Service name
VECTOR_BD_SERVER_PORT = 8000

model_path = "/mydir/saved_LLM_model"

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


def handle_client(client_socket, client_address, generation_args, pipe):
    """Handle a connected client: \n
    - receive query from the client and send it to the vector database server.
    - receive response from the vector database server. Send the response and the user query to the LLM.
    - get a generated response from the LLm and send it back to the client.
    - finally, close client socket connection."""
    # Receive data from the client (up to 1024 bytes)
    data = client_socket.recv(1024)

    if not data:
        print("No data was received.")
        return
    print(f"Received from client: {data.decode('utf-8')}")
    now=datetime.now()
    print(now)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Connect to the vector db handler server and send the query
        s.connect((VECTOR_DB_SERVER_IP, VECTOR_BD_SERVER_PORT))
        s.sendall(data)

        # Receive a response from the server 
        response = s.recv(1024).decode('utf-8')
        #response_as_list = pickle.loads(s.recv(1024))
        #response_as_list = json.loads(s.recv(1024).decode('utf-8'))

    print("Type of the received data: ", type(response))
    print("Received from the vector db handler server:\n", str(response))

    # Prepare response for the client
    if response:
        message = PROMPT.format(context=response,question=data)
    else:
        message = "I couldn't find relevant information for your query. Could you provide more details?"
    '''
    if response_as_list:
        retrieved_texts = "\n".join([
            f"**Topic**: {result['topic']}\n**Timestamp**: {result['timestamp']}\n**Text**: {result['text']}\n"
            for result in response_as_list[:3]
        ])

        print(f"Retrieved relevant info: {retrieved_texts}")
        now=datetime.now()
        print(now)
        
        message = PROMPT.format(context=retrieved_texts,question=data)

    else:
        message = "I couldn't find relevant information for your query. Could you provide more details?"
    '''

    # Generate output using the text generation model
    output = pipe(message, **generation_args)
    generated_text = output[0]['generated_text']
    print(f"Generated response before cleanup: {generated_text}")

    # Filter out the retrieved texts from the generated response
    final_generated_text = filter_generated_text(generated_text, response)
    print(f"Final generated response: {final_generated_text}")

    # Send the cleaned and filtered response back to the client
    client_socket.sendall(final_generated_text.encode('utf-8'))

    # Close the client connection
    client_socket.close()
    print(f"Connection closed with {client_address}")



def start_server():
    """Initialize the server. \n
    Create and start the socket server. \n
    Start listening for client connections."""
         
    # Load the embedding model once
    #embedding_function = SentenceTransformer('all-mpnet-base-v2')


    '''
    # Load the text generation model and tokenizer from Hugging Face Hub
    model = AutoModelForCausalLM.from_pretrained(
        "microsoft/Phi-3.5-mini-instruct", 
        device_map="auto",  # Automatically choose the device
        torch_dtype=torch.float32,  # Use float32 for CPU
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3.5-mini-instruct")
    '''

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


    # Create a socket object
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Bind the socket to the server address and port
    server_socket.bind((LLM_SERVER_IP, LLM_SERVER_PORT))
    
    # Listen for incoming connections (5 connections in the queue)
    server_socket.listen(5)
    print(f"Server is listening on {LLM_SERVER_IP}:{LLM_SERVER_PORT}")

    while True:
        try:
            # Accept an incoming connection
            client_socket, client_address = server_socket.accept()
            print(f"Connection established with {client_address}")

            handle_client(client_socket, client_address, generation_args, pipe)

        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    start_server()