""" Module for loading and saving the microsoft/Phi-3.5-vision-instruct model and processor.

This module is responsible for loading the microsoft/Phi-3.5-vision-instruct model and processor, either from
Hugging Face or from the local file system, depending on availability.

How this module works:
First, it checks if the model and processor are already saved locally in the './Phi-3.5-vision' directory.
- If they are found locally, they are loaded from that directory.
- If not, they are downloaded from Hugging Face ('microsoft/Phi-3.5-vision-instruct') and then saved locally
  in the './Phi-3.5-vision' directory.
"""

from transformers import AutoModelForCausalLM, AutoProcessor, BitsAndBytesConfig
import os
import logging
import torch
import bitsandbytes as bnb

logger = logging.getLogger(__name__)

print(bnb.__version__) 
print("CUDA available:", torch.cuda.is_available())
print("CUDA device count:", torch.cuda.device_count())
print("CUDA version:", torch.version.cuda)


# 4-bit quantization config
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
)

# Check if the model and processor are already saved locally
if os.path.exists("./phi_3_5_vision"):
    model_source = "./phi_3_5_vision"
    logger.info("Loading model from local cache...")
else:
    model_source = "microsoft/Phi-3.5-vision-instruct"
    logger.info("Downloading model from HuggingFace...")


# Load the model
model = AutoModelForCausalLM.from_pretrained(
    model_source,
    device_map="auto",
    quantization_config=bnb_config,
    trust_remote_code=True,
    _attn_implementation='eager',
)

#model = AutoModelForCausalLM.from_pretrained(
#    model_source,
#    device_map="cpu",
##    device_map="auto",
#    trust_remote_code=True,
##    torch_dtype="auto",        # For CPU?
#    torch_dtype=torch.float16,  # Use float16 for faster inference on compatible GPUs
#    _attn_implementation='eager',
#    offload_folder="./offload_cache"
#)

#Load the processor
processor = AutoProcessor.from_pretrained(
    model_source,
    trust_remote_code=True,
    num_crops=4
)

# Save the model locally if it's not already saved
if model_source == "microsoft/Phi-3.5-vision-instruct":

    processor.chat_template = processor.tokenizer.chat_template

    #model.save_pretrained("./phi_3_5_vision", safe_serialization=False)
    processor.save_pretrained("./phi_3_5_vision")
    original_model = AutoModelForCausalLM.from_pretrained(
        "microsoft/Phi-3.5-vision-instruct",
        trust_remote_code=True,
        torch_dtype=torch.float16,
    )
    original_model.save_pretrained("./phi_3_5_vision", safe_serialization=False)
    del original_model  # free memory after saving
    logger.info("Original model weights cached locally.")
    logging.info("Model loaded and saved!")

logging.info("Model loaded!")
    
# Check where model layers are loaded
hf_device_map = model.hf_device_map
logging.info(f"Device map: {hf_device_map}")

# Check GPU memory usage
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        allocated = torch.cuda.memory_allocated(i) / 1024**3
        reserved = torch.cuda.memory_reserved(i) / 1024**3
        logging.info(f"GPU {i}: {allocated:.2f} GB allocated, {reserved:.2f} GB reserved")
else:
    logging.warning("No CUDA GPU detected!")