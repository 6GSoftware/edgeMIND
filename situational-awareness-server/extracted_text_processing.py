"""Extracted Data Processing: Sentence Tokenizing

This module is responsible for tokenizing sentences from the extracted data provided by upstream processing services.

How this module works:
- The extracted data is received from upstream services and tokenized using NLTK's sentence tokenizer.
- The cleaned and tokenized sentences are saved to the Pre_processed_text.txt file and forwarded to the
  situational awareness module for topic classification and vectorization.
"""

import socket
import nltk
from sentence_transformers import SentenceTransformer
import re
from situational_awareness_faiss import send_new_data_to_database
#from dotenv import load_dotenv

# Loads the environment variables from the .env file
#load_dotenv()

HOST = "0.0.0.0"
PORT = 6500
TAG = "extracted_text_processing:  "

output_file_path = './Pre_processed_text.txt'

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    print("[NLTK] 'punkt' not found. Downloading now...")
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
    with open(output_file_path, 'a', encoding='utf-8') as output_file:
        for sentence in cleaned_sentences:
            output_file.write(f"{sentence}\n")
            processed_file_content = processed_file_content + f"{sentence}\n"
            #output_file.write(f"Embedding: {np.array2string(embedding, precision=4, separator=',')}\n\n")

    print(f"{TAG} Cleaned sentences saved to {output_file_path}")

    return processed_file_content


def receive_all(sock):
    data = b''
    while True:
        print("Receiving data...")
        part = sock.recv(4096)
        if not part:
            break
        data += part
    return data.decode("utf-8")


def run_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"{TAG} Server listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            with conn:
                print(f"{TAG} Connection established with {addr}")

                processed_file_contents = receive_all(conn)
                if not processed_file_contents:
                    print(f"{TAG} Connection closed by {addr}")
                    continue

                conn.sendall("Data was received!".encode('utf-8'))
                print(f"{TAG} Response sent")

                processed_file_contents = process_extracted_texts(processed_file_contents)
                send_new_data_to_database([
                    line + '\n' for line in processed_file_contents.split('\n') if line.strip()
                ])

if __name__ == "__main__":
    run_server()