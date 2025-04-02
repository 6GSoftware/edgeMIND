# EdgeMIND LLM Querying and User Message Handling Server

This module is the edgeMIND vector database querying and maintenance server. This module:
- sets up a socket server that accepts connections from the edgeMIND LLM server, receives queries that are sent from the edgeMIND LLM server and searches the vector database for relevant information related to the query.

## Setup instructions

1. Create or obtain from somewhere a **faiss index file** that contains the **vector database**. **NB!** The vector database file should be named as ```multimodal_faiss_index.index```.
2. Create or obtain from somewhere a **metadata file** that is used in the querying of the vector database for relevant information. **NB!** The metadata file should be named as ```topic_metadata_with_names.txt```.
3. ```LLMquery-server-audio``` and ```LLMquery-server-text``` modules use this module. See the `README.md` file of the ```LLMquery-server-text``` module for intructions on how to set them up.
4. See the project `README.md` file for general instructions on how to set up the whole service and how to run the server applications in Docker containers as a multi-container server application.

