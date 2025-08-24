"""QLoRA Supervised Fine-Tuning Script for Tutor Model.

Environment variables:
 BASE_MODEL (default: google/gemma-2b-it)
 DATA_FILE (path to processed JSONL from prepare_dataset)
 OUTPUT_DIR (default: ./adapters/gemma-tutor-lora)
 MAX_SEQ_LEN (default: 2048)
 EPOCHS (default: 2)
 LR (default: 2e-4)
 RANK (default: 32)
"""
from __future__ import annotations
import os, json
from pathlib import Path
from datasets import load_dataset
from transformers import (AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, TrainingArguments, Trainer, DataCollatorForLanguageModeling)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

BASE_MODEL = os.getenv("BASE_MODEL", "google/gemma-2b-it")
DATA_FILE = os.getenv("DATA_FILE", "./ai_training/sample_dataset_processed.jsonl")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./adapters/gemma-tutor-lora")
MAX_SEQ_LEN = int(os.getenv("MAX_SEQ_LEN", "2048"))
EPOCHS = int(os.getenv("EPOCHS", "2"))
LR = float(os.getenv("LR", "2e-4"))
RANK = int(os.getenv("RANK", "32"))


def load_data(path: str):
    return load_dataset("json", data_files=path, split="train")


def main():
    ds = load_data(DATA_FILE)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype="bfloat16",
    )

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=quant_cfg,
        device_map="auto",
    )

    model = prepare_model_for_kbit_training(model)

    lora_cfg = LoraConfig(
        r=RANK,
        lora_alpha=RANK,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_cfg)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=MAX_SEQ_LEN)

    tokenized = ds.map(tokenize, batched=True, remove_columns=ds.column_names)

    collator = DataCollatorForLanguageModeling(tokenizer, mlm=False)

    args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=32,
        num_train_epochs=EPOCHS,
        learning_rate=LR,
        warmup_ratio=0.05,
        logging_steps=50,
        save_strategy="epoch",
        bf16=True,
        report_to="none",
    )

    trainer = Trainer(model=model, args=args, train_dataset=tokenized, data_collator=collator)
    trainer.train()
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print(f"Saved LoRA adapter to {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
