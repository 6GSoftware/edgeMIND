# The Dockerfile for the text generating LLM server
FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

#COPY . .

CMD ["python", "llm_handling_server.py"]
#CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:5000", "llm_handling_server:app"]

