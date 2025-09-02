# The Dockerfile for the audio generating LLM server
FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN pip install eco2ai

COPY . .

#CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:5001", "llm_handling_server:app"]