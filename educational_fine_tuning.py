#!/usr/bin/env python3
"""
🚀 STEP 4: LoRA Fine-tuning for Educational Specialization
Fine-tunes the base model for educational tasks using LoRA (Low-Rank Adaptation)
"""

import os
import json
import torch
from pathlib import Path
from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer, 
    TrainingArguments,
    DataCollatorForLanguageModeling
)
from peft import LoraConfig, get_peft_model, TaskType, PeftModel
from trl import SFTTrainer
from datasets import Dataset
import time

class EducationalFineTuner:
    """Fine-tunes LLM for educational specialization using LoRA"""
    
    def __init__(self):
        self.datasets_dir = Path("./datasets")
        self.models_dir = Path("./models")
        self.fine_tuned_dir = self.models_dir / "educational-tuned"
        self.fine_tuned_dir.mkdir(parents=True, exist_ok=True)
        
    def load_base_model(self):
        """Load the base model from Step 2"""
        
        print("🔄 Loading base model from Step 2...")
        
        # Check for model info from Step 2
        base_model_dir = self.models_dir / "base-llm"
        model_info_file = base_model_dir / "model_info.json"
        
        if model_info_file.exists():
            with open(model_info_file, 'r') as f:
                model_info = json.load(f)
            model_name = model_info["model_name"]
            cache_dir = model_info["cache_dir"]
            print(f"✅ Using cached model: {model_name}")
        else:
            # Fallback to default
            model_name = "distilgpt2"
            cache_dir = str(base_model_dir)
            print(f"⚠️ No cached model found, using fallback: {model_name}")
        
        try:
            # Load tokenizer
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                cache_dir=cache_dir
            )
            
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
                
            # Load model
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                cache_dir=cache_dir,
                torch_dtype=torch.float32 if not torch.cuda.is_available() else torch.float16,
                device_map="auto" if torch.cuda.is_available() else None
            )
            
            print(f"✅ Base model loaded successfully")
            return model, tokenizer, model_name
            
        except Exception as e:
            print(f"❌ Failed to load base model: {e}")
            raise
    
    def prepare_datasets(self):
        """Load and prepare educational datasets for training"""
        
        print("🔄 Loading educational datasets...")
        
        # Load combined training dataset
        training_file = self.datasets_dir / "combined_training.json"
        
        if not training_file.exists():
            print("❌ Training datasets not found! Run Step 3 first.")
            raise FileNotFoundError("Training datasets missing")
        
        with open(training_file, 'r') as f:
            training_data = json.load(f)
        
        print(f"✅ Loaded {len(training_data)} training examples")
        
        # Convert to HuggingFace Dataset format
        texts = [example["text"] for example in training_data]
        dataset = Dataset.from_dict({"text": texts})
        
        # Split into train/validation
        train_size = int(0.8 * len(dataset))
        train_dataset = dataset.select(range(train_size))
        eval_dataset = dataset.select(range(train_size, len(dataset)))
        
        print(f"✅ Training set: {len(train_dataset)} examples")
        print(f"✅ Validation set: {len(eval_dataset)} examples")
        
        return train_dataset, eval_dataset
    
    def setup_lora_config(self):
        """Configure LoRA for efficient fine-tuning"""
        
        print("🔄 Setting up LoRA configuration...")
        
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=16,  # Low rank adaptation
            lora_alpha=32,
            lora_dropout=0.1,
            target_modules=["c_attn", "c_proj"] if "gpt" in str(self.model_name).lower() else None,
            bias="none",
        )
        
        print("✅ LoRA configuration ready")
        return lora_config
    
    def fine_tune_model(self):
        """Execute the fine-tuning process"""
        
        print("🚀 STEP 4: LORA FINE-TUNING FOR EDUCATIONAL SPECIALIZATION")
        print("=" * 70)
        
        try:
            # Step 4.1: Load base model
            print("\n🔄 Step 4.1: Loading Base Model...")
            model, tokenizer, model_name = self.load_base_model()
            self.model_name = model_name
            
            # Step 4.2: Prepare datasets
            print("\n🔄 Step 4.2: Preparing Training Data...")
            train_dataset, eval_dataset = self.prepare_datasets()
            
            # Step 4.3: Setup LoRA
            print("\n🔄 Step 4.3: Configuring LoRA...")
            lora_config = self.setup_lora_config()
            
            # Apply LoRA to model
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()
            
            # Step 4.4: Configure training
            print("\n🔄 Step 4.4: Setting Up Training...")
            
            # Training arguments optimized for educational fine-tuning
            training_args = TrainingArguments(
                output_dir=str(self.fine_tuned_dir),
                per_device_train_batch_size=2,  # Small batch size for stability
                per_device_eval_batch_size=2,
                gradient_accumulation_steps=4,   # Effective batch size = 8
                num_train_epochs=3,              # Quick training for demo
                learning_rate=2e-4,              # LoRA learning rate
                warmup_steps=10,
                logging_steps=10,
                evaluation_strategy="steps",
                eval_steps=50,
                save_steps=100,
                save_total_limit=2,
                load_best_model_at_end=True,
                metric_for_best_model="eval_loss",
                greater_is_better=False,
                report_to=None,  # Disable wandb/tensorboard
                remove_unused_columns=False,
                dataloader_pin_memory=False,
            )
            
            # Step 4.5: Initialize trainer
            print("\n🔄 Step 4.5: Initializing SFT Trainer...")
            
            trainer = SFTTrainer(
                model=model,
                tokenizer=tokenizer,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                args=training_args,
                dataset_text_field="text",
                max_seq_length=512,
                packing=False,
                data_collator=DataCollatorForLanguageModeling(
                    tokenizer=tokenizer,
                    mlm=False
                )
            )
            
            print("✅ Trainer initialized successfully")
            
            # Step 4.6: Execute training
            print("\n🔄 Step 4.6: Starting Fine-tuning Training...")
            print("⚡ This will take several minutes...")
            
            start_time = time.time()
            
            # Start training
            trainer.train()
            
            training_time = time.time() - start_time
            print(f"✅ Training completed in {training_time:.2f} seconds")
            
            # Step 4.7: Save fine-tuned model
            print("\n🔄 Step 4.7: Saving Fine-tuned Model...")
            
            # Save the LoRA adapter
            model.save_pretrained(self.fine_tuned_dir)
            tokenizer.save_pretrained(self.fine_tuned_dir)
            
            # Save training info
            training_info = {
                "base_model": model_name,
                "training_time": training_time,
                "training_examples": len(train_dataset),
                "validation_examples": len(eval_dataset),
                "lora_config": {
                    "r": lora_config.r,
                    "lora_alpha": lora_config.lora_alpha,
                    "target_modules": lora_config.target_modules,
                },
                "training_args": {
                    "learning_rate": training_args.learning_rate,
                    "num_epochs": training_args.num_train_epochs,
                    "batch_size": training_args.per_device_train_batch_size,
                },
                "fine_tuning_complete": True,
                "ready_for_production": True
            }
            
            with open(self.fine_tuned_dir / "training_info.json", "w") as f:
                json.dump(training_info, f, indent=2)
            
            print("✅ Fine-tuned model saved successfully")
            
            # Step 4.8: Test fine-tuned model
            print("\n🔄 Step 4.8: Testing Fine-tuned Model...")
            
            test_prompt = "<|im_start|>system\nYou are a helpful educational tutor.<|im_end|>\n<|im_start|>user\nExplain photosynthesis simply<|im_end|>\n<|im_start|>assistant\n"
            
            inputs = tokenizer(test_prompt, return_tensors="pt", truncation=True, max_length=200)
            
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=100,
                    temperature=0.7,
                    do_sample=True,
                    pad_token_id=tokenizer.eos_token_id
                )
            
            response = tokenizer.decode(outputs[0], skip_special_tokens=True)
            response = response.replace(test_prompt, "").strip()
            
            print(f"📝 Fine-tuned Response: {response}")
            
            print("\n🎉 STEP 4 COMPLETE: EDUCATIONAL FINE-TUNING SUCCESSFUL!")
            print("=" * 70)
            print(f"📍 Fine-tuned model saved at: {self.fine_tuned_dir}")
            print(f"⚡ Training time: {training_time:.2f} seconds")
            print(f"🎯 Educational specialization: COMPLETE")
            print(f"🚀 Ready for Step 5: Production Integration")
            
            return {
                "success": True,
                "model_path": str(self.fine_tuned_dir),
                "training_info": training_info
            }
            
        except Exception as e:
            print(f"\n❌ ERROR in Step 4: {str(e)}")
            print("🔧 Fine-tuning failed, but continuing to Step 5...")
            
            # Create mock fine-tuned info for Step 5
            mock_info = {
                "success": False,
                "error": str(e),
                "fallback_mode": True,
                "base_model_available": True
            }
            
            return mock_info

def main():
    fine_tuner = EducationalFineTuner()
    result = fine_tuner.fine_tune_model()
    
    if result["success"]:
        print("\n✅ Step 4 completed successfully!")
        print("🔄 Ready to proceed to Step 5...")
    else:
        print(f"\n⚠️ Step 4 encountered issues: {result.get('error', 'Unknown error')}")
        print("🔄 Proceeding to Step 5 with fallback configuration...")
    
    return result

if __name__ == "__main__":
    main()
