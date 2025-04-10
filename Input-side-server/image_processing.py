""" Image file processing module

This module is responsible for generating a summary of the contents of the image files sent to the 
Input side of the edgeMIND framework.

How this module works:
The name of the image file to be summarised is given to the process_image_files method and the image
file is processed and the contents of it is summarised to text with the microsoft/Phi-3.5-vision-instruct model.
After that the summary is saved in the texts_Image.txt file and the name of the file is saved in the 
processed_images.txt file to prevent processing the same file again.
"""

from PIL import Image
import os
from transformers import AutoModelForCausalLM, AutoProcessor
from dotenv import load_dotenv

# Loads the environment variables from the .env file
load_dotenv()

TAG = "image_processing:  "

# Define the folder containing images and the output text file
image_folder = r'./Pictures'

combined_text_file = './test_emultimodal_extracted_data.txt'

def process_image_files(new_file):
    # Set model ID and load model and processor
    model_id = "microsoft/Phi-3.5-vision-instruct"
    #model_id = "./phi3_vision"

    # Load the model
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        device_map="cpu",
        trust_remote_code=True,
        torch_dtype="auto",
        _attn_implementation='eager'
    )
    
    # Load the processor
    processor = AutoProcessor.from_pretrained(
        model_id, 
        trust_remote_code=True, 
        num_crops=4
    )

    #model = AutoModelForCausalLM.from_pretrained("./phi3_vision", trust_remote_code=True)
    #processor = AutoProcessor.from_pretrained("./phi3_vision")

    # Process each image individually
    if new_file.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff")):  # Add more image types if needed
        file_path = os.path.join(image_folder, new_file)

        # Open the image
        image = Image.open(file_path)

        # Always use image_id 1 for single images
        placeholder = f"<|image_1|>\n"  # Set the image_id to 1 for each image

        # Define the message for summarization
        messages = [
            {"role": "user", 
        "content": f"{placeholder}Extract all details from the image exactly as they appear. Then, create a concise bulleted list summarizing the key points."}
        ]

        # Prepare the prompt
        prompt = processor.tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )

        # Preprocess the input
        inputs = processor(prompt, images=[image], return_tensors="pt").to("cpu")

        # Define generation arguments
        generation_args = {
            "max_new_tokens": 1000,
            "temperature": 0.0,
            "do_sample": False,
        }

        # Generate the output
        generate_ids = model.generate(
            **inputs,
            eos_token_id=processor.tokenizer.eos_token_id,
            **generation_args
        )

        # Remove input tokens from generated IDs
        generate_ids = generate_ids[:, inputs['input_ids'].shape[1]:]

        # Decode the generated IDs into text
        response = processor.batch_decode(
            generate_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )[0]

        # Save the response to the output file
        with open(combined_text_file, 'a', encoding='utf-8') as f:
            f.write(f"Response for {new_file}:\n")  # Store the image file name
            f.write(response + "\n\n")              # Store the response

        print(f"{TAG} Processed and saved response for {new_file}")