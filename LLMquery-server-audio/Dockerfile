# The Dockerfile for the audio generating LLM server
FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

#COPY . .

EXPOSE 5001 6001

CMD ["python3", "-u", "llm-handling-server.py"]
