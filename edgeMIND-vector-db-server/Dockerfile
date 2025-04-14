FROM python:3.10
    #3.13-slim

WORKDIR /mydir

# Install dependencies
RUN pip install faiss-cpu
RUN pip install sentence-transformers
RUN pip install Flask

# Copy metadata file and vector database to the image
COPY topic_metadata_with_names.txt .
COPY multimodal_faiss_index.index .

# Copy the vector database handling server code to the image
#COPY vector-db-server.py .
COPY vector_db_server_http.py .

EXPOSE 8000

#CMD ["python3", "-u", "vector-db-server.py"]
CMD ["python3", "-u", "vector_db_server_http.py"]