""" Audio file processing module

This module is responsible for transcribing the audio files sent to the Input side of the edgeMIND framework.

How this module works:
The name of the audio file to be transcribed is sent to the transcribe_audio_files method and the audio
file is transcribed with the whisper model. After that the transcription is saved in the texts_audio.txt file
and the name of the file is saved in the processed_files.txt file to prevent processing the same file again.
"""

import os
import whisper  # Whisper model for audio transcription
from dotenv import load_dotenv

# Loads the environment variables from the .env file
load_dotenv()

TAG = "audio_processing:  "

# Folder with audio files
audio_folder = './Audio'

combined_text_file = './test_emultimodal_extracted_data.txt'


def transcribe_audio_files(audio_folder, new_file):
#def transcribe_audio_files(audio_folder, processed_files_path, new_file):
    """Load and process audio files, returning the transcriptions."""
    
    # Step 1: Initialize Whisper model for transcription
    model_whisper = whisper.load_model("base")
    print(f"{TAG} Whisper model loaded successfully.")
    
    texts = []

    # Step 3: Transcribe audio files and append transcriptions to texts
    if new_file.endswith('.mp3') or new_file.endswith('.wav'):

        new_file_path = os.path.join(audio_folder, new_file)
        print(f"{TAG} Processing file: {new_file_path}")
        
        # Transcribe the audio file using Whisper
        try:
            result = model_whisper.transcribe(new_file_path)
            transcription = result['text']
            print(f"Transcription for {new_file}: {transcription}")
            
            texts.append((new_file, transcription))  # Append the audio file name and transcription
        
        except Exception as e:
            print(f"{TAG} Error transcribing {new_file}: {e}")
            
    return texts


def process_audio_files(new_file):
    # Step 1: Process audio files and avoid reprocessing already transcribed files
    transcriptions = transcribe_audio_files(audio_folder, new_file)
    
    if not transcriptions:
        print(f"{TAG} No new transcriptions were generated.")
    else:
        # Step 2: Save new transcriptions and update the processed files list
        with open(combined_text_file, 'a', encoding='utf-8') as f:
            for audio_file, transcription in transcriptions:
                f.write(f"Transcription for {audio_file}:\n")  # Save the audio file name
                f.write(transcription + '\n\n')  # Save the transcription

    print(f"{TAG} Processing complete. New transcriptions saved to '{combined_text_file}', and processed files updated.")