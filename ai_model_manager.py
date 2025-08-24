"""
Enhanced AI Model Manager for LyoBackend
Supports local AI model loading with optimizations for course generation.
"""

import asyncio
import logging
import os
import time
from typing import Dict, Any, Optional
from pathlib import Path

import torch
from transformers import (
    AutoTokenizer, 
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    pipeline
)
from huggingface_hub import login, whoami

from lyo_app.core.config import settings
from lyo_app.core.logging import get_logger

logger = get_logger(__name__)


class AIModelManager:
    """
    Manages loading and inference for AI models with optimizations.
    Supports 4-bit quantization for memory efficiency.
    """
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.pipeline = None
        self.model_loaded = False
        self.model_id = settings.MODEL_ID or "gpt2"
        self.model_dir = Path(settings.MODEL_DIR)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Create model directory if it doesn't exist
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized AIModelManager with device: {self.device}")
        logger.info(f"Model ID: {self.model_id}")
        logger.info(f"Model directory: {self.model_dir}")
        
    def _setup_quantization_config(self) -> Optional[BitsAndBytesConfig]:
        """Setup 4-bit quantization configuration for memory efficiency."""
        # Only use quantization for larger models and if CUDA is available
        if torch.cuda.is_available() and self.model_id not in ["gpt2"]:
            return BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16
            )
        return None
    
    async def ensure_hf_authentication(self) -> bool:
        """Ensure Hugging Face authentication for gated models."""
        try:
            # For public models like GPT-2, we don't need authentication
            if self.model_id in ["gpt2", "gpt2-medium", "gpt2-large"]:
                logger.info("Using public model - no authentication required")
                return True
                
            # Check if already authenticated
            user_info = whoami()
            if user_info:
                logger.info(f"Already authenticated with Hugging Face as: {user_info['name']}")
                return True
        except Exception:
            logger.info("Not authenticated with Hugging Face - proceeding with public models only")
            
        # Try to authenticate with token from environment
        hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
        if hf_token:
            try:
                login(token=hf_token)
                logger.info("Successfully authenticated with Hugging Face using token")
                return True
            except Exception as e:
                logger.error(f"Failed to authenticate with HF token: {e}")
        
        logger.warning("Hugging Face authentication not available - using public models only")
        return True  # Continue with public models
    
    async def load_model(self) -> bool:
        """
        Load the AI model with optimizations.
        Returns True if successful, False otherwise.
        """
        if self.model_loaded:
            logger.info("Model already loaded")
            return True
            
        try:
            logger.info(f"Loading AI model: {self.model_id}")
            start_time = time.time()
            
            # Ensure authentication for gated models
            auth_success = await self.ensure_hf_authentication()
            if not auth_success:
                logger.error("Authentication failed, trying to load anyway...")
            
            # Setup quantization for memory efficiency (optional)
            quantization_config = self._setup_quantization_config()
            
            # Load tokenizer
            logger.info("Loading tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                cache_dir=str(self.model_dir),
                trust_remote_code=True
            )
            
            # Add padding token if not present
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Load model
            logger.info("Loading model...")
            model_kwargs = {
                "cache_dir": str(self.model_dir),
                "trust_remote_code": True,
                "low_cpu_mem_usage": True
            }
            
            # Add quantization if available
            if quantization_config:
                model_kwargs["quantization_config"] = quantization_config
                model_kwargs["device_map"] = "auto"
                model_kwargs["torch_dtype"] = torch.bfloat16
            
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                **model_kwargs
            )
            
            # Create text generation pipeline
            logger.info("Creating text generation pipeline...")
            self.pipeline = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if torch.cuda.is_available() else -1
            )
            
            load_time = time.time() - start_time
            self.model_loaded = True
            
            logger.info(f"✅ Model loaded successfully in {load_time:.2f} seconds")
            logger.info(f"Model device: {next(self.model.parameters()).device}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to load model: {str(e)}")
            logger.exception("Model loading error details:")
            return False
    
    def generate_text(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        do_sample: bool = True,
        **kwargs
    ) -> str:
        """
        Generate text using the loaded model.
        
        Args:
            prompt: Input text prompt
            max_new_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)
            top_p: Top-p sampling parameter
            do_sample: Whether to use sampling
            
        Returns:
            Generated text string
        """
        if not self.model_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        try:
            # Generate text
            outputs = self.pipeline(
                prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=do_sample,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                truncation=True,
                **kwargs
            )
            
            # Extract generated text (remove the input prompt)
            full_text = outputs[0]["generated_text"]
            generated_text = full_text[len(prompt):].strip()
            
            return generated_text
            
        except Exception as e:
            logger.error(f"Text generation failed: {str(e)}")
            raise RuntimeError(f"Text generation error: {str(e)}")
    
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self.model_loaded
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model."""
        if not self.model_loaded:
            return {"status": "not_loaded"}
        
        return {
            "status": "loaded",
            "model_id": self.model_id,
            "device": str(next(self.model.parameters()).device) if self.model else "unknown",
            "total_params": sum(p.numel() for p in self.model.parameters()) if self.model else None,
            "memory_footprint": f"{torch.cuda.memory_allocated() / 1024**3:.2f} GB" if torch.cuda.is_available() else "N/A"
        }
    
    def unload_model(self):
        """Unload model to free memory."""
        if self.model:
            del self.model
        if self.tokenizer:
            del self.tokenizer
        if self.pipeline:
            del self.pipeline
        
        # Clear CUDA cache if available
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        self.model_loaded = False
        logger.info("Model unloaded and memory cleared")


# Global model manager instance
model_manager = AIModelManager()


async def initialize_model() -> bool:
    """Initialize the global model manager."""
    try:
        logger.info("Initializing AI model...")
        success = await model_manager.load_model()
        if success:
            logger.info("✅ AI model initialized successfully")
        else:
            logger.error("❌ Failed to initialize AI model")
        return success
    except Exception as e:
        logger.error(f"Model initialization error: {str(e)}")
        return False


def generate_course_content(prompt: str, **kwargs) -> str:
    """
    Generate course content using the loaded model.
    
    Args:
        prompt: The input prompt for content generation
        **kwargs: Additional generation parameters
        
    Returns:
        Generated content string
    """
    if not model_manager.is_loaded():
        raise RuntimeError("Model not loaded. Please initialize the model first.")
    
    return model_manager.generate_text(prompt, **kwargs)
