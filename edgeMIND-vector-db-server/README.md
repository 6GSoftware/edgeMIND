# EdgeMIND Vector Database Server

This module is the EdgeMIND vector database server, which handles queries to the database and maintenance of the database.

## Setup instructions

1. Create or obtain a **permanent metadata file** that contains the **text chunks and their embeddings**, i.e. the database. **NB!** The vector database file should be named as ```permanent_metadata.json```. Otherwise you have to modify the file path in the code (`vector_db_server.py` file). If you create the file yourself, make sure to store some text chunks to the database before querying it, e.g. by uploading files through the **Input layer**.
2. Create or obtain a **temporary metadata file**. **NB!** The metadata file should be named as ```temp_metadata.json```. Otherwise you have to modify the file path in the code (`vector_db_server.py` file).
3. `LLMquery-server-audio` and `LLMquery-server-text` use this module. See the [`README.md`](LLMquery-server-text/README.md) file of the `LLMquery-server-text` module for intructions on how to set up the text generation service.
4. See the [`k3s_cluster_setup_instructions.md`](../k3s_cluster_setup_instructions.md) file for general instructions on how to set up the whole EdgeMIND system and how to run the server applications in a K3s cluster.

