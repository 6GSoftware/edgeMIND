# edgeMIND Framework
This is the repository for the edgeMIND framework. The edgeMIND framework is divided into three main parts: the Input layer, the Output layer and the Database layer.

The Input layer is responsible for processing new files that the users upload to the system. The users can upload the files (which can be audio, image or pdf files) by using a dedicated Android app. The Input side is also responsible for applying the RAG and situational awareness to the data extracted from the uploaded files and for the responses that are generated in the Output layer.

The Output layer is responsible for receiving a question from a user, and generating a response with a language model for the user using information that is retrieved from the vector database. The users can send the questions through a dedicated Android app.

The Database layer is responsible for handling the writing to and reading from the vector database. It also contains the actual vector database.

## General setup instructions

Here are some general setup instructions for the Input side and the Output side. The layer specific setup instructions can be found below this section.

### Step 1: Install Docker

You can install the Docker Engine from here: https://docs.docker.com/engine/install/.

Choose your operating system from the navigation on the left and follow the instructions for installing Docker.

### Step 2: Clone this repository to your machine

Clone this repository to your machine. For running the Output side only, you will NOT need the `Input-side-server`.

### Step 3: Create a docker network

Create a user-defined netwwork named `edgemind_network` by running `docker network create edgemind_network`.


## Set up instructions for running the Input side (`Input-side-server`)

Follow the instructions below to run the Input side file processing process. For uploading files to the Input side you can set up the client mobile app by following the instructions provided here.

### Step 1: Create a virtual environment and install requirements

Navigate to the edgeMIND project folder and create a python virtual environment:
` python<version> -m venv <venv-name>`

Activate the virtual environment: `source <venv-name>/bin/activate`

Navigate back to the project root and install the dependencies: `pip install -r requirements.txt`

### Step 2: Set up the environment variables

Create a `.env` file in the project root.

Acquire the API key for the LlamaParse library and save it in the `.env` file as `LLAMAPARSE_API_KEY`.

Save the IP address of your machine as `INPUT_SERVER_IP`.

### Step 3: Run the service

Run the service with `python http_file_upload_server.py`.


## Set up instructions for running the Output side (`LLMquery-server-text`, `LLMquery-server-audio`, and `edgeMIND-vector-db-server`)

Follow the instructions below to get the Output side servers up and running in Docker containers. For sending and receiving messages to and from the servers you can set up the client mobile app by following the instructions provided here.

### Step 1: Set up `LLMquery-server-text`, `LLMquery-server-audio` and `edgeMIND-vector-db-server`

See the instructions in the README files of the modules 
1. `LLMquery-server-text` and 
2. `LLMquery-server-audio` and
2. `edgeMIND-vector-db-server` 

for additional set up instructions for these particular modules.

### Step 2: Download and save the LLM model locally

Run ```python download_and_save_LLM.py```

(or `python3 download_and_save_LLM.py`) 

in the `LLMquery-server-text` directory, to download and locally save the LLM model used in `LLMquery-server-text` and `LLMquery-server-audio`.

Copy the LLM folder that was created and paste it in the `LLMquery-server-audio` direcory, too.

### Step 3: Run and stop the containers

In the project root directory, run `docker compose up --build`.

Now the containers should be running and you should be able to see logs for the running services in the terminal.

Stop the containers by pressing `Ctrl + C`and then run `docker compose down` in the terminal.
