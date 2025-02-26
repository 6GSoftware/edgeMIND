# EdgeMIND LLM Querying and User Message Handling Server

This module is the edgeMIND vector database querying and maintenance server. This module:
- sets up a socket server that accepts connections from the edgeMIND LLM server, receives queries that are sent from the edgeMIND LLM server and searches the vector database for relevant information related to the query.

## Setup instructions

1. Create or obtain from somewhere a **faiss index file** that contains the **vector database**. **NB!** If you don't name the file ```multimodal_faiss_index.index```, you will have to change the file name in Dockerfile and vector-db-server.py files.
2. Create or obtain from somewhere a **metadata file** that is used in the querying of the vector database for relevant information. **NB!** If you don't name the file ```topic_metadata_with_names.txt```, you will have to change the file name in Dockerfile and vector-db-server.py files.
3. The edgeMIND LLM and user query handling server uses this module. See the README-file of the LLM and user query server for intructions on how to set it up.
4. See the project README-file for general instructions on how to set up the whole service and how to run the server applications in Docker containers as a multi-container server application.

