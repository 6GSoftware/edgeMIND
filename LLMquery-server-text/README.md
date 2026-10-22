# EdgeMIND LLM Querying and User Message Handling Server

This module is the edgeMIND user message processing and LLM handling server. This module:
- prepares everything that is needed for processing queries sent to the server by users. This includes loading the generation model and the tokenizer, defining the prompt template and initializing the prompt with the template.
- starts the server and handles client connections.
- receives a query from a connected client and sends it forward to the edgeMIND vector database management server.
- receives text chunks related to the query from the vector database server and sends those chunks and the user query to an LLM for response generation. (RAG)
- sends the generated response back to the user.

## Setup instructions

**NB!** This module is dependent on `edgeMIND-vector-db-server`. See the [`README.md`](edgeMIND-vector-db-server/README.md) file of the vector database server for instructions on setting it up.

See the [`k3s_cluster_setup_instructions.md`](../k3s_cluster_setup_instructions.md) file for general instructions on how to set up the whole EdgeMIND system and how to run the server applications in a K3s cluster.

The `llm_handling_server.py` file contains code for loading and running inference on the following models:
- google/gemma-2-2b
- microsoft/Phi-3.5-mini-instruct
- meta-llama/Llama-2-7b-chat-hf

You can use these same models or use some other model that you like. However, if you decide to use the same models as have been used in the evaluation tests, keep in mind that in order to get access to some of these models, you need to do extra steps. For example, for some of the models, you need to log in to HuggingFace and provide your contact information. When you have got access to the mode you wish to use with this server, you need to create a `.env` file and add the model name there. Use the `example.env` file as template.