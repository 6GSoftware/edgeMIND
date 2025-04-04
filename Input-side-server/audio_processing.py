""" Audio file processing module

This module is responsible for transcribing the audio files sent to the Input side of the edgeMIND framework.

How this module works:
The name of the audio file to be transcribed is sent to the transcribe_audio_files method and the audio
file is transcribed with the whisper model. After that the transcription is saved in the texts_audio.txt file
and the name of the file is saved in the processed_files.txt file to prevent processing the same file again.
"""

import os
import whisper  # Whisper model for audio transcription

TAG = "audio_processing:  "

# Folder with audio files
audio_folder = './Audio'
transcription_file_path = os.path.join(audio_folder, 'texts_audio.txt')  # File to store transcriptions
processed_files_path = os.path.join(audio_folder, 'processed_files.txt')  # File to track processed files

def transcribe_audio_files(audio_folder, processed_files_path):
    """Load and process audio files, returning the transcriptions."""
    
    # Step 1: Initialize Whisper model for transcription
    model_whisper = whisper.load_model("base")
    print(f"{TAG} Whisper model loaded successfully.")
    
    texts = []

    # Step 2: Read existing processed file names to avoid reprocessing
    processed_files = set()
    if os.path.exists(processed_files_path):
        with open(processed_files_path, 'r', encoding='utf-8') as f:
            for line in f:
                processed_files.add(line.strip())  # Each line represents a processed file name

    # Step 3: Transcribe audio files and append transcriptions to texts
    for audio_file in os.listdir(audio_folder):
        if audio_file.endswith('.mp3') or audio_file.endswith('.wav'):
            if audio_file in processed_files:
                print(f"Skipping already processed file: {audio_file}")
                continue

            audio_path = os.path.join(audio_folder, audio_file)
            print(f"Processing file: {audio_path}")
            
            # Transcribe the audio file using Whisper
            try:
                result = model_whisper.transcribe(audio_path)
                transcription = result['text']
                print(f"Transcription for {audio_file}: {transcription}")
                
                texts.append((audio_file, transcription))  # Append the audio file name and transcription
            
            except Exception as e:
                print(f"Error transcribing {audio_file}: {e}")
            
    return texts


def process_audio_files():
    # Step 1: Process audio files and avoid reprocessing already transcribed files
    transcriptions = transcribe_audio_files(audio_folder, processed_files_path)
    
    if not transcriptions:
        print(f"{TAG} No new transcriptions were generated.")
    else:
        # Step 2: Save new transcriptions and update the processed files list
        with open(transcription_file_path, 'a', encoding='utf-8') as f:
            for audio_file, transcription in transcriptions:
                f.write(f"Transcription for {audio_file}:\n")  # Save the audio file name
                f.write(transcription + '\n\n')  # Save the transcription

        # Step 3: Update processed files list
        with open(processed_files_path, 'a', encoding='utf-8') as f:
            for audio_file, _ in transcriptions:
                f.write(audio_file + '\n')  # Save the audio file name to avoid reprocessing

        print(f"{TAG} Processing complete. New transcriptions saved to '{transcription_file_path}', and processed files updated.")