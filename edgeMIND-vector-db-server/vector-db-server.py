from datetime import datetime
import faiss
import json
import socket
from sentence_transformers import SentenceTransformer

HOST = "---"
HOST_PORT = 8000

#IDENTIFIER = "db"


index_file_path = 'multimodal_faiss_index.index'
metadata_file_path = 'topic_metadata_with_names.txt'


def load_metadata(file_path):
    """Load metadata from a file."""
    metadata = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            metadata.append(json.loads(line.strip()))  # Parse JSON lines
    return metadata


def load_faiss_index(index_file_path):
    """Load the FAISS index."""
    return faiss.read_index(index_file_path)


def load_embedding_function():
    return SentenceTransformer('all-mpnet-base-v2')


def search_faiss_index(query_text, index, metadata, embedding_function, k=3):
    """Search FAISS index for the closest topic."""

    # Do the actual search to the faiss index
    query_embedding = embedding_function.encode([query_text]).astype('float32')  # Generate query embedding
    distances, indices = index.search(query_embedding, k)  # Retrieve top-k results
    
    results = []
    for i, idx in enumerate(indices[0]):
        if idx == -1:  # FAISS returns -1 if no result is found
            continue
        result_entry = metadata[idx]
        results.append({
            "text": result_entry["text"],
            "topic": result_entry["topic"],
            "timestamp": result_entry["timestamp"],
            "distance": distances[0][i]
        })
    
    return results

'''
def choose_server(output_format):
    llm_server = {}
    match output_format:
        case "text":
            llm_server["server_ip"] = "edgemind_llm_query_server_1"
            llm_server["server_port"] = 5000
            return llm_server
        case "audio":
            llm_server["server_ip"] = "edgemind_llm_query_server_2"
            llm_server["server_port"] = 5001
            return llm_server
        case _:
            llm_server["server_ip"] = "edgemind_llm_query_server_1"
            llm_server["server_port"] = 5000
            return llm_server

    #return (llm_server_ip, llm_server_port)     # Return a tuple with the ip address and the port for the correct llm server'
'''

def choose_server(output_format):
    llm_server = {}
    match output_format:
        case "text":
            llm_server["server_ip"] = "edgemind_llm_query_server_1"
            llm_server["server_port"] = 6000
            return llm_server
        case "audio":
            llm_server["server_ip"] = "edgemind_llm_query_server_2"
            llm_server["server_port"] = 6001
            return llm_server
        case _:
            llm_server["server_ip"] = "edgemind_llm_query_server_1"
            llm_server["server_port"] = 6000
            return llm_server


def start_server():

    """Create and start the socket server"""
    """Start listening for client connections."""

    # Create a socket object
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Bind the socket to the server address and port
    server_socket.bind((HOST, HOST_PORT))
    
    # Listen for incoming connections (5 connections in the queue)
    server_socket.listen(5)
    print(f"Server is listening on {HOST}:{HOST_PORT}")

    while True:
        try:
            # Accept an incoming connection
            client_socket, client_address = server_socket.accept()
            print(f"Connection established with {client_address}")

            # Load faiss index, metadata and embedding function every time a new client is connected
            index = load_faiss_index(index_file_path)
            metadata = load_metadata(metadata_file_path)
            embedding_function = load_embedding_function()

            # Receive data from the client (up to 1024 bytes)
            query_text = client_socket.recv(1024).decode('utf-8')

            # Receive the choice about output format
            output_format = client_socket.recv(1024).decode('utf-8')

            # Choose which llm server to send the db results to, based on output_format
            llm_server = choose_server(output_format)
            print(f"The llm server to send the results to is: {llm_server['server_ip']}:{llm_server['server_port']}")

            # Close connection to the mobile app
            client_socket.close()
            print(f"Connection closed with {client_address}")

            results = search_faiss_index(query_text, index, metadata, embedding_function)
            print("Result from searching the faiss index:\n", results)

            # Prepare response for the llm server
            if results:
                retrieved_texts = "\n".join([
                    f"**Topic**: {result['topic']}\n**Timestamp**: {result['timestamp']}\n**Text**: {result['text']}\n"
                    for result in results[:3]
                ])

                print(f"Retrieved relevant info: {retrieved_texts}\n")
                now=datetime.now()
                print(now)
        
                response = retrieved_texts

            else:
                response = ""

            '''
            # Connect and send the response and the query to the llm server
            print("Establishing socket connection with the llm server...")

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((llm_server["server_ip"], llm_server["server_port"]))

                print("Connected to llm server!")
                print("Sending data to llm server...\n")

                s.sendall(IDENTIFIER.encode('utf-8'))
                print("identifier sent\n")
                # Send the db query result
                s.sendall(response.encode('utf-8'))
                print("db results sent\n")
                # Send the user query
                s.sendall(query_text.encode('utf-8'))
                print("user query sent\n")'
            '''

            # Connect and send the response and the query to the llm server

            data = json.dumps({"query": query_text, "results": response})

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                print("Connecting to the llm server...")
                s.connect((llm_server['server_ip'], llm_server['server_port']))

                s.sendall(data)

            # Convert results (list) to a string
            #result_as_string = str(results)

            # Send the faiss index search result to the client
            #client_socket.sendall(pickle.dumps(results))
            #client_socket.sendall(response.encode('utf-8'))
            #client_socket.sendall(json.dumps(results).encode('utf-8'))

        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == '__main__':
    start_server()