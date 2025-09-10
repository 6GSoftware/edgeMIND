"""Extracted Data Processing: Sentence Tokenizing

This module is responsible for tokenizing sentences from the extracted data provided by upstream processing services.

How this module works:
- The extracted data is received from upstream services and tokenized using NLTK's sentence tokenizer.
- The cleaned and tokenized sentences are saved to the Pre_processed_text.txt file and forwarded to the
  situational awareness module for topic classification and vectorization.
"""

import json
import nltk
import re

import requests
from situational_awareness_faiss import do_topic_modeling, send_new_data_to_database, send_llm_result_to_temp_database
import logging
from flask import Flask, request, jsonify


logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

HOST = "0.0.0.0"
TAG = "extracted_text_processing:  "
VECTOR_DB_URL_SEARCH = "http://vector_db_server:8000/search"

pre_processed_text_file_path = './Pre_processed_text.txt'

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    logging.info("[NLTK] 'punkt' not found. Downloading now...")
    nltk.download('punkt_tab')


def preprocess_sentence(sentence):
    sentence = sentence.lower()  # Convert to lowercase
    sentence = re.sub(r'\s+', ' ', sentence).strip()  # Remove extra spaces
    return sentence


def process_extracted_texts(file_content):
    processed_file_content = ""

    # Tokenize sentences using nltk's sentence tokenizer
    sentences = nltk.tokenize.sent_tokenize(file_content)
    #sentences = nltk.tokenize.sent_tokenize(text_data)

    # Preprocess each sentence: lowercase and remove extra spaces
    cleaned_sentences = [preprocess_sentence(sentence) for sentence in sentences]

    # Save embeddings to a .txt file
    with open(pre_processed_text_file_path, 'a', encoding='utf-8') as output_file:
        for sentence in cleaned_sentences:
            output_file.write(f"{sentence}\n")
            processed_file_content = processed_file_content + f"{sentence}\n"
            #output_file.write(f"Embedding: {np.array2string(embedding, precision=4, separator=',')}\n\n")

    logging.info(f"{TAG} Cleaned sentences saved to {pre_processed_text_file_path}")

    return processed_file_content



@app.route('/process_user_question', methods=['POST'])
def handle_user_question():
    try:
        req_data = request.json
        question = req_data["question"]

        if not question:
            logging.info(f"{TAG} No data received.")
            return jsonify({"status": "error", "message": "No data received"}), 400

        question_str = preprocess_sentence(str(question))

        with open(pre_processed_text_file_path, 'a', encoding='utf-8') as output_file:
            output_file.write(question_str)

        data_for_topic_modeling = [question_str]
        metadata = do_topic_modeling(data_for_topic_modeling)

        post_data = {
            'question': metadata["topic"]
        }
        headers = {'Content-type': 'application/json'}

        # Get results from vector database based on the created topic for the user question
        response = requests.post(VECTOR_DB_URL_SEARCH, data=json.dumps(post_data), headers=headers)
        response_as_json = response.json()
        logging.info(f"response from db server: {response_as_json}")

        if response_as_json['status'] == 'error':
            response_to_user = f"An error occurred in searching the vector database: {response_as_json['message']}"
            return jsonify({'status': 'error', 'message': response_to_user}), 500

        db_result = response_as_json['message']

        res_as_json = {
            'db_result': str(db_result),
            'usr_question_metadata': metadata
        }

        return jsonify({"status": "success", "message": res_as_json})

    except Exception as e:
        logging.error(f"{TAG} Error while processing: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/process_generated_response', methods=['POST'])
def handle_LLM_generated_response():
    try:
        req_data = request.json
        llm_result = req_data["data"]

        if not llm_result:
            logging.info(f"{TAG} No data received.")
            return jsonify({"status": "error", "message": "No data received"}), 400

        logging.info(f"Received from llm server\n:{llm_result}\n\n")

        llm_result_str = preprocess_sentence(str(llm_result))
        llm_result_str = llm_result_str.replace("\n", " ")
        logging.info("llm_result pre processed: " + llm_result_str)

        # Save embeddings to a .txt file
        with open(pre_processed_text_file_path, 'a', encoding='utf-8') as output_file:
            output_file.write(llm_result_str)

        #processed_gen_response_content = process_extracted_texts(llm_result)
        #logging.info("Pre processed generated response: " + processed_gen_response_content)

        #processed_gen_response_content = processed_gen_response_content.replace("\n", " ")
        #logging.info("Pre processing round 2 result: " + processed_gen_response_content)

        send_llm_result_to_temp_database(llm_result_str)

        return jsonify({"status": "success", "message": "Data processed"})

    except Exception as e:
        logging.error(f"{TAG} Error while processing: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/process_extracted_texts', methods=['POST'])
def handle_extracted_texts():
    try:
        # Extract data from the HTTP request
        processed_file_contents = request.get_json().get("data", "")

        if not processed_file_contents:
            logging.info(f"{TAG} No data received.")
            return jsonify({"status": "error", "message": "No data received"}), 400

        logging.info(f"{TAG} AFTER: {processed_file_contents}")

        processed_file_contents = process_extracted_texts(processed_file_contents)

        logging.info(f"{TAG} BEFORE: {processed_file_contents}")

        send_new_data_to_database([
            line + '\n' for line in processed_file_contents.split('\n') if line.strip()
        ])

        return jsonify({"status": "success", "message": "Data processed"})

    except Exception as e:
        logging.error(f"{TAG} Error while processing: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500