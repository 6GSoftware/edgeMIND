FROM python:3.10

WORKDIR /mydir

# Install dependencies
RUN pip install torch
RUN pip install langchain
RUN pip install accelerate
RUN pip install transformers==4.43.0

# Copy the server code file to the image (into the /mydir directory)
COPY llm-handling-server.py .

# Copy the LLM model into the image
COPY saved_LLM_model ./saved_LLM_model

# Set environment variable for the path of huggingface cache files
#ENV HF_HOME="/root/.cache/huggingface"

EXPOSE 5000

CMD ["python3", "-u", "llm-handling-server.py"]
