"""
Configuration management using Pydantic Settings.
All secrets and environment-specific values are loaded from environment variables.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application settings
    app_name: str = Field(default="LyoApp Backend", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment")
    
    # API settings
    api_prefix: str = Field(default="/api/v1", description="API prefix for versioning")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS allowed origins"
    )
    
    # Database settings
    database_url: str = Field(
        default="postgresql+asyncpg://lyo_user:lyo_password@localhost:5432/lyo_db",
        description="Database URL"
    )
    database_echo: bool = Field(default=False, description="Echo SQL queries")
    
    # Security settings
    secret_key: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for JWT tokens"
    )
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration time in minutes"
    )
    
    # Redis settings
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for caching and Celery"
    )
    
    # Celery settings
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL"
    )
    
    # Email settings
    smtp_server: str = Field(default="smtp.gmail.com", description="SMTP server")
    smtp_port: int = Field(default=587, description="SMTP port")
    smtp_username: Optional[str] = Field(default=None, description="SMTP username")
    smtp_password: Optional[str] = Field(default=None, description="SMTP password")
    smtp_from_email: str = Field(default="noreply@lyoapp.com", description="From email address")
    smtp_use_tls: bool = Field(default=True, description="Use TLS for SMTP")
    
    # API settings
    api_v1_prefix: str = Field(default="/api/v1", description="API v1 prefix")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS allowed origins"
    )
    
    # File upload settings
    max_file_size: int = Field(default=10 * 1024 * 1024, description="Max file size in bytes (10MB)")
    upload_dir: str = Field(default="uploads", description="Upload directory")
    
    # Testing settings
    testing: bool = Field(default=False, description="Testing mode")
    test_database_url: Optional[str] = Field(
        default=None,
        description="Test database URL (optional)"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Export the settings instance
settings = get_settings()
