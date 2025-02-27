FROM python:3.10

WORKDIR /mydir

# Install dependencies
RUN pip install faiss-cpu
RUN pip install sentence-transformers

# Copy metadata file and vector database to the image
COPY topic_metadata_with_names.txt .
COPY multimodal_faiss_index.index .

# Copy the vector database handling server code to the image
COPY vector-db-server.py .

EXPOSE 8000

CMD ["python3", "-u", "vector-db-server.py"]