# EdgeMIND PDF processing server

This module is the edgeMIND PDF file processing service. Users can send PDF files to this service to the `/upload_pdf` endpoint. The PDF file is then parsed with the LlamaParse model and the extracted text is sent to the `situational-awareness-server` for topic generation.

## Setup instructions

In order to use LlamaParse for parsing the PDF files, you need an API key. Once you have obtained the API key, add it to a `.env` file. Use the `example.env` file as a template.

See the [`k3s_cluster_setup_instructions.md`](../k3s_cluster_setup_instructions.md) file for general instructions on how to set up the whole EdgeMIND system and how to run the server applications in a K3s cluster.

