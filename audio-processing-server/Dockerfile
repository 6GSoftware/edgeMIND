FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

# Install system dependencies in one RUN to reduce layers
RUN apt-get update && apt-get install -y git ffmpeg && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY . .

CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "600", "-b", "0.0.0.0:5003", "audio_server:app"]
