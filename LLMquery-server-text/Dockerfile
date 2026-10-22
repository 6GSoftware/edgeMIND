# The Dockerfile for the text generating LLM server
FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir "accelerate>=0.26.0"

COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 5007

CMD ["python", "llm_handling_server.py"]