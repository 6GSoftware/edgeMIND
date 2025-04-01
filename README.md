# edgeMIND Framework
Repository for the edgeMIND servers: the LLM and user query handling server, and the vector database maintenance server.

This repository contains two servers: one is for handling user queries and the LLM, and the other one is for handling database queries and maintenance. Both servers can be run in Docker containers. The LLM and user query handling server accepts socket connections and receives messages from a client mobile app. The repository for the client app can be found here: --- 

## Set up instructions for running the Output side (LLMquery-server-text, LLMquery-server-audio, edgeMIND-vector-db-server)

Follow the instructions below to get the Output side servers up and running in Docker containers. For sending and receiving messages to and from the servers you can set up the client mobile app by following the instructions provided here.

### Step 1: Install Docker

You can install the Docker Engine from here: https://docs.docker.com/engine/install/.
Choose your operating system from the navigation on the left and follow the instructions for installing Docker.

### Step 2: Clone this repository to your machine

Clone this repository to your machine. For running the Output side only, you will NOT need the Input-side-server.

### Step 3: Set up ```LLMquery-server-text``` and ```edgeMIND-vector-db-server```

See the instructions in the README files of the modules ```LLMquery-server-text``` and ```edgeMIND-vector-db-server``` for additional set up instructions for these particular modules.

### Step 4: Download and save the LLM model locally

