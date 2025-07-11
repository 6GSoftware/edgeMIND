""" Module for loading and saving the microsoft/Phi-3.5-vision-instruct model and processor.

This module is responsible for loading the microsoft/Phi-3.5-vision-instruct model and processor, either from
Hugging Face or from the local file system, depending on availability.

How this module works:
First, it checks if the model and processor are already saved locally in the './Phi-3.5-vision' directory.
- If they are found locally, they are loaded from that directory.
- If not, they are downloaded from Hugging Face ('microsoft/Phi-3.5-vision-instruct') and then saved locally
  in the './Phi-3.5-vision' directory.
"""

from transformers import AutoModelForCausalLM, AutoProcessor
import os
import logging

logger = logging.getLogger(__name__)

# Check if the model and processor are already saved locally.
if os.path.exists("./Phi-3.5-vision"):
    model_source = "./Phi-3.5-vision"
else:
    model_source = "microsoft/Phi-3.5-vision-instruct"

#Load the model
model = AutoModelForCausalLM.from_pretrained(
    model_source,
    device_map="auto",
    trust_remote_code=True,
    torch_dtype="auto",
    _attn_implementation='eager'
)

#Load the processor
processor = AutoProcessor.from_pretrained(
    model_source,
    trust_remote_code=True,
    num_crops=4
)

# Save the model locally if it's not already saved
if model_source == "microsoft/Phi-3.5-vision-instruct":

    processor.chat_template = processor.tokenizer.chat_template

    model.save_pretrained("./Phi-3.5-vision", safe_serialization=False)
    processor.save_pretrained("./Phi-3.5-vision")
    logging.info("Model loaded and saved!")
else:
    logging.info("Model loaded!")