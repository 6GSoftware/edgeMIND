FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y curl tar && rm -rf /var/lib/apt/lists/*

RUN CRICTL_VERSION="v1.30.0" && \
    curl -L https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/crictl-${CRICTL_VERSION}-linux-amd64.tar.gz \
    | tar zx -C /usr/local/bin && \
    chmod +x /usr/local/bin/crictl

RUN apt-get update && apt-get install -y tcpdump && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 6501

ENV PYTHONUNBUFFERED=1

RUN mkdir -p /results

CMD ["python", "extracted_text_processing.py"]

# CMD ["gunicorn", "--preload", "-w", "4", "--threads", "1", "--timeout", "3600", "-b", "0.0.0.0:6501", "extracted_text_processing:app"]