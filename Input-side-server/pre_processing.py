""" Module for deciding the processing and text extraction method based on the file type

This module is responsible for deciding which processing and text extraction method is used to process the
file sent to the Input side of the edgeMIND framework.

How this module works:
The name of the PDF, image or audio file is given to the pre_process_uploaded_file method, which decides
the processing and text extraction method for the file based on the type of the file. After the processing
of the file, the contents of the files containing the extracted texts are combined to one single file,
emultimodal_extracted_data.txt file. 
"""

import os
import time
from audio_processing import process_audio_files
from pdf_processing import process_pdf_files
from image_processing import process_image_files
from dotenv import load_dotenv

# Loads the environment variables from the .env file
load_dotenv()

TAG = "pre_processing:  "


def pre_process_uploaded_file(file_name, file_type):
    """Process the upploaded file according to its file type"""
    
    if file_type == "audio":
        print(f"{TAG} Processing audio file...")
        process_audio_files(file_name)
        print(f"{TAG} Appending new audio data to texts_audio.txt")
    elif file_type == "pdf":
        print(f"{TAG} Processing PDF file...")
        process_pdf_files(file_name)
        print(f"{TAG} Appending new PDF data to texts_pdfs.txt")
    elif file_type == "image":
        print(f"{TAG} Processing image file...")
        process_image_files(file_name)
        print(f"{TAG} Appending new image data to texts_Image.txt")