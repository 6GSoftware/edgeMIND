FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN pip install eco2ai

#COPY . .

EXPOSE 8000

CMD ["python3", "-u", "vector-db-server.py"]