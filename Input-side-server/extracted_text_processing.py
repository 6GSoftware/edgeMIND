""" Extracted data processing: sentence tokenizing and computing embeddings

This module is responsible for tokenizing the sentences and computing sentence embeddings for the data that was
extracted from the audio, image and pdf files sent to the edgeMIND framework Input side.

How this module works:
The extracted data is read from the emultimodal_extracted_data.txt file and tokenized with nltk's sentence tokenizer.
Then, sentence embeddings are computed from the tokenized sentences. The tokenized sentences are then saved to the
Pre_processed_text.txt file.
"""

import nltk
import numpy as np
from sentence_transformers import SentenceTransformer
import re
from dotenv import load_dotenv

# Loads the environment variables from the .env file
load_dotenv()

TAG = "extracted_text_processing:  "

# Load the Sentence Transformer model
model = SentenceTransformer("all-mpnet-base-v2")
# File paths
file_path = './emultimodal_extracted_data.txt'
output_file_path = './Pre_processed_text.txt'


def preprocess_sentence(sentence):
    sentence = sentence.lower()  # Convert to lowercase
    sentence = re.sub(r'\s+', ' ', sentence).strip()  # Remove extra spaces
    return sentence


def process_extracted_texts():
    # Step 1: Read the text file
    with open(file_path, 'r', encoding='utf-8') as file:
        text_data = file.read()

    # Step 2: Tokenize sentences using nltk's sentence tokenizer
    sentences = nltk.tokenize.sent_tokenize(text_data)

    # Step 3: Preprocess each sentence: lowercase and remove extra spaces
    cleaned_sentences = [preprocess_sentence(sentence) for sentence in sentences]

    # Step 4: Compute sentence embeddings
    embeddings = model.encode(cleaned_sentences)

    # Step 5: Save sentences and embeddings to a .txt file
    with open(output_file_path, 'w', encoding='utf-8') as output_file:
        for sentence, embedding in zip(cleaned_sentences, embeddings):
            output_file.write(f"{sentence}\n")
            #output_file.write(f"Embedding: {np.array2string(embedding, precision=4, separator=',')}\n\n")

    print(f"{TAG} Cleaned sentences and embeddings saved to {output_file_path}")