# EdgeMIND Image Generation and User Message Handling Server

This module is the edgeMIND user query processing and image generation service. This module:
- prepares everything that is needed for processing queries sent to the server by users. This includes loading the generation model and the tokenizer, defining the prompt template and initializing the prompt with the template.
- starts the server and handles client connections.
- receives a query from a connected client and sends it forward to the edgeMIND vector database management server.
- receives a response from the vector database server and sends that response and the user query to an LLM for image generation.
- sends the generated image back to the user.

## Setup instructions

This service does not currently have a K3s manifest file and it has not been tested in the K3s cluster.