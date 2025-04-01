""" Module for loading and saving locally the microsoft/Phi-3.5-vision-instruct model and processor

This module is responsible for loading the microsoft/Phi-3.5-vision-instruct model and a processor from
HuggingFace and saving them locally to the computer's file system.

How this module works:
The microsoft/Phi-3.5-vision-instruct model and a processor are loaded from HuggingFace and saved to the
./phi3_vision folder.
"""

from transformers import AutoModelForCausalLM, AutoTokenizer, AutoProcessor

#model_name = "microsoft/Phi-3.5-vision-instruct"
#
## Download model and tokenizer
#model = AutoModelForCausalLM.from_pretrained(model_name)
#tokenizer = AutoTokenizer.from_pretrained(model_name)

# Set model ID and load model and processor
model_id = "microsoft/Phi-3.5-vision-instruct"

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

# Save locally
model.save_pretrained("./phi3_vision", safe_serialization=False)
processor.save_pretrained("./phi3_vision")
