FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN echo "setuptools<81" > /constraints.txt && \
    PIP_CONSTRAINT=/constraints.txt pip install --no-cache-dir -r requirements.txt

#COPY file_management.py /app/
COPY audio_server.py /app/
COPY audio_processing.py /app/
COPY Audio /app/Audio/

CMD ["python", "audio_server.py"]
#CMD ["sh", "./start.sh"]
