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
TAG = "test2:  "


class NumpyArrayEncoder(json.JSONEncoder):
    def default(self, object):
        if isinstance(object, np.ndarray):
            return object.tolist()
        return json.JSONEncoder.default(self, object)


# Define this function first, so that the top-level code above can use it
def create_chunks(text, chunk_size=500, chunk_overlap=20):
    """Chunk the input text into smaller segments."""

    print(f"{TAG} text to be chunked: {text}")

    words = text.split()
    print(f"{TAG} words: {words}")

    chunks = []
    for i in range(0, len(words), chunk_size - chunk_overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
            print(f"chunk: {chunk}")
    return chunks


def create_chunks_2(document, chunk_size=200):
    chunks = []
    words = document.split()
    print(f"{TAG} words: {words}\n\n")

    for i in range(0, len(words), chunk_size):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
            print(f"{TAG} chunk: {chunk}\n")
    
    return chunks


# TODO: import this module in the extracted_text_processing module!!!
# TODO: test the code that saves stuff to the JSON file!
# First time running: Train and fit the LDA model with the most recent data
with open(file_path, 'r') as file:
    documents = file.readlines()

# Preprocess the text: convert it to a document-term matrix
# First, chunk the documents before vectorizing
init_chunks = []
#for doc in documents:
#    # Define a function to chunk text before assigning topics
#    doc_chunks = create_chunks(doc.strip())
#    init_chunks.extend(doc_chunks)  # Add all chunks from this document to the overall chunk list
#    print("\n\n")
document = ' '.join(documents)
init_chunks = create_chunks_2(document)
print(f"\n\n{TAG} number of chunks: {len(init_chunks)}")

init_vectorizer = CountVectorizer(stop_words='english')
init_X = init_vectorizer.fit_transform(init_chunks)  # Use chunks for topic modeling

# Extract vocabulary
init_vocab = init_vectorizer.get_feature_names_out()

init_model = lda.LDA(n_topics=50, n_iter=1500, random_state=1)
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

#with open(situational_awareness_JSON, 'w') as file:
#    data = {"vocab": init_vocab, "topic_word": init_topic_word}
#    print("serialize these matrices into JSON and write into the file")
#    json.dump(data, file, cls=NumpyArrayEncoder)
#    print("Serialization process done!")

print("------------------------------------------------------------------------------------\n")



FILE_CONTENTS = """response for mug_phone_pens_20250410_133223.jpg: - the image shows a collection of items laid out on a white surface.
- there is a black smartphone with a visible screen protector.
- two pens, one red and one black, are placed next to the smartphone.
- a black mug is positioned to the right of the smartphone.
- a black hat is placed on the right side of the image.
- there is a piece of white tape or paper under the smartphone.
- the background is a plain wall with a door partially visible.
- the items are arranged in a somewhat scattered manner."""

FILE_CONTENTS_2 = """response for notebook_20250408_151711.jpg: - the image shows a white surface with a purple notebook lying on it.
- there are two blue earbuds placed on the notebook.
- the background is slightly blurred but appears to be an indoor setting with a chair and a bag visible.
- the lighting in the image is bright, suggesting it may be taken in a well-lit room."""


def fit_LDA_model():
    ...


def vectorize_and_send_to_database(file_contents):

    # Initialize the metadata and embeddings lists
    #metadata = []
    #embeddings = []
    #timestamp = datetime.now().isoformat()  # Calculate timestamp FOR THE NEW DATA ONLY!
    ## Initialize the embedding model
    #embedding_function = SentenceTransformer('all-mpnet-base-v2')

    # Introduce the global variables
    global init_vectorizer
    global init_topic_word
    global init_doc_topic
    global init_topic_names
    global init_vocab
    global init_chunks

    # Save file contents to the Pre_processed_text.txt file
    #with open(file_path, 'a') as file:
    #    file.write(file_contents)

    contents = file_contents.splitlines()
    print(f"{TAG} The file contents after splitting: {contents}\n")
    
    new_chunks = []
    #for content in contents:
    #    # Step 3: Define a function to chunk text before assigning topics
    #    cont_chunks = create_chunks(content.strip())
    #    new_chunks.extend(cont_chunks)
    contents = ' '.join(contents)
    new_chunks = create_chunks_2(contents)
    print(f"{TAG} Number of chunks: {len(new_chunks)}")
    print(f"{TAG} The chunks are: {new_chunks}\n")

    # Transform new chunks to a document-term matrix with the initial vectorizer
    new_X = init_vectorizer.transform(new_chunks)

    # Turn sparse matrix into dense vector
    #dense_vector = new_X.toarray().flatten()

    # Calculate the propability of a topic suiting a chunk
    topic_scores_matrix = new_X @ init_topic_word.T
    #topic_scores = dense_vector @ init_topic_word.T
    #topic_probs = topic_scores / topic_scores.sum()

    # Add a tiny epsilon to avoid division by zero if any row is all zeros
    epsilon = 1e-12

    row_sums = topic_scores_matrix.sum(axis=1) + epsilon
    topic_probs_matrix = topic_scores_matrix / row_sums[:, np.newaxis]
    print(f"{TAG} the topic_probs_matrix is: {np.matrix(topic_probs_matrix)}\n")

    fitting_chunks = []
    outliers = []

    # Calculate which are the topics that suit best for each chunk
    best_topic_indices = topic_probs_matrix.argmax(axis=1)  # Best topic per chunk <- index of the topic
    print(f"{TAG} the best topic indices: {best_topic_indices}")
    # Get the score of the best fitting topic per chunk
    best_topic_scores = topic_probs_matrix.max(axis=1)      # Best topic score per chunk <- best score
    print(f"{TAG} the best topic scores per chunk: {best_topic_scores}")

    threshold = 0.5

    # Determine which chunks should be assigned an existing topic and which ones should be generated a new topic
    for idx, score in enumerate(best_topic_scores):
        if score > threshold:
            fitting_chunks.append((new_chunks[idx], best_topic_indices[idx]))
            print(f"{TAG} fitting chunk!")
        else:
            outliers.append(new_chunks[idx])
            print(f"{TAG} outlier...")

'''
    if fitting_chunks:
        for chunk, topic_i in fitting_chunks:
            topic = init_topic_names[topic_i]
            print(f"{TAG} Topic for chunk '{chunk}': {topic}")

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
'''

    #if outliers:
    #    init_chunks = init_chunks + new_chunks
    #    new_vectorizer = CountVectorizer(stop_words='english')
    #    all_X = new_vectorizer.fit_transform(init_chunks)  # Use chunks for topic modeling
    #
    #    # Extract vocabulary
    #    new_vocab = new_vectorizer.get_feature_names_out()
    #
    #    new_model = lda.LDA(n_topics=10, n_iter=1500, random_state=1)   #TODO: make code that decides how many topics are generated
    #    new_model.fit(all_X)
    #
    #    # Get the topic-word distribution and create meaningful topic names
    #    n_top_words = 8
    #    new_topic_names = []
    #    new_topic_word = new_model.topic_word_
    #
    #    for i, topic_dist in enumerate(new_topic_word):
    #        # Get the top words for the topic
    #        topic_words = np.array(new_vocab)[np.argsort(topic_dist)][:-(n_top_words+1):-1]
    #        topic_name = " ".join(topic_words)
    #        new_topic_names.append(topic_name)  # Store the topic name
    #        print(f'{TAG} Topic {i}: {topic_name}')
    #
    #    # Step 8: Get the document-topic distribution for the chunks
    #    new_doc_topic = new_model.doc_topic_
    #
    #    for i, chunk in enumerate(outliers):
    #        # Get the top topic index and name for each chunk
    #        top_topic_idx = new_doc_topic[i].argmax()  # Get the top topic index for the chunk
    #        top_topic_name = new_topic_names[top_topic_idx]  # Use the corresponding topic name
    #
    #        # Generate embedding for each chunk
    #        embedding = embedding_function.encode([chunk]).astype('float16')[0]  # Get the first (and only) embedding
    #
    #        # Collect embeddings and metadata
    #        embeddings.append(embedding)  # Store the embedding for FAISS
    #
    #        # Store the metadata with the topic name
    #        metadata.append({
    #            "timestamp": timestamp,
    #            "topic": top_topic_name,  # Store the topic name here
    #            "text": chunk,
    #            "embedding": embedding.tolist()  # Convert numpy array to list for JSON serialization
    #        })





'''
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
'''
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
'''
        init_vectorizer = CountVectorizer(stop_words='english')
        init_X = init_vectorizer.fit_transform(init_chunks)  # Use chunks for topic modeling

        # Extract vocabulary
        init_vocab = init_vectorizer.get_feature_names_out()

        init_model = lda.LDA(n_topics=10, n_iter=1500, random_state=1)
        init_model.fit(init_X)
'''


    # TODO: put this somewhere else
    #combined_vocab = list(prev_vocab | new_vocab)
    #combined_vectorizer = CountVectorizer(stop_words='english', vocabulary=combined_vocab)


if __name__ == "__main__":
    vectorize_and_send_to_database(FILE_CONTENTS)
    print("--------------------------------------------------------------------------------\n")
    vectorize_and_send_to_database(FILE_CONTENTS_2)
