# EdgeMIND Framework

This is the repository for the **EdgeMIND** framework [[1]](#1). The EdgeMIND framework is divided into three main parts: the **Input layer**, the **Output layer** and the **Database layer**.

The **Input layer** is responsible for processing new files that the users upload to the system. In the current EdgeMIND system, users can upload **audio, image or pdf** files. The Input side is also responsible for applying situational awareness (topic modeling) to the data extracted from the uploaded files and for the responses that are generated in the Output layer. In essence, each uploaded file is processed with some model that extracts the information from the file into text format. In the situational awareness service, the extracted text is divided into chunks, and each chunks gets generated a topic, or alternatively they get assigned an existing topic that matches the content of the text chunk. The Input layer consists of the following services:
- [`audio-processing-server`](audio-processing-server)
- [`image-processing-server`](image-processing-server)
- [`pdf-processing-server`](pdf-processing-server)
- [`situational-awareness-server`](situational-awareness-server)

The **Output layer** is responsible for receiving a question from a user, and generating a response with a language model for the user using information that is retrieved from the vector database. The response can be either text or an image, depending on which service is used. The Output layer consists of the following services:
- [`LLMquery-server-text`](LLMquery-server-text)
- [`LLMquery-server-image`](LLMquery-server-image)


The **Database layer** is responsible for handling the writing to and reading from the vector database. It also contains the actual vector database. The vector database service is used to retrieve information from the database to be utilized in the generation of the response for the user (RAG). The Database layer consists of only one service:
- [`edgeMIND-vector-db-server`](edgeMIND-vector-db-server)


## Evaluation tests

The EdgeMIND system has been eveluated through evaluation tests that are divided to four different stages. The results for each evaluation metric on each stage, as well as the scripts that were used in the evaluation tests, can be found in this folder: <!-- ADD LINK! -->.


## Team and Affiliation

Members of the artifact development and research team:
- Dinesh Karthikeyan
- Pertti Arvola
- Anna-Sofia Paavonen
- Roopesh Shanmugasundaram
- Niko Mäkitalo

University of Jyväskylä, Finland

The EdgeMIND framework has been developed as a part of the 6GSoft-project (6G software for extremely distributed and heterogeneous massive networks of connected devices). The project website can be found here: [6GSoft-project](https://sites.google.com/view/6gsoft/about?pli=1&authuser=0).


## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## How to Set up the EdgeMIND System in a K3s Cluster

Instructions for setting up the EdgeMIND system in a K3s cluster can be found in this file: [`k3s_cluster_setup_instructions.md`](k3s_cluster_setup_instructions.md).

## References

<a id="1">[1]</a> 
Dinesh Kumar Karthikeyan, Roopesh Kumar Shanmugasundaram, Anna-Sofia Paavonen, Tommi Mikkonen, Niko Mäkitalo, and Ronny Seiger. 2025. Distributed Computing with Language Models at the Edge: A Framework and Prototype. In Proceedings of the 15th International Conference on the Internet of Things (IOT '25). Association for Computing Machinery, New York, NY, USA, 77–85. https://doi.org/10.1145/3770501.3770511
