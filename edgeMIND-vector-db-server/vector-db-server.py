from datetime import datetime
import faiss
import json
import socket
from sentence_transformers import SentenceTransformer

HOST = "edgemind_vector_db_server"  # Service name
PORT = 8000


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


def start_server():

    """Create and start the socket server"""
    """Start listening for client connections."""

    # Create a socket object
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Bind the socket to the server address and port
    server_socket.bind((HOST, PORT))
    
    # Listen for incoming connections (5 connections in the queue)
    server_socket.listen(5)
    print(f"Server is listening on {HOST}:{PORT}")

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

            results = search_faiss_index(query_text, index, metadata, embedding_function)
            print("Result from searching the faiss index:\n", results)

            # Prepare response for the llm server
            if results:
                retrieved_texts = "\n".join([
                    f"**Topic**: {result['topic']}\n**Timestamp**: {result['timestamp']}\n**Text**: {result['text']}\n"
                    for result in results[:3]
                ])

                print(f"Retrieved relevant info: {retrieved_texts}")
                now=datetime.now()
                print(now)
        
                response = retrieved_texts

            else:
                response = ""

            # Convert results (list) to a string
            #result_as_string = str(results)

            # Send the faiss index search result to the client
            #client_socket.sendall(pickle.dumps(results))
            client_socket.sendall(response.encode('utf-8'))
            #client_socket.sendall(json.dumps(results).encode('utf-8'))

            # Close the client connection
            client_socket.close()
            print(f"Connection closed with {client_address}")

        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == '__main__':
    start_server()