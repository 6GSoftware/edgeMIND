FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

#COPY . .

EXPOSE 6500

CMD ["python", "-u", "extracted_text_processing.py"]