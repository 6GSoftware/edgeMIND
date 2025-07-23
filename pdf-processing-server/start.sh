#!/bin/sh

# Start old file cleanup script in background
python3 /app/file_management.py &

# Start the main program, i.e. audio file processing program (foreground so container stays alive)
gunicorn --preload -w 4 --threads 1 --timeout 3600 -b 0.0.0.0:5004 pdf_server:app