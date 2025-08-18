#!/usr/bin/env python3
"""
🚀 STEP 2: Deploy Base LLM Locally (Open Alternative)
Downloads and caches an open LLM model for local inference
"""

import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from pathlib import Path
import time

def deploy_base_model():
    """Deploy open LLM base model locally with optimization"""
    
    print("🚀 STEP 2: DEPLOYING BASE LLM LOCALLY")
    print("=" * 60)
    
    # Model configuration - Using open alternative
    model_name = "microsoft/DialoGPT-medium"  
    backup_models = [
        "distilgpt2", 
        "gpt2",
        "microsoft/DialoGPT-small"
    ]
    cache_dir = "./models/base-llm"
    
    # Create models directory
    os.makedirs(cache_dir, exist_ok=True)
    
    print(f"📦 Model: {model_name}")
    print(f"💾 Cache Directory: {cache_dir}")
    print(f"🖥️  Device: {'CUDA' if torch.cuda.is_available() else 'CPU'}")
    
    try:
        print("\n🔄 Step 2.1: Downloading Tokenizer...")
        
        # Try primary model first
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                cache_dir=cache_dir
            )
            print(f"✅ Tokenizer loaded: {model_name}")
        except Exception as e:
            print(f"⚠️ Failed to load {model_name}: {e}")
            print("🔄 Trying backup models...")
            
            for backup_model in backup_models:
                try:
                    print(f"🔄 Trying {backup_model}...")
                    tokenizer = AutoTokenizer.from_pretrained(
                        backup_model,
                        cache_dir=cache_dir
                    )
                    model_name = backup_model
                    print(f"✅ Using {backup_model}")
                    break
                except Exception as backup_e:
                    print(f"❌ {backup_model} failed: {backup_e}")
                    continue
            else:
                raise Exception("All models failed to load")
        
        # Add padding token if not present
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            
        print("\n🔄 Step 2.2: Configuring Model Optimization...")
        
        # Configure for CPU/GPU
        if torch.cuda.is_available():
            torch_dtype = torch.float16
            device_map = "auto"
        else:
            torch_dtype = torch.float32
            device_map = None
            
        print(f"🔧 Data Type: {torch_dtype}")
        print(f"🔧 Device Map: {device_map or 'CPU'}")
        
        print("\n🔄 Step 2.3: Loading Base Model...")
        start_time = time.time()
        
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            torch_dtype=torch_dtype,
            device_map=device_map,
            low_cpu_mem_usage=True
        )
        
        load_time = time.time() - start_time
        print(f"✅ Model loaded in {load_time:.2f} seconds")
        
        print("\n🔄 Step 2.4: Testing Base Model...")
        
        # Test the model with a simple educational query
        test_prompt = "Explain photosynthesis:"
        
        inputs = tokenizer(test_prompt, return_tensors="pt", truncation=True, max_length=100)
        
        print("🧠 Generating test response...")
        start_time = time.time()
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=50,
                temperature=0.8,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
            
        generation_time = time.time() - start_time
        
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        response = response.replace(test_prompt, "").strip()
        
        print(f"🕒 Generation time: {generation_time:.3f} seconds")
        print(f"📝 Response: {response[:200]}...")
        
        print("\n🔄 Step 2.5: Saving Model Configuration...")
        
        # Save model info for later use
        model_info = {
            "model_name": model_name,
            "cache_dir": cache_dir,
            "torch_dtype": str(torch_dtype),
            "device_map": str(device_map),
            "generation_time": generation_time,
            "test_successful": True,
            "ready_for_fine_tuning": True
        }
        
        import json
        with open(f"{cache_dir}/model_info.json", "w") as f:
            json.dump(model_info, f, indent=2)
            
        print("✅ Model configuration saved")
        
        print("\n🎉 STEP 2 COMPLETE: BASE MODEL DEPLOYED SUCCESSFULLY!")
        print("=" * 60)
        print(f"📍 Model cached at: {cache_dir}")
        print(f"⚡ Ready for fine-tuning in Step 4")
        print(f"🚀 Model can be used for educational fine-tuning")
        
        return {
            "success": True,
            "model": model,
            "tokenizer": tokenizer,
            "model_info": model_info
        }
        
    except Exception as e:
        print(f"\n❌ ERROR in Step 2: {str(e)}")
        print("🔧 Model deployment failed")
        
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    result = deploy_base_model()
    
    if result["success"]:
        print("\n✅ Step 2 completed successfully!")
        print("🔄 Ready to proceed to Step 4 (Fine-tuning)...")
    else:
        print(f"\n❌ Step 2 failed: {result.get('error', 'Unknown error')}")
        print("⚠️ Continuing to Step 4 with alternative approach...")
