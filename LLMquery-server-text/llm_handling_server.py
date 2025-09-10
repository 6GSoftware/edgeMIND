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

#from dotenv import load_dotenv
import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from langchain.prompts import PromptTemplate
from datetime import datetime
import re
import requests
from flask import Flask, request, jsonify
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

@app.route('/health')
def health():
    return {'status': 'ok'}

# Set the random seed for reproducibility
torch.random.manual_seed(0)

VECTOR_DB_URL = "http://vector_db_server:8000/search"
INPUT_LAYER_URL = "http://situational_awareness_server:6501/process_user_question"

#loppu = "/process_generated_response"

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
        return ""

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
    try:
        user_question = request.json.get('question', '')
        if not user_question:
            return jsonify({'status': 'error', 'message': 'No question provided'}), 400

        logging.info(f"Received question: {user_question}")
        now = datetime.now()
        logging.info(now)

        # Data to be sent
        post_data = {
            'question': user_question
        }

        # Defining content type for the payload
        headers = {'Content-type': 'application/json'}
        # Post the user question to the vector database server and get the query result as response
        #response = requests.post(VECTOR_DB_URL, data=json.dumps(post_data), headers=headers)
        #response_as_json = response.json()
        ##db_result = response_as_json['message']
        #logging.info(f"response from db server: {response_as_json}")

        response = requests.post(INPUT_LAYER_URL, data=json.dumps(post_data, headers=headers))
        response_as_json = response.json()

        #if response_as_json['status'] == 'error':
        if response_as_json['status'] == 'error':
            logging.info("An error occurred in generating the topic and/or searchin the vector database")
            return jsonify({'status': 'error', 'message': response_as_json['message']}), 500

        whole_response = response_as_json['message']
        db_result = whole_response['db_result']

        # Query the llm
        llm_result = query_llm(generation_args, pipe, db_result, user_question)
        #llm_result = f"The result from the database: {result}"

        if llm_result == "":
            exception_message = "I couldn't find relevant information for your query. Could you provide more details?"
            return jsonify({'status': 'ok', 'message': exception_message})
        
        # Send LLM generated result to input processing layer
        input_post_data = {'data': user_question + ' ' + llm_result}
        logging.info(f"Data to be sent to SA: {json.dumps(input_post_data)}")

        #input_response = requests.post(INPUT_LAYER_URL, data=json.dumps(input_post_data), headers=headers)
        #input_response_as_json = input_response.json()
        #logging.info(f"Received from the input side: {input_response_as_json['status']}, {input_response_as_json['message']}")


        return jsonify({'status': 'ok', 'message': llm_result})

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

#if __name__ == '__main__':
#    socket_thread = threading.Thread(target=start_server, daemon=True)
#    socket_thread.start()
#    app.run(host='0.0.0.0', port=6000)