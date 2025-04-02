# EdgeMIND LLM Querying and User Message Handling Server

This module is the edgeMIND user message processing and LLM handling server. This module:
- prepares everything that is needed for processing queries sent to the server by users. This includes loading the generation model and the tokenizer, defining the prompt template and initializing the prompt with the template.
- starts the web socket server and handles client connections.
- receives a query from a connected client and sends it forward to the edgeMIND vector database management server.
- receives a response from the vector database server ands sends that response and the user query to an LLM for
      response generation.
- sends the generated response back to the user.

## Setup instructions

1. Change the value of ```LLM_SERVER_IP``` in file ```llm-handling-server.py``` to match the IP address of your development machine.
3. **NB!** This module is dependent on `edgeMIND-vector-db-server`. See the `README.md` file of the vector database server for instructions on setting it up.
4. See the project `README.md` file for general instructions on how to set up the whole service and how to run the server applications in Docker containers as a multi-container server application.

