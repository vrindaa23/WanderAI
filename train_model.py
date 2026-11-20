"""
WanderAI - QLoRA Fine-Tuning Script
====================================
Fine-tunes a Causal LLM (e.g. Mistral-7B / LLaMA-3 / TinyLlama) on travel instruction data.
Uses 4-bit NormalFloat (NF4) quantization via BitsAndBytes to train on consumer/colab GPUs.
"""

import os
import sys
import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from trl import SFTTrainer

# =============================================================================
#  CONFIGURATION & HYPERPARAMETERS
# =============================================================================
MODEL_NAME = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # Fast demo model (swap for Mistral-7B / Llama-3 in production)
DATASET_PATH = "travel_dataset.jsonl"
OUTPUT_DIR = "./fine_tuned_travel_model"

# LoRA Configuration
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

# Training Hyperparameters
NUM_EPOCHS = 3
BATCH_SIZE = 2
GRAD_ACCUMULATION_STEPS = 4
LEARNING_RATE = 2e-4
MAX_SEQ_LENGTH = 1024


def format_prompts(example):
    """Formats Alpaca instruction dataset into a standard prompt template."""
    instruction = example["instruction"]
    output = example["output"]
    formatted = f"<|system|>\nYou are an expert AI Travel Concierge. Output pure valid JSON.\n<|user|>\n{instruction}\n<|assistant|>\n{output}"
    return {"text": formatted}


def main():
    print(f"[*] Starting QLoRA Fine-Tuning for WanderAI...")
    print(f"[*] Base Model : {MODEL_NAME}")
    print(f"[*] Dataset    : {DATASET_PATH}")
    print(f"[*] Output Dir : {OUTPUT_DIR}")

    if not os.path.exists(DATASET_PATH):
        print(f"[!] Dataset file '{DATASET_PATH}' not found. Run 'python create_dataset.py' first.")
        sys.exit(1)

    # 1. 4-bit Quantization Configuration (NF4)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        bnb_4bit_use_double_quant=True,
    )

    # 2. Load Tokenizer & Base Model
    print("[*] Loading Tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    device_map = "auto" if torch.cuda.is_available() else "cpu"
    print(f"[*] Loading Base Model in 4-bit (Device: {device_map})...")

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config if torch.cuda.is_available() else None,
        device_map=device_map,
        trust_remote_code=True,
    )

    if torch.cuda.is_available():
        model = prepare_model_for_kbit_training(model)

    # 3. LoRA Configuration
    peft_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=TARGET_MODULES,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM",
    )

    # 4. Load & Format Dataset
    print("[*] Loading dataset...")
    dataset = load_dataset("json", data_files=DATASET_PATH, split="train")
    dataset = dataset.map(format_prompts)

    # 5. Training Arguments
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUMULATION_STEPS,
        learning_rate=LEARNING_RATE,
        fp16=torch.cuda.is_available(),
        logging_steps=10,
        save_strategy="epoch",
        optim="paged_adamw_8bit" if torch.cuda.is_available() else "adamw_torch",
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        report_to="none",
    )

    # 6. Initialize SFTTrainer
    print("[*] Initializing SFTTrainer...")
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=peft_config,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        tokenizer=tokenizer,
        args=training_args,
    )

    # 7. Start Fine-Tuning Loop
    print("[*] Beginning model training...")
    trainer.train()

    # 8. Save Trained Adapters & Tokenizer
    print(f"[*] Saving fine-tuned LoRA weights to '{OUTPUT_DIR}'...")
    trainer.model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print(f"[+] Fine-tuning complete! Trained LoRA adapter saved to '{OUTPUT_DIR}'.")


if __name__ == "__main__":
    main()
