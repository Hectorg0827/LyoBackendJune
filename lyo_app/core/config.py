"""
Configuration management using Pydantic Settings.
All secrets and environment-specific values are loaded from environment variables.
"""

import secrets
import re
from functools import lru_cache
from typing import Optional, List, Union

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application settings
    app_name: str = Field(default="LyoApp Backend", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment")
    base_url: str = Field(default="http://localhost:8000", description="Base URL for constructing links (verification, password reset, etc.)")
    
    # API settings
    api_prefix: str = Field(default="/api/v1", description="API prefix for versioning")
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS allowed origins"
    )
    
    # Database settings
    database_url: str = Field(
        default="sqlite+aiosqlite:///./lyo_app_dev.db",
        description="Database URL"
    )
    database_echo: bool = Field(default=False, description="Echo SQL queries")
    connection_pool_size: int = Field(default=20, description="Database connection pool size")
    max_overflow: int = Field(default=30, description="Database max overflow connections")
    
    # Security settings
    secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret key for JWT tokens"
    )
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration time in minutes"
    )
    refresh_token_expire_days: int = Field(
        default=7, description="Refresh token expiration time in days"
    )
    
    # Monitoring settings
    sentry_dsn: Optional[str] = Field(default=None, description="Sentry DSN for error tracking")
    
    # Redis settings - support REDIS_HOST/REDIS_PORT for Cloud Run
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: str = Field(default="6379", description="Redis port")
    redis_url: Optional[str] = Field(default=None, description="Redis URL for caching and Celery (optional, built from host/port if not set)")
    
    @property
    def effective_redis_url(self) -> str:
        """Get the effective Redis URL, building from host/port if REDIS_URL not set."""
        import os
        # Priority: REDIS_URL env var > REDIS_HOST:REDIS_PORT env vars > defaults
        env_redis_url = os.getenv("REDIS_URL")
        if env_redis_url:
            return env_redis_url
        host = os.getenv("REDIS_HOST", self.redis_host)
        port = os.getenv("REDIS_PORT", self.redis_port)
        return f"redis://{host}:{port}/0"
    
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
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")
    
    # OpenAI Configuration (for conversations and TTS)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key for ChatGPT and TTS")
    spotify_client_id: Optional[str] = Field(default=None, description="Spotify Client ID")
    spotify_client_secret: Optional[str] = Field(default=None, description="Spotify Client Secret")
    # Note: At runtime, if these are None we attempt secret manager fallback where used.
    
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
    
    # OpenAI Configuration (for conversations and TTS)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key for ChatGPT and TTS")
    
    # Dual AI System Configuration
    ai_brain_provider: str = Field(default="gemini", description="AI Brain provider for reasoning (gemini)")
    ai_conversation_provider: str = Field(default="openai", description="AI Conversation provider (openai)")
    ai_hybrid_mode: bool = Field(default=True, description="Enable hybrid AI mode")
    
    # Google Cloud Configuration
    gcs_bucket: Optional[str] = Field(default=None, description="Google Cloud Storage bucket name")
    gcs_project_id: Optional[str] = Field(default=None, description="Google Cloud Project ID")
    google_application_credentials: Optional[str] = Field(default=None, description="Path to GCS service account JSON")
    
    # Performance Settings
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    
    # Production Enhancement Settings
    # Storage Configuration
    storage_provider: str = Field(default="gcs", description="Storage provider: local, gcs, aws_s3, cloudflare_r2")
    storage_bucket: Optional[str] = Field(default=None, description="Storage bucket name")
    cdn_domain: Optional[str] = Field(default=None, description="CDN domain for faster file delivery")
    
    # AWS Configuration
    aws_access_key_id: Optional[str] = Field(default=None, description="AWS Access Key")
    aws_secret_access_key: Optional[str] = Field(default=None, description="AWS Secret Key")
    aws_region: str = Field(default="us-east-1", description="AWS region")
    
    # Cloudflare R2 Configuration (S3-compatible, cheaper)
    r2_endpoint: Optional[str] = Field(default=None, description="Cloudflare R2 endpoint")
    r2_access_key: Optional[str] = Field(default=None, description="R2 Access Key")
    r2_secret_key: Optional[str] = Field(default=None, description="R2 Secret Key")
    
    # Cloudflare CDN Configuration
    cloudflare_api_token: Optional[str] = Field(default=None, description="Cloudflare API token for CDN management")
    cloudflare_zone_id: Optional[str] = Field(default=None, description="Cloudflare zone ID for CDN management")
    cdn_base_url: Optional[str] = Field(default=None, description="CDN base URL for content delivery")
    
    # Database Optimization
    database_pool_size: int = Field(default=20, description="Database connection pool size")
    database_max_overflow: int = Field(default=30, description="Database max overflow connections")
    database_pool_timeout: int = Field(default=30, description="Database pool timeout")
    database_pool_recycle: int = Field(default=3600, description="Database pool recycle time")
    
    # Performance & Scaling
    enable_query_cache: bool = Field(default=True, description="Enable database query caching")
    cache_default_ttl: int = Field(default=300, description="Default cache TTL in seconds")
    max_concurrent_requests: int = Field(default=1000, description="Max concurrent requests")
    
    # Real-time Features
    websocket_max_connections: int = Field(default=10000, description="Max WebSocket connections")
    websocket_heartbeat_interval: int = Field(default=30, description="WebSocket heartbeat interval")
    
    # Search Enhancement
    enable_elasticsearch: bool = Field(default=False, description="Enable Elasticsearch for advanced search")
    elasticsearch_url: Optional[str] = Field(default=None, description="Elasticsearch cluster URL")
    
    # Content Delivery
    enable_content_compression: bool = Field(default=True, description="Enable content compression")
    image_optimization_quality: int = Field(default=85, description="Image optimization quality (1-100)")
    max_image_size: int = Field(default=5 * 1024 * 1024, description="Max image size in bytes")
    
    # API Enhancement
    api_rate_limit_per_minute: int = Field(default=100, description="API rate limit per minute")
    api_burst_limit: int = Field(default=20, description="API burst limit")
    
    # Monitoring & Analytics
    enable_performance_monitoring: bool = Field(default=True, description="Enable performance monitoring")
    enable_user_analytics: bool = Field(default=True, description="Enable user analytics")
    analytics_batch_size: int = Field(default=100, description="Analytics batch processing size")
    
    # Security Enhancement
    enable_advanced_security: bool = Field(default=True, description="Enable advanced security features")
    password_min_length: int = Field(default=12, description="Minimum password length")
    session_timeout_minutes: int = Field(default=60, description="Session timeout in minutes")
    max_login_attempts: int = Field(default=5, description="Max login attempts before lockout")
    
    # Content Moderation
    enable_content_moderation: bool = Field(default=True, description="Enable AI content moderation")
    moderation_confidence_threshold: float = Field(default=0.8, description="Content moderation confidence threshold")
    
    # Backup & Recovery
    enable_automated_backups: bool = Field(default=True, description="Enable automated database backups")
    backup_retention_days: int = Field(default=30, description="Backup retention period in days")
    
    # Mobile App Integration
    ios_app_store_url: Optional[str] = Field(default=None, description="iOS App Store URL")
    android_play_store_url: Optional[str] = Field(default=None, description="Android Play Store URL")
    deep_link_scheme: str = Field(default="lyoapp", description="Deep link URL scheme")
    
    # Push Notifications
    apns_key_id: Optional[str] = Field(default=None, description="Apple Push Notification service Key ID")
    apns_team_id: Optional[str] = Field(default=None, description="Apple Developer Team ID")
    apns_bundle_id: Optional[str] = Field(default=None, description="iOS App Bundle ID")
    fcm_server_key: Optional[str] = Field(default=None, description="Firebase Cloud Messaging Server Key")
    
    # Additional settings for enhanced features
    APP_NAME: str = Field(default="LyoApp Backend", description="Application name (legacy)")
    APP_VERSION: str = Field(default="1.0.0", description="Application version (legacy)")
    CLOUDFLARE_ZONE_ID: Optional[str] = Field(default=None, description="Cloudflare zone ID for CDN management")
    
    @field_validator('youtube_api_key', 'gemini_api_key', 'podchaser_api_key')
    @classmethod
    def validate_api_keys(cls, v, info):
        """Validate API key format and length."""
        if v is None:
            return v
        
        # Minimum length check
        if len(v) < 10:
            raise ValueError(f"{info.field_name} seems too short (minimum 10 characters)")
        
        # Check for obvious placeholder values
        placeholder_patterns = [
            'your-api-key', 'your_api_key', 'replace-me', 
            'change-me', 'placeholder', 'test-key'
        ]
        if any(pattern in v.lower() for pattern in placeholder_patterns):
            raise ValueError(f"{info.field_name} appears to be a placeholder value")
        
        return v
    
    @field_validator('secret_key')
    @classmethod
    def validate_secret_key(cls, v):
        """Validate secret key strength."""
        if len(v) < 32:
            raise ValueError("Secret key must be at least 32 characters")
        
        # Check for weak patterns
        if v in ['your-secret-key', 'change-me', 'secret']:
            raise ValueError("Secret key is too weak - use a secure random value")
        
        return v
    
    @field_validator('cors_origins')
    @classmethod
    def validate_cors_origins(cls, v):
        """Validate CORS origins format."""
        for origin in v:
            if not origin.startswith(('http://', 'https://')):
                raise ValueError(f"CORS origin '{origin}' must start with http:// or https://")
        return v
    
    @field_validator('smtp_from_email')
    @classmethod
    def validate_email_format(cls, v):
        """Validate email format."""
        if v and '@' not in v:
            raise ValueError("Invalid email format")
        return v
    
    @model_validator(mode='after')
    def validate_environment_specific(self):
        """Validate environment-specific configurations."""
        # For model_validator in 'after' mode, self is the model instance
        environment = self.environment
        
        # Production-specific validations
        if environment == 'production':
            # Require secure secret key in production
            secret_key = self.secret_key
            if len(secret_key) < 64:
                raise ValueError("Production secret key must be at least 64 characters")
            
            # Require database URL in production
            database_url = self.database_url
            if 'sqlite' in database_url.lower():
                raise ValueError("SQLite is not recommended for production - use PostgreSQL")
            
            # Require HTTPS CORS origins in production
        
        return self
    
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

# Convenience helpers for secret-managed credentials (lazy import to avoid cycle)
def get_credential(name: str, current: Optional[str]) -> Optional[str]:
    """Return existing setting or secret manager fallback.

    Args:
        name: Environment/secret name
        current: Value already loaded into settings
    """
    if current:
        return current
    try:  # local import avoids dependency if not on GCP
        from lyo_app.integrations.gcp_secrets import get_secret  # type: ignore
        return get_secret(name)
    except Exception:  # pragma: no cover
        import os
        return os.getenv(name)

