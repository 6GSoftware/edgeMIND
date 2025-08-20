# The Dockerfile for the audio generating LLM server
FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

#RUN pip install eco2ai

COPY . .

CMD ["python3", "-u", "llm_handling_server.py"]