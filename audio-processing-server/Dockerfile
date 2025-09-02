FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

# Install system dependencies in one RUN to reduce layers
RUN apt-get update && apt-get install -y git ffmpeg && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

#COPY . .
#RUN chmod +x start.sh

#ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

#CMD ["python", "audio_server.py"]
#CMD ["gunicorn", "--preload", "-w", "1", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:5003", "audio_server:app"]
CMD ["sh", "./start.sh"]
