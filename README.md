# WanderAI — LLM Fine-Tuning & QLoRA Pipeline 🚀

This module contains the complete machine learning pipeline for fine-tuning a Large Language Model (LLM) using **QLoRA (4-bit Quantized Low-Rank Adaptation)** for the **WanderAI Travel Recommendation System**.

---

## 📋 Features

- **Synthetic Instruction Dataset Generator** (`create_dataset.py`): Generates structured travel instruction-response dataset in `travel_dataset.jsonl` format.
- **4-bit NF4 Quantized Training** (`train_model.py`): Fits fine-tuning on low-VRAM GPUs (NVIDIA T4 / RTX 3060/3090 / Google Colab) using `BitsAndBytesConfig`.
- **PEFT / LoRA Adapter Fine-Tuning**: Trains lightweight parameter-efficient adapters targeting projection layers (`q_proj`, `v_proj`, `k_proj`, etc.).
- **Inference Pipeline** (`infer.py`): Merges the trained LoRA adapter with the base model to generate structured JSON travel itineraries.

---

## 🛠️ Step 1: Installation & Setup

Ensure Python 3.9+ and PyTorch (CUDA supported) are installed:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install transformers peft trl bitsandbytes accelerate datasets pandas
```

---

## 🎲 Step 2: Generate Fine-Tuning Dataset

Run the dataset generator to produce `travel_dataset.jsonl`:

```bash
python create_dataset.py
```

This creates 140+ instruction-response pairs formatted for JSON travel itineraries.

---

## 🏋️ Step 3: Run QLoRA Fine-Tuning

To train the model locally or on Google Colab GPU:

```bash
python train_model.py
```

### Key Training Hyperparameters:
| Parameter | Value |
|---|---|
| **Quantization** | 4-bit NormalFloat (NF4) |
| **LoRA Rank ($r$)** | 16 |
| **LoRA Alpha ($\alpha$)** | 32 |
| **Target Modules** | `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |
| **Optimizer** | `paged_adamw_8bit` |
| **Learning Rate** | `2e-4` |
| **Epochs** | 3 |

The trained LoRA weights will be saved to `./fine_tuned_travel_model/`.

---

## 🔮 Step 4: Run Inference

Test the fine-tuned model by running:

```bash
python infer.py
```

---

## ☁️ Running on Google Colab (Free T4 GPU)

1. Open a new notebook in [Google Colab](https://colab.research.google.com/).
2. Change runtime type to **T4 GPU** (`Runtime > Change runtime type > T4 GPU`).
3. Upload `create_dataset.py`, `train_model.py`, and `infer.py`.
4. Run:
```bash
!pip install -q torch transformers peft trl bitsandbytes accelerate datasets
!python create_dataset.py
!python train_model.py
!python infer.py
```
