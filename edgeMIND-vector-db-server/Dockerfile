FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN pip install eco2ai

COPY . .

ENV PYTHONPATH=/app

RUN apt-get update && \
    apt-get install -y curl tcpdump procps && \
    rm -rf /var/lib/apt/lists/*

EXPOSE 8000

# CMD ["python", "vector_db_server.py"]
CMD ["python", "-u", "vector_db_server.py"]


# CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:8000", "vector_db_server:app"]