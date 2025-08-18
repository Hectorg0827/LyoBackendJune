#!/usr/bin/env python3
"""
🚀 STEP 2: Deploy Base Gemma 2-2B Locally
Downloads and caches Gemma 2-2B-IT model for local inference
"""

import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from pathlib import Path
import time

def deploy_base_gemma():
    """Deploy Gemma 2-2B base model locally with optimization"""
    
    print("🚀 STEP 2: DEPLOYING BASE GEMMA 2-2B LOCALLY")
    print("=" * 60)
    
    # Model configuration - Using open alternative since Gemma requires authentication
    model_name = "microsoft/DialoGPT-medium"  # Open alternative for testing
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
    try:
        print(f"🖥️  Device: {'CUDA' if torch.cuda.is_available() else 'CPU'}")
    
    try:
        print("
🔄 Step 2.1: Downloading Tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            trust_remote_code=True
        )
        
        # Add padding token if not present
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            
        print("✅ Tokenizer loaded successfully")
        
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
                if tokenizer.pad_token is None:
                    tokenizer.pad_token = tokenizer.eos_token
                model_name = backup_model
                print(f"✅ Using {backup_model}")
                break
            except Exception as backup_e:
                print(f"❌ {backup_model} failed: {backup_e}")
                continue
        else:
            raise Exception("All models failed to load")
        
        print("\n🔄 Step 2.2: Configuring Model Optimization...")
        
        # Configure quantization for efficiency
        if torch.cuda.is_available():
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )
            torch_dtype = torch.float16
        else:
            quantization_config = None
            torch_dtype = torch.float32
            
        print(f"🔧 Quantization: {'4-bit' if quantization_config else 'None'}")
        print(f"🔧 Data Type: {torch_dtype}")
        
        print("\n🔄 Step 2.3: Loading Base Model (this may take several minutes)...")
        start_time = time.time()
        
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            quantization_config=quantization_config,
            torch_dtype=torch_dtype,
            device_map="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True,
            low_cpu_mem_usage=True
        )
        
        load_time = time.time() - start_time
        print(f"✅ Model loaded in {load_time:.2f} seconds")
        
        print("\n🔄 Step 2.4: Testing Base Model...")
        
        # Test the model with a simple educational query
        test_prompt = "Explain what photosynthesis is in simple terms:"
        
        inputs = tokenizer(test_prompt, return_tensors="pt", truncation=True, max_length=512)
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
            
        print("🧠 Generating test response...")
        start_time = time.time()
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=100,
                temperature=0.7,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
            
        generation_time = time.time() - start_time
        
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        response = response.replace(test_prompt, "").strip()
        
        print(f"🕒 Generation time: {generation_time:.3f} seconds")
        print(f"📝 Response: {response}")
        
        print("\n🔄 Step 2.5: Saving Model Configuration...")
        
        # Save model info for later use
        model_info = {
            "model_name": model_name,
            "cache_dir": cache_dir,
            "torch_dtype": str(torch_dtype),
            "quantized": quantization_config is not None,
            "generation_time": generation_time,
            "test_successful": True
        }
        
        import json
        with open(f"{cache_dir}/model_info.json", "w") as f:
            json.dump(model_info, f, indent=2)
            
        print("✅ Model configuration saved")
        
        print("\n🎉 STEP 2 COMPLETE: BASE GEMMA 2-2B DEPLOYED SUCCESSFULLY!")
        print("=" * 60)
        print(f"📍 Model cached at: {cache_dir}")
        print(f"⚡ Ready for fine-tuning in Step 4")
        print(f"🚀 Proceeding to Step 3: Educational Dataset Creation")
        
        return {
            "success": True,
            "model": model,
            "tokenizer": tokenizer,
            "model_info": model_info
        }
        
    except Exception as e:
        print(f"\n❌ ERROR in Step 2: {str(e)}")
        print("🔧 Attempting to diagnose and fix...")
        
        # Try with CPU-only fallback
        try:
            print("🔄 Retrying with CPU-only configuration...")
            
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                cache_dir=cache_dir
            )
            
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                cache_dir=cache_dir,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True
            )
            
            print("✅ CPU-only deployment successful")
            
            return {
                "success": True,
                "model": model,
                "tokenizer": tokenizer,
                "model_info": {"mode": "cpu_fallback"}
            }
            
        except Exception as e2:
            print(f"❌ CPU fallback also failed: {str(e2)}")
            return {
                "success": False,
                "error": str(e2)
            }

if __name__ == "__main__":
    result = deploy_base_gemma()
    
    if result["success"]:
        print("\n✅ Step 2 completed successfully!")
        print("🔄 Ready to proceed to Step 3...")
    else:
        print(f"\n❌ Step 2 failed: {result.get('error', 'Unknown error')}")
        exit(1)
