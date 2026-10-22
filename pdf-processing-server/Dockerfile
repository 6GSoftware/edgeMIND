FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY pdfs /app/pdfs
#COPY file_management.py /app/
COPY pdf_processing.py /app/
COPY pdf_server.py /app/
COPY .env /app/

#CMD ["sh", "./start.sh"]
CMD ["python", "pdf_server.py"]