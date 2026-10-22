FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

RUN apt-get update && \
    apt-get install -y curl tcpdump procps && \
    rm -rf /var/lib/apt/lists/*

EXPOSE 8000

CMD ["python", "-u", "vector_db_server.py"]