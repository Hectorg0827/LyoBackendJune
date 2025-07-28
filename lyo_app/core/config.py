"""
Configuration management using Pydantic Settings.
All secrets and environment-specific values are loaded from environment variables.
"""

import secrets
import re
from functools import lru_cache
from typing import Optional, List

from pydantic import Field, validator, root_validator
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
        default="sqlite+aiosqlite:///./lyo_app_dev.db",
        description="Database URL"
    )
    database_echo: bool = Field(default=False, description="Echo SQL queries")
    
    # Security settings
    secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret key for JWT tokens"
    )
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration time in minutes"
    )
    
    # Monitoring settings
    sentry_dsn: Optional[str] = Field(default=None, description="Sentry DSN for error tracking")
    
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
    
    # File upload settings
    max_file_size: int = Field(default=10 * 1024 * 1024, description="Max file size in bytes (10MB)")
    upload_dir: str = Field(default="uploads", description="Upload directory")
    
    # Testing settings
    testing: bool = Field(default=False, description="Testing mode")
    test_database_url: Optional[str] = Field(
        default=None,
        description="Test database URL (optional)"
    )
    
    # External API Keys
    youtube_api_key: Optional[str] = Field(default=None, description="YouTube Data API v3 key")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")
    
    # Spotify API (for podcast content)
    spotify_client_id: Optional[str] = Field(default=None, description="Spotify Client ID")
    spotify_client_secret: Optional[str] = Field(default=None, description="Spotify Client Secret")
    
    # API Quota Management
    youtube_daily_quota: int = Field(default=10000, description="YouTube API daily quota")
    youtube_cost_per_search: int = Field(default=100, description="YouTube search cost in units")
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(default=60, description="API rate limit per minute")
    
    # Caching
    cache_ttl: int = Field(default=3600, description="Default cache TTL in seconds")
    
    # Podchaser API (missing from requirements)
    podchaser_api_key: Optional[str] = Field(default=None, description="Podchaser API key")
    
    # AI Configuration
    ai_daily_cost_limit: float = Field(default=50.0, description="Daily AI cost limit in USD")
    ai_enable_multi_language: bool = Field(default=True, description="Enable multi-language AI support")
    ai_default_language: str = Field(default="en", description="Default AI language")
    
    # Additional External APIs
    listennotes_api_key: Optional[str] = Field(default=None, description="ListenNotes Podcast API key")
    open_library_api_key: Optional[str] = Field(default=None, description="Open Library API key (optional)")
    
    # Performance Settings
    connection_pool_size: int = Field(default=20, description="Database connection pool size")
    max_overflow: int = Field(default=10, description="Maximum overflow connections")
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    
    @validator('youtube_api_key', 'openai_api_key', 'anthropic_api_key', 'gemini_api_key', 'podchaser_api_key')
    def validate_api_keys(cls, v, field):
        """Validate API key format and length."""
        if v is None:
            return v
        
        # Minimum length check
        if len(v) < 10:
            raise ValueError(f"{field.name} seems too short (minimum 10 characters)")
        
        # Check for obvious placeholder values
        placeholder_patterns = [
            'your-api-key', 'your_api_key', 'replace-me', 
            'change-me', 'placeholder', 'test-key'
        ]
        if any(pattern in v.lower() for pattern in placeholder_patterns):
            raise ValueError(f"{field.name} appears to be a placeholder value")
        
        return v
    
    @validator('secret_key')
    def validate_secret_key(cls, v):
        """Validate secret key strength."""
        if len(v) < 32:
            raise ValueError("Secret key must be at least 32 characters")
        
        # Check for weak patterns
        if v in ['your-secret-key', 'change-me', 'secret']:
            raise ValueError("Secret key is too weak - use a secure random value")
        
        return v
    
    @validator('cors_origins')
    def validate_cors_origins(cls, v):
        """Validate CORS origins format."""
        for origin in v:
            if not origin.startswith(('http://', 'https://')):
                raise ValueError(f"CORS origin '{origin}' must start with http:// or https://")
        return v
    
    @validator('smtp_from_email')
    def validate_email_format(cls, v):
        """Validate email format."""
        if v and '@' not in v:
            raise ValueError("Invalid email format")
        return v
    
    @root_validator
    def validate_environment_specific(cls, values):
        """Validate environment-specific configurations."""
        environment = values.get('environment', 'development')
        
        # Production-specific validations
        if environment == 'production':
            # Require secure secret key in production
            secret_key = values.get('secret_key', '')
            if len(secret_key) < 64:
                raise ValueError("Production environment requires a secret key of at least 64 characters")
            
            # Require database URL in production
            database_url = values.get('database_url', '')
            if 'sqlite' in database_url.lower():
                raise ValueError("SQLite is not recommended for production - use PostgreSQL")
            
            # Require HTTPS CORS origins in production
            cors_origins = values.get('cors_origins', [])
            for origin in cors_origins:
                if origin.startswith('http://') and 'localhost' not in origin:
                    raise ValueError("Production CORS origins should use HTTPS")
        
        return values
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields to prevent validation errors


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Export the settings instance
settings = get_settings()
