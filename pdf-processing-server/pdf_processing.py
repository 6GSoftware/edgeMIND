""" PDF file processing module

This module is responsible for extracting texts from the PDF files sent to the Input side of the edgeMIND framework.

How this module works:
The name of the PDF file is given to the process_pdf_files method and the texts in the PDF file are extracted with
Llamaparse. After that the extracted texts are saved in the texts_pdfs.txt file and the name of the file is saved in the 
processed_files.txt file to prevent processing the same file again.
"""

import os
from llama_parse import LlamaParse
from dotenv import load_dotenv

# Loads the environment variables from the .env file
load_dotenv()

TAG = "pdf_processing:  "

# Set the folder path for the PDF files
pdf_folder = "./pdfs"

combined_text_file = './emultimodal_extracted_data.txt'

LLAMAPARSE_API_KEY = os.environ.get("LLAMAPARSE_API_KEY", None)
if LLAMAPARSE_API_KEY is None: 
    raise IOError("API key missing")


# Set up LlamaParse with the API key and desired output format
parser = LlamaParse(
    api_key=LLAMAPARSE_API_KEY,  
    result_type="markdown"
)

# Function to process the new pdf file
def process_pdfs_with_llamaparse(new_file):
    """Use LlamaParse to extract text from PDF files, skipping already processed files."""
    texts = []
    newly_processed_files = []

    if new_file.endswith(".pdf"):
        pdf_path = os.path.join(pdf_folder, new_file)
        try:
            print(f"{TAG} Started parsing the file: {new_file}")
            extracted_documents = parser.load_data(pdf_path)

            # Log the number of documents extracted
            print(f"{TAG} Extracted {len(extracted_documents)} documents from {new_file}")

            # Extract text from each document
            for doc in extracted_documents:
                texts.append((new_file, doc.text))  # Store the PDF file name with the text

            # Add the successfully processed file to the list
            newly_processed_files.append(new_file)

        except Exception as e:
            print(f"{TAG} Error while parsing the file '{pdf_path}': {e}")

    return texts, newly_processed_files


def process_pdf_files(new_file):
    """Process PDFs and save extracted data to a .txt file"""

    # Process PDF files and extract text
    extracted_texts, newly_processed_files = process_pdfs_with_llamaparse(new_file)

    combined_text = ""
    for pdf_file, text in extracted_texts:
        if isinstance(text, str):
            combined_text += f"Response for {pdf_file}:\n"
            combined_text += text + "\n\n"

    return combined_text
