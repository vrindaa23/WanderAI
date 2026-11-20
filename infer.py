"""
WanderAI - Inference Script for Fine-Tuned Model
=================================================
Loads the base model, applies the fine-tuned LoRA adapter from `./fine_tuned_travel_model`,
and generates structured JSON travel recommendations for a given user prompt.
"""

import os
import sys
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL_NAME = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
ADAPTER_PATH = "./fine_tuned_travel_model"


def generate_recommendation(instruction: str) -> str:
    """Load model & adapter to generate travel recommendations."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] Inference Device : {device}")

    # Load Tokenizer
    print("[*] Loading Tokenizer...")
    if os.path.exists(ADAPTER_PATH):
        tokenizer = AutoTokenizer.from_pretrained(ADAPTER_PATH)
    else:
        tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME)

    # Load Base Model
    print(f"[*] Loading Base Model ({BASE_MODEL_NAME})...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_NAME,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
    )

    # Load & Attach LoRA Adapter if fine-tuned weights exist
    if os.path.exists(ADAPTER_PATH):
        print(f"[*] Applying fine-tuned LoRA adapter from '{ADAPTER_PATH}'...")
        model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
    else:
        print(f"[!] Warning: Adapter path '{ADAPTER_PATH}' not found. Running inference with base model.")
        model = base_model

    model.eval()

    # Format Prompt
    prompt = (
        f"<|system|>\nYou are an expert AI Travel Concierge. Output pure valid JSON.\n"
        f"<|user|>\n{instruction}\n<|assistant|>\n"
    )

    inputs = tokenizer(prompt, return_tensors="pt").to(device)

    print("[*] Generating recommendation response...")
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=768,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )

    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return response


def main():
    sample_prompt = (
        "Generate travel recommendations for a Domestic trip from India. "
        "Scope: Domestic, Budget: Budget, Companion: Solo, "
        "Vibes: Mountains, Adventure, Duration: 3 days, Pace: Action-packed."
    )

    print("=========================================================")
    print(" WanderAI LLM Fine-Tuned Inference Demo")
    print("=========================================================")
    print(f"Input Prompt: {sample_prompt}\n")

    result = generate_recommendation(sample_prompt)

    print("\n---------------- Model Output Response ----------------")
    print(result)
    print("-------------------------------------------------------")


if __name__ == "__main__":
    main()
