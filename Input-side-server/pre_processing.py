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
#from watchdog.observers import Observer
#from watchdog.events import FileSystemEventHandler
from audio_processing import process_audio_files
from pdf_processing import process_pdf_files
from image_processing import process_image_files

TAG = "pre_processing:  "

# Define the folder paths for audio, PDFs, and images
audio_folder = './Audio'
pdfs_folder = './pdfs'
images_folder = './Pictures'

# Define paths to the text files
audio_text_file = os.path.join(audio_folder, 'texts_audio.txt')
pdfs_text_file = os.path.join(pdfs_folder, 'texts_pdfs.txt')
images_text_file = os.path.join(images_folder, 'texts_Image.txt')
combined_text_file = './emultimodal_extracted_data.txt'


def update_combined_text_file():
    """Function to append new content from individual text files to the combined file."""
    
    with open(combined_text_file, 'w', encoding='utf-8') as outfile:
        # Append audio text
        if os.path.exists(audio_text_file):
            with open(audio_text_file, 'r', encoding='utf-8') as infile:
                outfile.write(f"--- Audio Text ---\n")
                outfile.write(infile.read())
                outfile.write("\n\n")
        
        # Append PDF text
        if os.path.exists(pdfs_text_file):
            with open(pdfs_text_file, 'r', encoding='utf-8') as infile:
                outfile.write(f"--- PDF Text ---\n")
                outfile.write(infile.read())
                outfile.write("\n\n")
        
        # Append image text
        if os.path.exists(images_text_file):
            with open(images_text_file, 'r', encoding='utf-8') as infile:
                outfile.write(f"--- Image Text ---\n")
                outfile.write(infile.read())
                outfile.write("\n\n")
    
    print(f"{TAG} Combined file updated with the latest content from all individual text files.")


def pre_process_uploaded_file(file_name, file_type):

    # Process the file according to its file type
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

    # Once processing is done, update the combined text file
    update_combined_text_file()