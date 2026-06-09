"""Enhanced settings configuration for LyoBackend with Gemma 3 support."""

import os
from typing import List, Optional, Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with comprehensive configuration."""
    
    # App Configuration
    APP_NAME: str = "LyoApp Backend"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    API_V1_PREFIX: str = "/v1"
    
    # Database
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./lyo_app.db", env="DATABASE_URL")
    DATABASE_ECHO: bool = Field(default=False, env="DATABASE_ECHO")
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 30
    
    # Redis & Caching  
    REDIS_URL: Optional[str] = Field(default=None, env="REDIS_URL")
    REDIS_HOST: str = Field(default="localhost", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    CACHE_DEFAULT_TTL: int = 300
    
    # Celery Configuration
    CELERY_BROKER_URL: Optional[str] = Field(default=None, env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: Optional[str] = Field(default=None, env="CELERY_RESULT_BACKEND")
    CELERY_TASK_TIMEOUT: int = 1200  # 20 minutes
    
    # JWT Configuration
    # JWT_SECRET_KEY falls back to SECRET_KEY (see derive_jwt_secret below) so
    # that setting a single SECRET_KEY in Railway secures both signing paths.
    JWT_SECRET_KEY: str = Field(default="", env="JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")
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
    
    # AI Model Configuration (Public Model for Testing)
    MODEL_PROVIDER: Literal["hf", "s3", "gcs"] = "hf"
    MODEL_ID: str = "gpt2"  # Using GPT-2 public model for testing
    MODEL_URI: Optional[str] = None  # For S3/GCS
    MODEL_DIR: str = "/tmp/models/ai_model"
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
    SECRET_KEY: str = Field(default="dev_secret_key", env="SECRET_KEY")
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
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra='ignore'
    )

    @field_validator("DEBUG", mode='before')
    @classmethod
    def parse_debug_flag(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production", "prod", "staging"}:
                return False
        return v

    # Known insecure development defaults that must never sign production tokens.
    _INSECURE_SECRETS = {
        "", "dev_jwt_secret_key", "dev_secret_key", "changeme", "secret",
        "dev-only-insecure-secret-key-change-in-production-123456",
    }

    @model_validator(mode='after')
    def derive_jwt_secret(self) -> 'Settings':
        """Source the JWT signing key and refuse insecure defaults in production.

        Historically this module signed JWTs with its own JWT_SECRET_KEY env
        var (default 'dev_jwt_secret_key') while other config modules read
        SECRET_KEY — so a deployment that set only SECRET_KEY still signed
        tokens with the publicly-known dev default. Now JWT_SECRET_KEY falls
        back to SECRET_KEY, and production refuses to boot with either left
        at a known-insecure default.
        """
        if not self.JWT_SECRET_KEY:
            self.JWT_SECRET_KEY = self.SECRET_KEY

        if self.ENVIRONMENT == "production":
            problems = []
            if self.SECRET_KEY in self._INSECURE_SECRETS or len(self.SECRET_KEY) < 32:
                problems.append(
                    "SECRET_KEY is unset/insecure — set a strong unique value "
                    "in Railway project variables"
                )
            if self.JWT_SECRET_KEY in self._INSECURE_SECRETS or len(self.JWT_SECRET_KEY) < 32:
                problems.append(
                    "JWT_SECRET_KEY is unset/insecure — set JWT_SECRET_KEY or a "
                    "strong SECRET_KEY (it is used as the fallback)"
                )
            if problems:
                raise ValueError(
                    "Refusing to start in production with insecure token secrets: "
                    + "; ".join(problems)
                )
        return self

    @model_validator(mode='after')
    def build_urls(self) -> 'Settings':
        """Build Redis and Celery URLs if not provided."""
        if not self.REDIS_URL:
            self.REDIS_URL = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/1"
            
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/2"
            
        return self

    @field_validator("CORS_ORIGINS", mode='before')
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @field_validator("MODEL_DIR")
    def validate_model_dir(cls, v):
        """Ensure model directory is absolute path."""
        return os.path.abspath(v)
    
    @field_validator("DATABASE_URL")
    def validate_database_url(cls, v):
        """Validate database URL format."""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://", "sqlite", "sqlite+aiosqlite://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL or SQLite URL")
        return v




# Global settings instance
settings = Settings()
