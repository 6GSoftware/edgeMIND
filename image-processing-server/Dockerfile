FROM python:3.10-slim

WORKDIR /app

RUN pip install --default-timeout=999 \
    torch==2.6.0 \
    torchvision==0.21.0 \
    transformers==4.45.1

# Install ALL system dependencies in ONE layer
RUN apt-get update && \
    apt-get install -y \
        curl \
        tcpdump \
        procps \
        iw \
        tar \
        gcc \
        g++ \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Install crictl (FIXED: URL must be quoted)
RUN CRICTL_VERSION="v1.30.0" && \
    curl -L "https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/crictl-${CRICTL_VERSION}-linux-amd64.tar.gz" \
    | tar zx -C /usr/local/bin && \
    chmod +x /usr/local/bin/crictl

# Copy project files
COPY phi_3_5_vision /app/phi_3_5_vision
COPY Pictures /app/Pictures
COPY download_phi_3_5_vision.py /app/
# COPY emultimodal_extracted_data.txt /app/
COPY file_management.py /app/
COPY save_measurements.py /app/
COPY image_processing.py /app/
COPY image_server.py /app/

ENV PYTHONUNBUFFERED=1

EXPOSE 5002

CMD ["python", "image_server.py"]
# CMD ["gunicorn", "--preload", "-w", "8", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:5002", "image_server:app"]

