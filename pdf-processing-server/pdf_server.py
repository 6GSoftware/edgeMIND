from flask import Flask, request
import os
import threading
import socket

from pdf_processing import process_pdf_files

HOST = "situational_awareness_server"
PORT = 6500

TAG = "pdf_service: "

BASE_DIRECTORY = "./"
PDF_DIRECTORY = os.path.join(BASE_DIRECTORY, "pdfs/")
os.makedirs(PDF_DIRECTORY, exist_ok=True)

app = Flask(__name__)

def process_file(**kwargs):
    file_name = kwargs.get('file_name')

    # Extract text from the file and save the exracted text to appropriate file.
    print(f"{TAG} Processing PDF file...")
    processed_file_content = process_pdf_files(file_name)

    send_to_extracted_text_processing(processed_file_content)

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


def send_to_extracted_text_processing(processed_file_content):

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            s.sendall(processed_file_content.encode('utf-8'))
            s.shutdown(socket.SHUT_WR)
            response = s.recv(1024)
            print(f"{TAG}Response from the processor: {response.decode('utf-8')}")
    except Exception as e:
        print(f"{TAG}Connection failed: {e}")


def format_processed_content(extracted_texts):
    """
    Takes a list of (filename, text) tuples and converts it into a readable string.
    """
    output = ""
    for filename, text in extracted_texts:
        output += f"Response for {filename}:\n"
        for line in text.strip().split('\n'):
            if line.strip():
                output += f"- {line.strip()}\n"
    return output

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)