"""
This module is only for downloading the LLM model from Huggingface and saving it locally on the machine.
You should run this only once per device and everytime you want to update the model.
"""

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# Load the text generation model and tokenizer from Hugging Face Hub
model = AutoModelForCausalLM.from_pretrained(
    "microsoft/Phi-3.5-mini-instruct", 
    device_map="auto",  # Automatically choose the device
    torch_dtype=torch.float32,  # Use float32 for CPU
    trust_remote_code=True,
)
tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3.5-mini-instruct")

model.save_pretrained("./saved_LLM_model")
tokenizer.save_pretrained("./saved_LLM_model")