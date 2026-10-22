# The Dockerfile for the audio generating LLM server
FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "llm_handling_server.py"]