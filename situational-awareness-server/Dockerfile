FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y curl tar && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 6501

ENV PYTHONUNBUFFERED=1

RUN mkdir -p /results

CMD ["python", "extracted_text_processing.py"]