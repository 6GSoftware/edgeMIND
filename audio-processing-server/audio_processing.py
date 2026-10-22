""" Audio file processing module

This module is responsible for transcribing the audio files sent to the Input side of the edgeMIND framework.

How this module works:
The name of the audio file to be transcribed is sent to the transcribe_audio_files method and the audio
file is transcribed with the whisper model. After that the transcription is saved in the texts_audio.txt file
and the name of the file is saved in the processed_files.txt file to prevent processing the same file again.
"""

from concurrent.futures import ProcessPoolExecutor
import os
import whisper  # Whisper model for audio transcription
import logging

logging.basicConfig(level=logging.INFO)

TAG = "audio_processing:  "

# Folder with audio files
audio_folder = './Audio'


model_whisper = None


def init_model():
    global model_whisper
    model_whisper = whisper.load_model("base")
    (f"{TAG} Whisper model loaded successfully.")


def transcribe_audio_files(new_file):
    """Load and process audio files, returning the transcriptions."""
    
    global model_whisper

    texts = []

    # Step 3: Transcribe audio files and append transcriptions to texts
    if new_file.endswith('.mp3') or new_file.endswith('.wav'):

        new_file_path = os.path.join(audio_folder, new_file)
        logging.info(f"{TAG} Processing file: {new_file_path}")
        
        # Transcribe the audio file using Whisper
        try:
            result = model_whisper.transcribe(new_file_path)
            transcription = result['text']
            logging.info(f"Transcription for {new_file}: {transcription}")
            
            texts.append((new_file, transcription))  # Append the audio file name and transcription
        
        except Exception as e:
            logging.info(f"{TAG} Error transcribing {new_file}: {e}")
            
    return texts


executor = ProcessPoolExecutor(max_workers=1, initializer=init_model)

def process_audio_files(new_file):
    """Process audio files and return transcriptions as a formatted string"""

    future = executor.submit(transcribe_audio_files, new_file)
    transcriptions = None

    try:
        transcriptions = future.result()
    except Exception as e:
        logging.info("An error occurred in transcribing the audio file:\n" + str(e))
        return ""   # Return empty string if nothing was processed

    if not transcriptions:
        logging.info(f"{TAG} No new transcriptions were generated.")
        return ""  # Return empty string if nothing was processed

    # Step 2: Build the combined text
    combined_text = ""
    for audio_file, transcription in transcriptions:
        combined_text += f"Transcription for {audio_file}:\n"
        combined_text += transcription + '\n\n'

    logging.info(f"{TAG} Processing complete. New transcriptions ready in memory.")
    return combined_text