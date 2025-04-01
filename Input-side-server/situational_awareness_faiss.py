""" Module for saving the processed data in a metadata file and the vector database

This module is responsible for vectorizing the extracted and tokenized data, and saving the data in
a metadata file and the vector database (faiss index).

How this module works:
...
"""

import numpy as np
import lda
from sklearn.feature_extraction.text import CountVectorizer
from datetime import datetime
import json
import faiss
from sentence_transformers import SentenceTransformer

TAG = "situational_awareness_faiss:  "

file_path = './Pre_processed_text.txt'
output_file_path = './topic_metadata_with_names.txt'


def create_chunks(text, chunk_size=500, chunk_overlap=20):
    """Chunk the input text into smaller segments."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - chunk_overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def vectorize_and_save_to_vector_db():
    # Step 1: Load the text data from the file
    with open(file_path, 'r') as file:
        documents = file.readlines()

    # Step 2: Count total sentences and words
    #total_sentences = len(documents)
    #total_words = sum(len(doc.split()) for doc in documents)

    # Step 4: Preprocess the text: convert it to a document-term matrix
    # First, chunk the documents before vectorizing
    chunks = []
    for doc in documents:
        # Step 3: Define a function to chunk text before assigning topics
        doc_chunks = create_chunks(doc.strip())
        chunks.extend(doc_chunks)  # Add all chunks from this document to the overall chunk list

    vectorizer = CountVectorizer(stop_words='english')
    X = vectorizer.fit_transform(chunks)  # Use chunks for topic modeling

    # Step 5: Extract vocabulary
    vocab = vectorizer.get_feature_names_out()

    # Step 6: Fit the LDA model using the chunks
    model = lda.LDA(n_topics=10, n_iter=1500, random_state=1)
    model.fit(X)

    # Step 7: Get the topic-word distribution and create meaningful topic names
    n_top_words = 8
    topic_names = []
    topic_word = model.topic_word_

    for i, topic_dist in enumerate(topic_word):
        # Get the top words for the topic
        topic_words = np.array(vocab)[np.argsort(topic_dist)][:-(n_top_words+1):-1]
        topic_name = " ".join(topic_words)
        topic_names.append(topic_name)  # Store the topic name
        print(f'{TAG} Topic {i}: {topic_name}')

    # Step 8: Get the document-topic distribution for the chunks
    doc_topic = model.doc_topic_

    # Step 9: Prepare metadata to save
    metadata = []
    timestamp = datetime.now().isoformat()

    # Initialize the embedding model
    embedding_function = SentenceTransformer('all-mpnet-base-v2')

    # Step 10: Generate embeddings and collect metadata for each chunk
    embeddings = []
    for i, chunk in enumerate(chunks):
        # Get the top topic index and name for each chunk
        top_topic_idx = doc_topic[i].argmax()  # Get the top topic index for the chunk
        top_topic_name = topic_names[top_topic_idx]  # Use the corresponding topic name

        # Generate embedding for each chunk
        embedding = embedding_function.encode([chunk]).astype('float16')[0]  # Get the first (and only) embedding

        # Collect embeddings and metadata
        embeddings.append(embedding)  # Store the embedding for FAISS

        # Store the metadata with the topic name
        metadata.append({
            "timestamp": timestamp,
            "topic": top_topic_name,  # Store the topic name here
            "text": chunk,
            "embedding": embedding.tolist()  # Convert numpy array to list for JSON serialization
        })

    # Step 11: Save FAISS index using the embeddings
    dimension = embeddings[0].shape[0]  # Embedding dimension size
    index = faiss.IndexFlatL2(dimension)  # Create a FAISS index using L2 distance
    index.add(np.array(embeddings))  # Add embeddings to FAISS index

    # Save FAISS index to a file
    faiss.write_index(index, 'multimodal_faiss_index.index')

    # Step 12: Save metadata to a text file in JSON format
    with open(output_file_path, 'w') as f:
        for entry in metadata:
            f.write(json.dumps(entry) + '\n')  # Write each entry as a JSON string

    print(f"{TAG} FAISS index saved and metadata has been saved to '{output_file_path}' with {len(metadata)} entries.")