FROM python:3.10

WORKDIR /mydir

# Install dependencies
RUN pip install torch
RUN pip install langchain
RUN pip install accelerate
RUN pip install transformers==4.43.0

# Copy the server code file to the image
COPY llm-handling-server.py .

# Install dotenv library and copy the .env file to the image
RUN pip install python-dotenv
COPY .env .

# Set environment variable for the path of huggingface cache files
ENV HF_HOME="/root/.cache/huggingface"

EXPOSE 5000

CMD ["python3", "-u", "llm-handling-server.py"]
