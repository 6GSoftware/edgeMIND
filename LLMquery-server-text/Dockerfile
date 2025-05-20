# The Dockerfile for the text generating LLM server
FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "600", "-b", "0.0.0.0:6000", "llm_handling_server:app"]
