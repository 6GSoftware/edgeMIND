FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip

RUN pip install --default-timeout=300 \
    torch==2.6.0 \
    torchvision==0.21.0 \
    transformers==4.45.1

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

#CMD ["python", "image_server.py"]
#CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:5002", "image_server:app"]
CMD ["sh", "./start.sh"]