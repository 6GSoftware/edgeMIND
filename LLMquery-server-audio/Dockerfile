# The Dockerfile for the audio generating LLM server
FROM python:3.10

WORKDIR /mydir

# Install dependencies
RUN pip install torch
RUN pip install langchain
RUN pip install accelerate
RUN pip install transformers==4.43.0

# Copy the LLM model into the image
COPY saved_LLM_model ./saved_LLM_model

# Copy the server code file to the image (into the /mydir directory)
#COPY llm-handling-server.py .
COPY test_server.py .

# Set environment variable for the path of huggingface cache files
#ENV HF_HOME="/root/.cache/huggingface"

EXPOSE 5001 6001

#CMD ["python3", "-u", "llm-handling-server.py"]
CMD ["python3", "-u", "test_server.py"]
