FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y curl tcpdump && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --default-timeout=999 \
    torch==2.6.0 \
    torchvision==0.21.0 \
    transformers==4.45.1

COPY requirements.txt .

RUN apt-get update && \
    apt-get install -y iw && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

RUN CRICTL_VERSION="v1.30.0" && \
    curl -L https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/crictl-${CRICTL_VERSION}-linux-amd64.tar.gz \
    | tar zx -C /usr/local/bin && \
    chmod +x /usr/local/bin/crictl

# Make this smarter later:
COPY phi_3_5_vision /app/phi_3_5_vision
COPY Pictures /app/Pictures
COPY results /app/results
COPY download_phi_3_5_vision.py /app/
COPY emultimodal_extracted_data.txt /app/
COPY file_management.py /app/
COPY save_measurements.py /app/
COPY image_processing.py /app/
COPY image_server.py /app/

RUN mkdir -p /results

ENV PYTHONUNBUFFERED=1

EXPOSE 5002

CMD ["python", "image_server.py"]
#CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:5002", "image_server:app"]
# CMD ["sh", "./start.sh"]