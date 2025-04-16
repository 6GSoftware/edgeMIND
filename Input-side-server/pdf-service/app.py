from flask import Flask, request
import os
import threading

from pdf_processing import process_pdf_files
from extracted_text_processing import process_extracted_texts
from situational_awareness_faiss import vectorize_and_save_to_vector_db

TAG = "pdf_service: "

BASE_DIRECTORY = "./"
PDF_DIRECTORY = os.path.join(BASE_DIRECTORY, "pdfs/")
os.makedirs(PDF_DIRECTORY, exist_ok=True)

app = Flask(__name__)

def process_file(**kwargs):
    file_name = kwargs.get('file_name')

    # Process step 2: Extract text from the file and save the exracted text to appropriate file.
    print(f"{TAG} Processing PDF file...")
    process_pdf_files(file_name)
    print(f"{TAG} Appending new PDF data to texts_pdfs.txt")
    print(f"{TAG} Text extracted from the file and saved to appropriate files")
    
    # Process step 3: Process the data that was extracted from the uploaded file:
    # tokenize sentences and save them to appropriate file
    process_extracted_texts()
    print(f"{TAG} Text tokenized, embeddings created and saved to appropriate file")
    
    # Process step 4:
    vectorize_and_save_to_vector_db()
    print(f"{TAG} The texts have been vectorized and saved to the faiss index")
    
    print(f"{TAG} Process complete!\n")

def save_file(file_name, file):
    """Save the uploaded file to an appropriate directory"""

    # Determine file type and set the appropriate directory
    directory = PDF_DIRECTORY

    if directory is None:
        print("Unknown file type. Skipping file.")
        return 'Unknown filetype'

    # Create full file path
    file_path = os.path.join(directory, file_name)

    # Save received file to appropriate folder
    file.save(f"{file_path}")
    print(f"{TAG} File saved successfully at: {file_path}")

    return 'File uploaded and saved successfully'

@app.route('/upload_pdf', methods=['POST'])
def upload_file():
    """Handle http POST request from the client and receive a file."""

    if 'file' not in request.files:
        return {'message': 'No file part'}, 400

    file = request.files['file']
    if file.filename == '':
        return {'message': 'No selected file'}, 400
    
    file_name = file.filename

    # Save the uploaded file
    response_message = save_file(file_name, file)

    # Process the file in another thread
    thread = threading.Thread(target=process_file, kwargs={
                    'file_name': file_name})
    thread.start()

    # Send a response message to the mobile app
    return {'message': response_message}, 200


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)