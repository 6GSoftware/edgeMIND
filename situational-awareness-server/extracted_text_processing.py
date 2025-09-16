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
from situational_awareness_faiss import create_metadata_for_text_chunks, create_topics, send_new_data_to_database
import logging
from flask import Flask, request, jsonify


logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

HOST = "0.0.0.0"
TAG = "extracted_text_processing:  "
VECTOR_DB_URL_SEARCH = "http://vector_db_server:8000/search"
VECTOR_DB_ERROR_MSG = "An error occurred in searching the vector database."

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



def process_user_question_and_save_to_file(question):
    logging.info("Pre process the user question.\n")
    question = preprocess_sentence(question)

    with open(pre_processed_text_file_path, 'a', encoding='utf-8') as output_file:
        output_file.write(question)

    return question



def search_db_based_on_usr_question_topic(usr_question_topic):
    logging.info("Get matching topics and their text chunks based on the topic that was created for the user question.\n")
    post_data = {
        'question': usr_question_topic
    }

    headers = {'Content-type': 'application/json'}
    # Get results from vector database based on the created topic for the user question
    response = requests.post(VECTOR_DB_URL_SEARCH, data=json.dumps(post_data), headers=headers)
    response_as_json = response.json()

    logging.info(f"Response from db server: {response_as_json}\n")

    if response_as_json['status'] == 'error':
        return "error"
    
    db_result = str(response_as_json['message'])

    return db_result



@app.route('/process_user_question', methods=['POST'])
def handle_user_question():
    try:
        req_data = request.json
        question = req_data["question"]

        if not question:
            logging.info(f"{TAG} No data received.")
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        question = process_user_question_and_save_to_file(str(question))

        all_chunks = create_topics([question])
        logging.info(f"chunks: {str(all_chunks)}")
        metadata = create_metadata_for_text_chunks(all_chunks)

        metadata = metadata.pop()
        logging.info("Topic that was created: " + metadata["topic"] + "\n")

        db_result = search_db_based_on_usr_question_topic(metadata["topic"])

        if db_result == "error":
            return jsonify({'status': 'error', 'message': VECTOR_DB_ERROR_MSG}), 500

        res_as_json = {
            "db_result": db_result,
            "usr_question_metadata": metadata
        }

        logging.info(f"Results from db based on user's question: {db_result}")
        logging.info("Metadata:\ntimestamp: " + str(metadata["timestamp"]) + "\ntopic: " + str(metadata["topic"]) + "\ntext: " + str(metadata["text"]))

        return jsonify({"status": "success", "message": res_as_json})

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

        #logging.info(f"{TAG} AFTER: {processed_file_contents}")

        processed_file_contents = process_extracted_texts(processed_file_contents)

        #logging.info(f"{TAG} BEFORE: {processed_file_contents}")

        send_new_data_to_database([
            line + '\n' for line in processed_file_contents.split('\n') if line.strip()
        ])

        return jsonify({"status": "success", "message": "Data processed"})

    except Exception as e:
        logging.error(f"{TAG} Error while processing: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500