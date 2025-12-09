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
import logging

logging.basicConfig(level=logging.INFO)

from download_phi_3_5_vision import model, processor

TAG = "image_processing:  "

image_folder = r'./Pictures'


def process_image_files(image=None, filename=None):
    """
    Processes an image either from:
    - a PIL Image object (`image`)
    - or a filename (`filename`) located in `image_folder`
    """

    if isinstance(image, str) and filename is None:
        filename = image
        image = None

    # New way: image is a PIL Image object
    if image is not None:
        new_file = filename or "uploaded_image"
        logging.info(f"{TAG} Processing image directly (PIL object)")

    # Old way: filename is provided
    elif filename is not None:
        file_path = os.path.join(image_folder, filename)

        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        image = Image.open(file_path)
        new_file = filename
        logging.info(f"{TAG} Processing image from disk: {file_path}")

    else:
        raise ValueError("You must provide either a PIL image or a filename")

    # Always use image_id 1 for single images
    placeholder = f"<|image_1|>\n"

    # Define the message for summarization
    messages = [
        {
            "role": "user",
            "content": (
                f"{placeholder}Extract all details from the image exactly as they appear. "
                "Then, create a concise bulleted list summarizing the key points."
            )
        }
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

    processed_file_content = f"Response for {new_file}:\n" + response + "\n\n"

    logging.info(f"{TAG} Processed and saved response for {new_file}")

    return processed_file_content