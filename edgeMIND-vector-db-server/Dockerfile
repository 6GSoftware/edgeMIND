FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN pip install eco2ai

#COPY . .

CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:8000", "vector_db_server:app"]