"""Enhanced settings configuration for LyoBackend with Gemma 3 support."""

import os
from typing import List, Optional, Literal
from pydantic import Field, field_validator
try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for when pydantic_settings is not available
    from pydantic import BaseModel
    class BaseSettings(BaseModel):
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"


class Settings(BaseSettings):
    """Application settings with comprehensive configuration."""
    
    # App Configuration
    APP_NAME: str = "LyoApp Backend"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    API_V1_PREFIX: str = "/v1"
    
    # Database
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_ECHO: bool = Field(default=False, env="DATABASE_ECHO")
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 30
    
    # Redis & Caching  
    REDIS_URL: str = Field(..., env="REDIS_URL")
    CACHE_DEFAULT_TTL: int = 300
    
    # Celery Configuration
    CELERY_BROKER_URL: str = Field(..., env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(..., env="CELERY_RESULT_BACKEND")
    CELERY_TASK_TIMEOUT: int = 1200  # 20 minutes
    
    # JWT Configuration
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080", 
        "http://127.0.0.1:3000"
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # AI Model Configuration (Gemma 3)
    MODEL_PROVIDER: Literal["hf", "s3", "gcs"] = "hf"
    MODEL_ID: str = "google/gemma-2-2b-it"  # Default to available model
    MODEL_URI: Optional[str] = None  # For S3/GCS
    MODEL_DIR: str = "/tmp/models/gemma3"
    MODEL_SHA256: Optional[str] = None
    HF_HOME: str = "/tmp/models/cache"
    
    # API Keys
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    GEMINI_API_KEY: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    YOUTUBE_API_KEY: Optional[str] = Field(default=None, env="YOUTUBE_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    
    # Push Notifications (APNs)
    APNS_KEY_ID: Optional[str] = Field(default=None, env="APNS_KEY_ID")
    APNS_TEAM_ID: Optional[str] = Field(default=None, env="APNS_TEAM_ID")  
    APNS_BUNDLE_ID: str = "com.lyoapp.ios"
    APNS_KEY_FILE: Optional[str] = Field(default=None, env="APNS_KEY_FILE")
    APNS_SANDBOX: bool = True
    
    # Firebase/FCM for Android
    FCM_SERVER_KEY: Optional[str] = Field(default=None, env="FCM_SERVER_KEY")
    
    # Rate Limiting
    API_RATE_LIMIT_PER_MINUTE: int = 100
    API_BURST_LIMIT: int = 20
    MAX_CONCURRENT_REQUESTS: int = 1000
    MAX_REQUEST_SIZE: int = 512 * 1024  # 512KB
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 50
    
    # Content Processing
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_CONTENT_TYPES: List[str] = [
        "video", "article", "ebook", "pdf", "podcast", "course"
    ]
    
    # Monitoring & Observability
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN")
    ENABLE_METRICS: bool = True
    ENABLE_TRACING: bool = True
    LOG_LEVEL: str = "INFO"
    
    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    PASSWORD_MIN_LENGTH: int = 8
    SESSION_TIMEOUT_MINUTES: int = 60
    MAX_LOGIN_ATTEMPTS: int = 5
    ENABLE_RATE_LIMITING: bool = True
    
    # WebSocket Configuration
    WS_MAX_CONNECTIONS: int = 1000
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MESSAGE_QUEUE_SIZE: int = 100
    
    # External Services
    YOUTUBE_DAILY_QUOTA_LIMIT: int = 10000
    AI_DAILY_COST_LIMIT: float = 50.0
    CONTENT_GENERATION_TIMEOUT: int = 300  # 5 minutes
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @field_validator("MODEL_DIR")
    @classmethod
    def validate_model_dir(cls, v):
        """Ensure model directory is absolute path."""
        return os.path.abspath(v)
    
    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v):
        """Validate database URL format."""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        return v
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "allow",  # Allow extra fields in Pydantic v2
    }


# Global settings instance
settings = Settings()
