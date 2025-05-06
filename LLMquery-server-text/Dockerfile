# The Dockerfile for the text generating LLM server
FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000 6000

CMD ["python3", "-u", "llm-handling-server.py"]
