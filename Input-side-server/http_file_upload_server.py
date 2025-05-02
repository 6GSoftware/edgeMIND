""" Flask server for receiving the audio, image or pdf file that was sent from the edgeMIND Input side mobile app.

This Flask server is responsible for receiving the audio, image or pdf file sent from the edgeMIND mobile app as an
http request, and for orchestrating the processing of this file.

How this module works:
The file is received in an http request and saved to an appropriate file depending on the type of the file.
Then the other modules handling the processing of the file are called in order, to take care of the other steps
in the file processing process.
"""

from flask import Flask, request
import os
import threading
import socket



from pre_processing import pre_process_uploaded_file


app = Flask(__name__)

INPUT_SERVER_IP = os.environ.get("INPUT_SERVER_IP", None)
if INPUT_SERVER_IP is None: 
    raise IOError("Server IP missing")

TAG = "file_upload_server:  "
BASE_DIRECTORY = "./"

# Directory paths for different file types
IMAGE_DIRECTORY = os.path.join(BASE_DIRECTORY, "Pictures/")
PDF_DIRECTORY = os.path.join(BASE_DIRECTORY, "pdfs/")
AUDIO_DIRECTORY = os.path.join(BASE_DIRECTORY, "Audio/")

# Ensure directories exist
os.makedirs(IMAGE_DIRECTORY, exist_ok=True)
os.makedirs(PDF_DIRECTORY, exist_ok=True)
os.makedirs(AUDIO_DIRECTORY, exist_ok=True)
print(f"{TAG} Directories created or already exist.")


def get_file_type(file_name):
   """Determine the file type based on the file extension"""

   file_name = file_name.lower()
   if file_name.endswith((".jpg", ".jpeg", ".png")):
       return "image"
   elif file_name.endswith(".pdf"):
       return "pdf"
   elif file_name.endswith((".mp3",".mpeg")):
       return "audio"
   
   return None


def get_directory_for_file_type(file_type):
   """Get the directory for a given file type"""

   if file_type == "image":
       return IMAGE_DIRECTORY
   elif file_type == "pdf":
       return PDF_DIRECTORY
   elif file_type == "audio":
       return AUDIO_DIRECTORY

   return None


def process_file(**kwargs):
    file_name = kwargs.get('file_name')
    file_type = kwargs.get('file_type')

    processed_file_content = pre_process_uploaded_file(file_name, file_type)
    
    print(f"{TAG} Text extracted from the file and saved to appropriate files")
    print(f"{TAG} The content of the processed file is now: {processed_file_content}")

    send_to_extracted_text_processing(processed_file_content)


def save_file(file_name, file, file_type):
    """Save the uploaded file to an appropriate directory"""

    # Determine file type and set the appropriate directory
    directory = get_directory_for_file_type(file_type)

    if directory is None:
        print("Unknown file type. Skipping file.")
        return 'Unknown filetype'

    # Create full file path
    file_path = os.path.join(directory, file_name)

    # Save received file to appropriate folder
    file.save(f"{file_path}")
    print(f"{TAG} File saved successfully at: {file_path}")

    return 'File uploaded and saved successfully'


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle http POST request from the client and receive a file."""

    if 'file' not in request.files:
        return {'message': 'No file part'}, 400

    file = request.files['file']
    if file.filename == '':
        return {'message': 'No selected file'}, 400
    
    file_name = file.filename

    # Determine the type of the file
    file_type = get_file_type(file_name)

    # Save the uploaded file
    response_message = save_file(file_name, file, file_type)

    # Process the file in another thread
    thread = threading.Thread(target=process_file, kwargs={
                    'file_name': file_name, 'file_type': file_type})
    thread.start()

    # Send a response message to the mobile app
    return {'message': response_message}, 200

def send_to_extracted_text_processing(processed_file_content):
    HOST = "172.17.0.1"
    PORT = 6500

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            s.sendall(processed_file_content.encode('utf-8'))
            response = s.recv(1024)
            print(f"{TAG}Response from the processor: {response.decode('utf-8')}")
    except Exception as e:
        print(f"{TAG}Connection failed: {e}")


if __name__ == '__main__':
    app.run(host=INPUT_SERVER_IP, port=5000)  # TODO Change the port to be 7000!