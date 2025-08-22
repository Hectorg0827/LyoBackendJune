"""Gemma 3 model loading and management system."""

import os
import hashlib
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from lyo_app.core.settings import settings
from lyo_app.core.problems import ModelNotAvailableProblem

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a loaded model."""
    name: str
    version: Optional[str]
    path: str
    checksum: Optional[str]
    loaded_at: datetime
    size_bytes: int


class ModelManager:
    """Manages Gemma 3 model download, verification, and loading."""
    
    def __init__(self):
        self.model_info: Optional[ModelInfo] = None
        self._model_instance = None
        
    def ensure_model(self) -> ModelInfo:
        """
        Ensure model is available and verified.
        Downloads if necessary, verifies checksum.
        
        Returns:
            ModelInfo with model details
            
        Raises:
            ModelNotAvailableProblem: If model cannot be loaded
        """
        model_path = Path(settings.MODEL_DIR)
        
        # Check if model exists and is valid
        if self._is_model_valid(model_path):
            logger.info(f"Model already available at {model_path}")
            return self._load_model_info(model_path)
        
        # Download model
        logger.info(f"Downloading model to {model_path}")
        self._download_model(model_path)
        
        # Verify checksum if provided
        if settings.MODEL_SHA256:
            if not self._verify_checksum(model_path, settings.MODEL_SHA256):
                shutil.rmtree(model_path, ignore_errors=True)
                raise ModelNotAvailableProblem(f"Model checksum verification failed for {settings.MODEL_ID}")
        
        return self._load_model_info(model_path)
    
    def _is_model_valid(self, model_path: Path) -> bool:
        """Check if model directory exists and contains expected files."""
        if not model_path.exists():
            return False
            
        # Check for essential model files
        expected_files = [
            "config.json",
            "tokenizer.json",
        ]
        
        # Look for model weight files (various formats)
        weight_patterns = [
            "model*.safetensors",
            "pytorch_model*.bin", 
            "model*.bin"
        ]
        
        # Check essential files exist
        for file_name in expected_files:
            if not (model_path / file_name).exists():
                logger.warning(f"Missing essential file: {file_name}")
                return False
        
        # Check at least one weight file exists
        has_weights = False
        for pattern in weight_patterns:
            if list(model_path.glob(pattern)):
                has_weights = True
                break
        
        if not has_weights:
            logger.warning("No model weight files found")
            return False
        
        # Verify checksum if configured
        if settings.MODEL_SHA256:
            return self._verify_checksum(model_path, settings.MODEL_SHA256)
        
        return True
    
    def _download_model(self, model_path: Path):
        """Download model from configured provider."""
        model_path.mkdir(parents=True, exist_ok=True)
        
        try:
            if settings.MODEL_PROVIDER == "hf":
                self._download_from_huggingface(model_path)
            elif settings.MODEL_PROVIDER == "s3":
                self._download_from_s3(model_path)
            elif settings.MODEL_PROVIDER == "gcs":
                self._download_from_gcs(model_path)
            else:
                raise ModelNotAvailableProblem(f"Unsupported model provider: {settings.MODEL_PROVIDER}")
                
        except Exception as e:
            # Clean up on failure
            shutil.rmtree(model_path, ignore_errors=True)
            raise ModelNotAvailableProblem(f"Model download failed: {str(e)}")
    
    def _download_from_huggingface(self, model_path: Path):
        """Download model from Hugging Face Hub."""
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            raise ModelNotAvailableProblem("huggingface_hub not installed")
        
        # Set cache directory if configured
        if settings.HF_HOME:
            os.environ["HF_HOME"] = settings.HF_HOME
        
        logger.info(f"Downloading {settings.MODEL_ID} from Hugging Face Hub")
        
        snapshot_download(
            repo_id=settings.MODEL_ID,
            local_dir=str(model_path),
            local_dir_use_symlinks=False,
            ignore_patterns=["*.md", "*.txt", ".git*"]
        )
        
        logger.info(f"Successfully downloaded {settings.MODEL_ID}")
    
    def _download_from_s3(self, model_path: Path):
        """Download model from S3."""
        if not settings.MODEL_URI:
            raise ModelNotAvailableProblem("MODEL_URI not configured for S3 provider")
        
        try:
            import boto3
        except ImportError:
            raise ModelNotAvailableProblem("boto3 not installed for S3 download")
        
        # Parse S3 URI: s3://bucket/path/to/model.tar.gz
        uri = settings.MODEL_URI
        if not uri.startswith("s3://"):
            raise ModelNotAvailableProblem(f"Invalid S3 URI: {uri}")
        
        bucket_and_key = uri[5:]  # Remove s3://
        bucket, key = bucket_and_key.split("/", 1)
        
        s3 = boto3.client("s3")
        
        with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp_file:
            logger.info(f"Downloading from S3: {bucket}/{key}")
            s3.download_file(bucket, key, tmp_file.name)
            
            # Extract tarball
            import tarfile
            with tarfile.open(tmp_file.name, "r:gz") as tar:
                tar.extractall(model_path)
        
        logger.info(f"Successfully downloaded model from S3")
    
    def _download_from_gcs(self, model_path: Path):
        """Download model from Google Cloud Storage."""
        if not settings.MODEL_URI:
            raise ModelNotAvailableProblem("MODEL_URI not configured for GCS provider")
        
        try:
            from google.cloud import storage
        except ImportError:
            raise ModelNotAvailableProblem("google-cloud-storage not installed for GCS download")
        
        # Parse GCS URI: gs://bucket/path/to/model.tar.gz
        uri = settings.MODEL_URI
        if not uri.startswith("gs://"):
            raise ModelNotAvailableProblem(f"Invalid GCS URI: {uri}")
        
        bucket_and_path = uri[5:]  # Remove gs://
        bucket_name, blob_path = bucket_and_path.split("/", 1)
        
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp_file:
            logger.info(f"Downloading from GCS: {bucket_name}/{blob_path}")
            blob.download_to_filename(tmp_file.name)
            
            # Extract tarball
            import tarfile
            with tarfile.open(tmp_file.name, "r:gz") as tar:
                tar.extractall(model_path)
        
        logger.info(f"Successfully downloaded model from GCS")
    
    def _verify_checksum(self, model_path: Path, expected_checksum: str) -> bool:
        """Verify model directory checksum."""
        logger.info("Verifying model checksum...")
        
        # Calculate checksum of all files in sorted order
        hasher = hashlib.sha256()
        
        for file_path in sorted(model_path.rglob("*")):
            if file_path.is_file():
                with open(file_path, "rb") as f:
                    while chunk := f.read(8192):
                        hasher.update(chunk)
        
        calculated_checksum = hasher.hexdigest()
        
        if calculated_checksum == expected_checksum:
            logger.info("Model checksum verification passed")
            return True
        else:
            logger.error(f"Checksum mismatch. Expected: {expected_checksum}, Got: {calculated_checksum}")
            return False
    
    def _load_model_info(self, model_path: Path) -> ModelInfo:
        """Load model information from path."""
        # Calculate directory size
        total_size = sum(f.stat().st_size for f in model_path.rglob('*') if f.is_file())
        
        # Try to read model version from config
        version = None
        config_path = model_path / "config.json"
        if config_path.exists():
            try:
                import json
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    version = config.get('model_version') or config.get('version')
            except Exception:
                logger.warning("Could not read model version from config.json")
        
        model_info = ModelInfo(
            name=settings.MODEL_ID,
            version=version,
            path=str(model_path),
            checksum=settings.MODEL_SHA256,
            loaded_at=datetime.utcnow(),
            size_bytes=total_size
        )
        
        self.model_info = model_info
        logger.info(f"Model info loaded: {model_info.name} ({model_info.size_bytes / 1024 / 1024:.1f} MB)")
        
        return model_info
    
    def get_model_instance(self):
        """
        Get the actual model instance for inference.
        
        This is a placeholder - implement based on your inference needs:
        - Transformers pipeline
        - vLLM engine
        - Custom inference wrapper
        """
        if not self.model_info:
            self.ensure_model()
        
        if self._model_instance is None:
            self._model_instance = self._load_model_for_inference()
        
        return self._model_instance
    
    def _load_model_for_inference(self):
        """
        Load model for inference.
        
        Implement this based on your inference framework:
        - For Transformers: pipeline("text-generation", model=path)
        - For vLLM: LLM(model=path)
        - For custom: your inference wrapper
        """
        model_path = self.model_info.path
        
        try:
            # Example: Transformers pipeline
            from transformers import pipeline
            
            logger.info(f"Loading model for inference from {model_path}")
            
            model_instance = pipeline(
                "text-generation",
                model=model_path,
                device_map="auto",
                torch_dtype="auto",
                trust_remote_code=True
            )
            
            logger.info("Model loaded successfully for inference")
            return model_instance
            
        except ImportError:
            logger.warning("Transformers not available, using mock model")
            return MockModel()
        except Exception as e:
            logger.error(f"Failed to load model for inference: {e}")
            raise ModelNotAvailableProblem(f"Failed to load model: {str(e)}")
    
    def health_check(self) -> Dict[str, Any]:
        """Check model health status."""
        try:
            model_info = self.ensure_model()
            return {
                "status": "healthy",
                "model_name": model_info.name,
                "model_version": model_info.version,
                "checksum_verified": bool(settings.MODEL_SHA256),
                "last_loaded_at": model_info.loaded_at,
                "size_mb": round(model_info.size_bytes / 1024 / 1024, 1)
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "model_name": settings.MODEL_ID
            }


class MockModel:
    """Mock model for development/testing when real model not available."""
    
    def __call__(self, prompt: str, **kwargs) -> str:
        """Generate mock response."""
        return f"Mock response for: {prompt[:50]}..."


# Global model manager instance
model_manager = ModelManager()
