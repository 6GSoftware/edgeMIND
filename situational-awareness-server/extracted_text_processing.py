"""Extracted Data Processing: Sentence Tokenizing

This module is responsible for tokenizing sentences from the extracted data provided by upstream processing services.

How this module works:
- The extracted data is received from upstream services and tokenized using NLTK's sentence tokenizer.
- The cleaned and tokenized sentences are saved to the Pre_processed_text.txt file and forwarded to the
  situational awareness module for topic classification and vectorization.
"""

import nltk
import re
from situational_awareness_faiss import send_new_data_to_database, send_llm_result_to_temp_database
import logging
from flask import Flask, request, jsonify


logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

HOST = "0.0.0.0"
TAG = "extracted_text_processing:  "

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
        req_json = request.get_json()
        processed_file_contents = req_json.get("data", "")
        file_type = req_json.get("file_type", "text")

        if not processed_file_contents:
            logging.info(f"{TAG} No data received.")
            return jsonify({"status": "error", "message": "No data received"}), 400

        logging.info(f"{TAG} AFTER: {processed_file_contents}")

        processed_file_contents = process_extracted_texts(processed_file_contents)

        logging.info(f"{TAG} BEFORE: {processed_file_contents}")

        send_new_data_to_database([
            line + '\n' for line in processed_file_contents.split('\n') if line.strip()
        ], file_type)

        return jsonify({"status": "success", "message": "Data processed"})

    except Exception as e:
        logging.error(f"{TAG} Error while processing: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6501, debug=True)