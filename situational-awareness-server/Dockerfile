FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:6501", "extracted_text_processing:app"]