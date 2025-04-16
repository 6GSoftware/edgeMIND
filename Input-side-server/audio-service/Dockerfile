FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

# Install git
RUN apt-get update && apt-get install -y git

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "-u", "app.py"]