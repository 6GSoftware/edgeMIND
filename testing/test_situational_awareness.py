""" Module for saving the processed data in a metadata file and the vector database

This module is responsible for vectorizing the extracted and tokenized data, and saving the data in
a metadata file and the vector database (faiss index).

How this module works:
...
"""

import numpy as np
import lda
import requests
from sklearn.feature_extraction.text import CountVectorizer
from datetime import datetime
import json
import faiss
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from torch import cosine_similarity

# Load the environment variables from the .env file
load_dotenv()

# File paths
file_path = './Pre_processed_text.txt'  # FIXME: get the correct path!
situational_awareness_JSON = "./situational_awareness.json"

# Constants
TAG = "test_situational_awareness:  "


class NumpyArrayEncoder(json.JSONEncoder):
    def default(self, object):
        if isinstance(object, np.ndarray):
            return object.tolist()
        return json.JSONEncoder.default(self, object)


# Define this function first, so that the top-level code above can use it
def create_chunks(text, chunk_size=500, chunk_overlap=20):
    """Chunk the input text into smaller segments."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - chunk_overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks



# TODO: import this module in the extracted_text_processing module!!!
# TODO: test the code that saves stuff to the JSON file!
# First time running: Train and fit the LDA model with the most recent data
with open(file_path, 'r') as file:
    documents = file.readlines()

# Preprocess the text: convert it to a document-term matrix
# First, chunk the documents before vectorizing
init_chunks = []
for doc in documents:
    # Define a function to chunk text before assigning topics
    doc_chunks = create_chunks(doc.strip())
    init_chunks.extend(doc_chunks)  # Add all chunks from this document to the overall chunk list

init_vectorizer = CountVectorizer(stop_words='english')
init_X = init_vectorizer.fit_transform(init_chunks)  # Use chunks for topic modeling

# Extract vocabulary
init_vocab = init_vectorizer.get_feature_names_out()

init_model = lda.LDA(n_topics=10, n_iter=1500, random_state=1)
init_model.fit(init_X)

# Get the topic-word distribution and create meaningful topic names
n_top_words = 8
init_topic_names = []
init_topic_word = init_model.topic_word_

for i, topic_dist in enumerate(init_topic_word):
    # Get the top words for the topic
    topic_words = np.array(init_vocab)[np.argsort(topic_dist)][:-(n_top_words+1):-1]
    topic_name = " ".join(topic_words)
    init_topic_names.append(topic_name)  # Store the topic name
    print(f'{TAG} Topic {i}: {topic_name}')

# Step 8: Get the document-topic distribution for the chunks
init_doc_topic = init_model.doc_topic_

with open(situational_awareness_JSON, 'w') as file:
    data = {"vocab": init_vocab, "topic_word": init_topic_word}
    print("serialize these matrices into JSON and write into the file")
    json.dump(data, file, cls=NumpyArrayEncoder)
    print("Serialization process done!")



FILE_CONTENTS = """response for mug_phone_pens_20250410_133223.jpg: - the image shows a collection of items laid out on a white surface.
- there is a black smartphone with a visible screen protector.
- two pens, one red and one black, are placed next to the smartphone.
- a black mug is positioned to the right of the smartphone.
- a black hat is placed on the right side of the image.
- there is a piece of white tape or paper under the smartphone.
- the background is a plain wall with a door partially visible.
- the items are arranged in a somewhat scattered manner."""


def fit_LDA_model():
    ...


def vectorize_and_send_to_database():

    # Initialize the metadata and embeddings lists
    metadata = []
    embeddings = []
    timestamp = datetime.now().isoformat()  # Calculate timestamp FOR THE NEW DATA ONLY!
    # Initialize the embedding model
    embedding_function = SentenceTransformer('all-mpnet-base-v2')

    # Save file contents to the Pre_processed_text.txt file
    with open(file_path, 'a') as file:
        file.write(FILE_CONTENTS)

    file_contents = FILE_CONTENTS.splitlines()
    print(f"{TAG} The file contents after splitting: {file_contents}")
    
    new_chunks = []
    for content in file_contents:
        # Step 3: Define a function to chunk text before assigning topics
        cont_chunks = create_chunks(content.strip())
        new_chunks.extend(cont_chunks)

    print(f"{TAG} Number of chunks: {len(new_chunks)}\n")
    print(f"{TAG} The chunks are: {new_chunks}")

    # NOTE: is this really needed?
    new_vectorizer = CountVectorizer(stop_words='english')
    X_new = new_vectorizer.fit_transform(new_chunks)
    new_vocab = new_vectorizer.get_feature_names_out()

    new_terms = new_vocab - init_vocab
    #new_terms = new_vocab - prev_vocab
    overlapping_terms = new_vocab & init_vocab
    #overlapping_terms = new_vocab & prev_vocab
    percent_new = len(new_terms) / max(len(new_vocab), 1)

    print("\nVocabulary Drift Report")
    print("---------------------------")
    print(f"Old vocab size:         {len(init_vocab)}")
    #print(f"Old vocab size:         {len(prev_vocab)}")
    print(f"New vocab size:         {len(new_vocab)}")
    print(f"Overlapping terms:      {len(overlapping_terms)}")
    print(f"New unseen terms:       {len(new_terms)}")
    print(f"→ Percent new terms:    {percent_new:.2%}")

    # Vectorize new docs using old vocabulary
    X = init_vectorizer.transform(new_chunks)
    # TODO: find out which one should be used: the above one or the below one
    #vectorizer = CountVectorizer(stop_words='english', vocabulary=init_vocab)
    #X = prev_vectorizer.transform(new_chunks)

    # Normalize for cosine similarity
    X_norm = X / (X.sum(axis=1) + 1e-6)

    # Compare new chunks to existing topic-word distributions
    similarity = cosine_similarity(X_norm, init_topic_word)    # FIXME: get the previous topic_word_ distribution from somewhere!

    fitting_docs = []
    outliers = []

    treshold = 0.5 # TODO: find out what exactly this is
    for i, sim in enumerate(similarity):
        max_sim = np.max(sim)
        best_topic = np.argmax(sim)
        if max_sim >= treshold:
            fitting_docs.append((i, best_topic))
            """
                i = index of a document in the new_chunks list
                best_topic = index of a topic (row) in the topic-name distribution matrix
            """
        else:
            outliers.append(i)

    if fitting_docs:
        for doc_i, topic_i in fitting_docs:
            topic = init_topic_names[topic_i]   # TODO: check that this is correct, that this works like it should!
            chunk = new_chunks[doc_i]           # TODO: check that this is correct, that this works like it should!
            print(f"{TAG} Topic for chunk {doc_i}: {topic}")

            # Generate embedding for each chunk
            embedding = embedding_function.encode([chunk]).astype('float16')[0]  # Get the first (and only) embedding

            # Collect embeddings and metadata
            embeddings.append(embedding)  # Store the embedding for FAISS

            # Store the metadata with the topic name
            metadata.append({
                "timestamp": timestamp,
                "topic": topic,  # Store the topic name here
                "text": chunk,
                "embedding": embedding.tolist()  # Convert numpy array to list for JSON serialization
            })

    if outliers:
        """
            Decide the number of topics to generate based on the size of the data, i.e. the number
            of elements in the list containing the data (new_chunks).

            >> elements <= 10:       5 topics
            >> 10 < elemets <= 30:   10 topics
            >> 30 < elemets <= 60:   15 topics
            >> 60 < elemets <= 120:  20 topics
            >> elements > 120:       30 topics        
        """
        # TODO: n_topics should be determined based on the size of the data

        # Get the outlier chunks from the new_chunks list
        chunks = []
        for i in outliers:
            idx = outliers[i]
            chunks.append(new_chunks[idx])

        # Create vectorizer only for the outliers, fit it with the outlier chunks, 
        # and get vocab only for the outliers
        vectorizer = CountVectorizer(stop_words='english')
        X = vectorizer.fit_transform(chunks)
        vocab = vectorizer.get_feature_names_out()

        model = lda.LDA(n_topics=10, n_iter=1500, random_state=1)
        model.fit(X)

        # Get the topic-word distribution and create meaningful topic names
        n_top_words = 8
        topic_names = []
        topic_word = model.topic_word_

        for i, topic_dist in enumerate(topic_word):
            # Get the top words for the topic
            topic_words = np.array(vocab)[np.argsort(topic_dist)][:-(n_top_words+1):-1]
            topic_name = " ".join(topic_words)
            topic_names.append(topic_name)  # Store the topic name
            print(f'{TAG} Topic {i}: {topic_name}')

        # Get the document-topic distribution for the chunks
        doc_topic = model.doc_topic_

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

        """
            When the handling of the outliers is done, some of the variables have to be re-evaluated
            for the situational awareness to take the new chunks and topics into consideration the
            next time new data is sent:

            >> add new chunks to init_chunks
            >> fit the init_vectorizer with the extended init_chunks
            >> get extended vocabulary
            >> train the lda model again    <-- NB! with this current approach this has to be done possibly every time, anyways
            >> fit the lda model with the extended init_chunks
            >> make new topic-word AND doc_topic distributions with the newly trained lda
        """

        init_vectorizer = CountVectorizer(stop_words='english')
        init_X = init_vectorizer.fit_transform(init_chunks)  # Use chunks for topic modeling

        # Extract vocabulary
        init_vocab = init_vectorizer.get_feature_names_out()

        init_model = lda.LDA(n_topics=10, n_iter=1500, random_state=1)
        init_model.fit(init_X)
        


    # TODO: put this somewhere else
    #combined_vocab = list(prev_vocab | new_vocab)
    #combined_vectorizer = CountVectorizer(stop_words='english', vocabulary=combined_vocab)



    '''
    vectorizer = CountVectorizer(stop_words='english')
    X = vectorizer.fit_transform(new_chunks)  # Use chunks for topic modeling

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
    timestamp = datetime.now().isoformat()  # Calculate timestamp FOR THE NEW DATA ONLY!

    # Initialize the embedding model
    embedding_function = SentenceTransformer('all-mpnet-base-v2')

    # Step 10: Generate embeddings and collect metadata for each chunk
    embeddings = []
    for i, chunk in enumerate(new_chunks):
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

    # Data to be sent
    post_data = {
        'embeddings': embeddings,
        'metadata': metadata
    }

    # Defining content type for the payload
    headers = {'Content-type': 'application/json'}
    # Post the user question to the vector database server and get the query result as response
    response = requests.post(VECTOR_DB_URL, data=json.dumps(post_data), headers=headers)
    response_as_json = response.json()
    print(f"The received response is: {response_as_json['message']}")
    '''

'''
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
    timestamp = datetime.now().isoformat()  # Calculate timestamp FOR THE NEW DATA ONLY!

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
'''

if __name__ == "__main__":
    vectorize_and_send_to_database()