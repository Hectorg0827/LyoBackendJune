"""
Market-Ready Configuration V2
============================

Production-grade configuration management for Google Cloud deployment.
Environment-aware settings with security validation and secret management.
"""

import os
from typing import List, Optional, Any, Dict
from functools import lru_cache

from pydantic import BaseSettings, Field, validator, PostgresDsn, RedisDsn
from pydantic.networks import HttpUrl


class Settings(BaseSettings):
    """Application configuration with environment-specific defaults."""
    
    # Application
    APP_NAME: str = "LyoApp Backend"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # API Configuration
    API_V1_STR: str = "/v1"
    ALLOWED_HOSTS: List[str] = Field(default=["*"], env="ALLOWED_HOSTS")
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        env="CORS_ORIGINS"
    )
    
    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    ENCRYPTION_KEY: Optional[str] = Field(None, env="ENCRYPTION_KEY")
    
    # Database - Google Cloud SQL
    DATABASE_URL: Optional[PostgresDsn] = Field(None, env="DATABASE_URL")
    DATABASE_HOST: str = Field(default="localhost", env="DATABASE_HOST")
    DATABASE_PORT: int = Field(default=5432, env="DATABASE_PORT")
    DATABASE_NAME: str = Field(default="lyo_app", env="DATABASE_NAME")
    DATABASE_USER: str = Field(default="postgres", env="DATABASE_USER")
    DATABASE_PASSWORD: str = Field(default="postgres", env="DATABASE_PASSWORD")
    DATABASE_SSL_MODE: str = Field(default="prefer", env="DATABASE_SSL_MODE")
    DATABASE_POOL_SIZE: int = Field(default=20, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=30, env="DATABASE_MAX_OVERFLOW")
    
    # Redis - Google Memorystore
    REDIS_URL: Optional[RedisDsn] = Field(None, env="REDIS_URL")
    REDIS_HOST: str = Field(default="localhost", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    REDIS_DB: int = Field(default=0, env="REDIS_DB")
    REDIS_PASSWORD: Optional[str] = Field(None, env="REDIS_PASSWORD")
    REDIS_POOL_SIZE: int = Field(default=10, env="REDIS_POOL_SIZE")
    
    # Google Cloud Storage
    GCS_BUCKET_NAME: str = Field(..., env="GCS_BUCKET_NAME")
    GCS_PROJECT_ID: str = Field(..., env="GCS_PROJECT_ID")
    GCS_CREDENTIALS_PATH: Optional[str] = Field(None, env="GCS_CREDENTIALS_PATH")
    GCS_CREDENTIALS_JSON: Optional[str] = Field(None, env="GCS_CREDENTIALS_JSON")
    
    # Google Cloud Secret Manager
    SECRET_MANAGER_PROJECT_ID: Optional[str] = Field(None, env="SECRET_MANAGER_PROJECT_ID")
    
    # AI Configuration
    OPENAI_API_KEY: Optional[str] = Field(None, env="OPENAI_API_KEY")
    GOOGLE_AI_API_KEY: Optional[str] = Field(None, env="GOOGLE_AI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = Field(None, env="ANTHROPIC_API_KEY")
    AI_PROVIDER: str = Field(default="google", env="AI_PROVIDER")  # google, openai, anthropic
    AI_MODEL: str = Field(default="gemini-pro", env="AI_MODEL")
    AI_MAX_TOKENS: int = Field(default=2048, env="AI_MAX_TOKENS")
    AI_TEMPERATURE: float = Field(default=0.7, env="AI_TEMPERATURE")
    AI_TIMEOUT: int = Field(default=30, env="AI_TIMEOUT")
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, env="RATE_LIMIT_PER_MINUTE")
    AI_RATE_LIMIT_PER_MINUTE: int = Field(default=10, env="AI_RATE_LIMIT_PER_MINUTE")
    UPLOAD_RATE_LIMIT_PER_MINUTE: int = Field(default=20, env="UPLOAD_RATE_LIMIT_PER_MINUTE")
    
    # WebSocket
    WEBSOCKET_MAX_CONNECTIONS: int = Field(default=1000, env="WEBSOCKET_MAX_CONNECTIONS")
    WEBSOCKET_HEARTBEAT_INTERVAL: int = Field(default=30, env="WEBSOCKET_HEARTBEAT_INTERVAL")
    
    # Monitoring & Observability
    SENTRY_DSN: Optional[HttpUrl] = Field(None, env="SENTRY_DSN")
    ENABLE_METRICS: bool = Field(default=True, env="ENABLE_METRICS")
    METRICS_PORT: int = Field(default=9090, env="METRICS_PORT")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    STRUCTURED_LOGGING: bool = Field(default=True, env="STRUCTURED_LOGGING")
    
    # Feature Flags
    ENABLE_SEARCH: bool = Field(default=True, env="ENABLE_SEARCH")
    ENABLE_AI_TUTOR: bool = Field(default=True, env="ENABLE_AI_TUTOR")
    ENABLE_WEBSOCKETS: bool = Field(default=True, env="ENABLE_WEBSOCKETS")
    ENABLE_MODERATION: bool = Field(default=True, env="ENABLE_MODERATION")
    ENABLE_ANALYTICS: bool = Field(default=True, env="ENABLE_ANALYTICS")
    ENABLE_ADVANCED_SOCRATIC: bool = Field(default=True, env="ENABLE_ADVANCED_SOCRATIC")
    ENABLE_RETRIEVAL_AUGMENTATION: bool = Field(default=False, env="ENABLE_RETRIEVAL_AUGMENTATION")
    ENABLE_ADAPTIVE_DIFFICULTY: bool = Field(default=True, env="ENABLE_ADAPTIVE_DIFFICULTY")
    ENABLE_HISTORY_SUMMARIZATION: bool = Field(default=True, env="ENABLE_HISTORY_SUMMARIZATION")
    ENABLE_STRATEGY_METRICS: bool = Field(default=True, env="ENABLE_STRATEGY_METRICS")
    ENABLE_SUPERIOR_AI_MODE: bool = Field(default=True, env="ENABLE_SUPERIOR_AI_MODE")
    
    # Content & Media
    MAX_FILE_SIZE_MB: int = Field(default=100, env="MAX_FILE_SIZE_MB")
    ALLOWED_FILE_TYPES: List[str] = Field(
        default=["image/jpeg", "image/png", "image/gif", "video/mp4", "application/pdf"],
        env="ALLOWED_FILE_TYPES"
    )
    MEDIA_CDN_URL: Optional[HttpUrl] = Field(None, env="MEDIA_CDN_URL")
    
    # Search - pgvector
    ENABLE_VECTOR_SEARCH: bool = Field(default=True, env="ENABLE_VECTOR_SEARCH")
    VECTOR_DIMENSION: int = Field(default=1536, env="VECTOR_DIMENSION")  # OpenAI embedding size
    SEARCH_RESULTS_LIMIT: int = Field(default=50, env="SEARCH_RESULTS_LIMIT")
    
    # Moderation
    ENABLE_AUTO_MODERATION: bool = Field(default=True, env="ENABLE_AUTO_MODERATION")
    MODERATION_CONFIDENCE_THRESHOLD: float = Field(default=0.8, env="MODERATION_CONFIDENCE_THRESHOLD")
    
    # Notifications
    FCM_CREDENTIALS_PATH: Optional[str] = Field(None, env="FCM_CREDENTIALS_PATH")
    APNS_KEY_PATH: Optional[str] = Field(None, env="APNS_KEY_PATH")
    APNS_KEY_ID: Optional[str] = Field(None, env="APNS_KEY_ID")
    APNS_TEAM_ID: Optional[str] = Field(None, env="APNS_TEAM_ID")
    
    # Email (SendGrid/SMTP)
    SENDGRID_API_KEY: Optional[str] = Field(None, env="SENDGRID_API_KEY")
    SMTP_HOST: Optional[str] = Field(None, env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USERNAME: Optional[str] = Field(None, env="SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = Field(None, env="SMTP_PASSWORD")
    FROM_EMAIL: str = Field(default="noreply@lyoapp.com", env="FROM_EMAIL")
    
    # Apple Sign-In
    APPLE_CLIENT_ID: Optional[str] = Field(None, env="APPLE_CLIENT_ID")
    APPLE_TEAM_ID: Optional[str] = Field(None, env="APPLE_TEAM_ID")
    APPLE_KEY_ID: Optional[str] = Field(None, env="APPLE_KEY_ID")
    APPLE_PRIVATE_KEY_PATH: Optional[str] = Field(None, env="APPLE_PRIVATE_KEY_PATH")
    
    # Analytics - BigQuery
    BIGQUERY_PROJECT_ID: Optional[str] = Field(None, env="BIGQUERY_PROJECT_ID")
    BIGQUERY_DATASET_ID: str = Field(default="lyo_analytics", env="BIGQUERY_DATASET_ID")
    
    # Pub/Sub for events
    PUBSUB_PROJECT_ID: Optional[str] = Field(None, env="PUBSUB_PROJECT_ID")
    EVENTS_TOPIC: str = Field(default="lyo-events", env="EVENTS_TOPIC")
    
    @validator("DATABASE_URL", pre=True)
    def build_database_url(cls, v: Optional[str], values: Dict[str, Any]) -> str:
        """Build database URL from components if not provided."""
        if isinstance(v, str):
            return v
        
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            user=values.get("DATABASE_USER"),
            password=values.get("DATABASE_PASSWORD"),
            host=values.get("DATABASE_HOST"),
            port=str(values.get("DATABASE_PORT")),
            path=f"/{values.get('DATABASE_NAME') or ''}",
            query=f"sslmode={values.get('DATABASE_SSL_MODE', 'prefer')}"
        )
    
    @validator("REDIS_URL", pre=True)
    def build_redis_url(cls, v: Optional[str], values: Dict[str, Any]) -> str:
        """Build Redis URL from components if not provided."""
        if isinstance(v, str):
            return v
        
        password = values.get("REDIS_PASSWORD")
        if password:
            return f"redis://:{password}@{values.get('REDIS_HOST')}:{values.get('REDIS_PORT')}/{values.get('REDIS_DB')}"
        else:
            return f"redis://{values.get('REDIS_HOST')}:{values.get('REDIS_PORT')}/{values.get('REDIS_DB')}"
    
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("ALLOWED_HOSTS", pre=True)
    def parse_allowed_hosts(cls, v):
        """Parse allowed hosts from string or list."""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",")]
        return v
    
    @validator("ALLOWED_FILE_TYPES", pre=True)
    def parse_file_types(cls, v):
        """Parse allowed file types from string or list."""
        if isinstance(v, str):
            return [mime.strip() for mime in v.split(",")]
        return v
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT.lower() in ["development", "dev", "local"]
    
    def is_staging(self) -> bool:
        """Check if running in staging environment."""
        return self.ENVIRONMENT.lower() in ["staging", "stage"]
    
    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic."""
        return str(self.DATABASE_URL).replace("+asyncpg", "")
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
