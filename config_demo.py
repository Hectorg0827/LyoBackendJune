"""
Minimal Configuration for Demo
=============================
"""

import os
from typing import Optional

class Settings:
    """Minimal settings for demo."""
    
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./lyo_demo.db")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "demo-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    ALLOWED_HOSTS: list = ["localhost", "127.0.0.1", "0.0.0.0"]
    CORS_ORIGINS: list = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # Google Cloud (Demo values)
    GCP_PROJECT_ID: Optional[str] = os.getenv("GCP_PROJECT_ID")
    GOOGLE_CLOUD_CREDENTIALS: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    # Storage
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "lyoapp-demo-media")
    
    # AI
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # Features
    ENABLE_WEBSOCKETS: bool = True
    ENABLE_AI_TUTOR: bool = True
    ENABLE_GAMIFICATION: bool = True


# Global settings instance
settings = Settings()
