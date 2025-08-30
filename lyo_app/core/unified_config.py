"""
Unified Configuration Management Module
--------------------------------------
Provides a centralized configuration system that:
1. Consolidates settings from multiple sources (environment, files, etc.)
2. Enforces environment-specific validation (dev vs prod)
3. Provides clear documentation and type safety
4. Gracefully handles configuration errors
5. Supports hot reloading for development
"""

import os
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Literal
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Configure logging
logger = logging.getLogger(__name__)


class Environment(str, Enum):
    """Application environment types with specific behavior expectations."""
    
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class DatabaseProvider(str, Enum):
    """Supported database providers."""
    
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"  # Development only


class StorageProvider(str, Enum):
    """Supported storage providers."""
    
    LOCAL = "local"
    AWS_S3 = "aws_s3"
    CLOUDFLARE_R2 = "cloudflare_r2"
    GCP_STORAGE = "gcp_storage"


class AIProvider(str, Enum):
    """Supported AI model providers."""
    
    GOOGLE = "google"  # Gemini models
    OPENAI = "openai"  # OpenAI models (backup)
    ANTHROPIC = "anthropic"  # Claude models (backup)
    LOCAL = "local"  # Local models (development only)


class UnifiedSettings(BaseSettings):
    """
    Comprehensive application settings with smart defaults and validation.
    
    Combines and standardizes settings from legacy modules:
    - config.py
    - settings.py
    - enhanced_config.py
    
    Features:
    - Environment-specific behavior
    - Type safety with Pydantic
    - Comprehensive validation
    - Clear documentation
    """
    
    # ==========================================================================
    # CORE APPLICATION SETTINGS
    # ==========================================================================
    
    APP_NAME: str = Field(
        default="LyoApp Backend",
        description="Application name displayed in API docs and headers"
    )
    APP_VERSION: str = Field(
        default="2.0.0", 
        description="Semantic version number (major.minor.patch)"
    )
    APP_DESCRIPTION: str = Field(
        default="LyoApp AI-Powered Learning Platform",
        description="Application description for documentation"
    )
    
    # Environment Configuration
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment (development, staging, production)"
    )
    DEBUG: bool = Field(
        default=False, 
        env="DEBUG",
        description="Enable debug mode (verbose logging, etc.)"
    )
    
    # Server Configuration
    HOST: str = Field(
        default="0.0.0.0", 
        env="HOST",
        description="Server host address"
    )
    PORT: int = Field(
        default=8000, 
        env="PORT",
        description="Server port"
    )
    WORKERS: int = Field(
        default=1, 
        env="WORKERS",
        description="Number of worker processes"
    )
    API_V1_PREFIX: str = Field(
        default="/api/v1",
        description="API version prefix"
    )
    
    # ==========================================================================
    # DATABASE SETTINGS
    # ==========================================================================
    
    # Primary database configuration (PostgreSQL recommended for all environments)
    DATABASE_URL: str = Field(
        ..., 
        env="DATABASE_URL",
        description="Database connection URL (PostgreSQL required for production)"
    )
    DATABASE_ECHO: bool = Field(
        default=False, 
        env="DATABASE_ECHO",
        description="Echo SQL queries (development only)"
    )
    DATABASE_PROVIDER: DatabaseProvider = Field(
        default=DatabaseProvider.POSTGRESQL,
        description="Database provider type"
    )
    
    # Connection pool settings
    DATABASE_POOL_SIZE: int = Field(
        default=20,
        env="DATABASE_POOL_SIZE", 
        description="Database connection pool size"
    )
    DATABASE_MAX_OVERFLOW: int = Field(
        default=30, 
        env="DATABASE_MAX_OVERFLOW",
        description="Database max overflow connections"
    )
    DATABASE_POOL_TIMEOUT: int = Field(
        default=30, 
        env="DATABASE_POOL_TIMEOUT",
        description="Database pool timeout (seconds)"
    )
    DATABASE_POOL_RECYCLE: int = Field(
        default=3600, 
        env="DATABASE_POOL_RECYCLE",
        description="Database pool recycle time (seconds)"
    )
    
    # SQLite configuration (development only)
    SQLITE_DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./lyo_app_dev.db",
        env="SQLITE_DATABASE_URL", 
        description="SQLite database URL (development only)"
    )
    
    # ==========================================================================
    # CACHING & REDIS SETTINGS
    # ==========================================================================
    
    # Redis configuration (used for caching, Celery, and WebSockets)
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", 
        env="REDIS_URL",
        description="Redis connection URL"
    )
    REDIS_MAX_CONNECTIONS: int = Field(
        default=20, 
        env="REDIS_MAX_CONNECTIONS",
        description="Redis max connections"
    )
    
    # Caching configuration
    CACHE_ENABLED: bool = Field(
        default=True, 
        env="CACHE_ENABLED",
        description="Enable caching"
    )
    CACHE_DEFAULT_TTL: int = Field(
        default=300, 
        env="CACHE_DEFAULT_TTL",
        description="Default cache TTL (seconds)"
    )
    CACHE_USER_DATA_TTL: int = Field(
        default=1800, 
        env="CACHE_USER_DATA_TTL",
        description="User data cache TTL (seconds)"
    )
    CACHE_STATIC_CONTENT_TTL: int = Field(
        default=86400, 
        env="CACHE_STATIC_CONTENT_TTL",
        description="Static content cache TTL (seconds)"
    )
    
    # ==========================================================================
    # CELERY SETTINGS (BACKGROUND TASKS)
    # ==========================================================================
    
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1", 
        env="CELERY_BROKER_URL",
        description="Celery broker URL"
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/2", 
        env="CELERY_RESULT_BACKEND",
        description="Celery result backend URL"
    )
    CELERY_TASK_TIMEOUT: int = Field(
        default=1200, 
        env="CELERY_TASK_TIMEOUT",
        description="Celery task timeout (seconds)"
    )
    
    # ==========================================================================
    # SECURITY SETTINGS
    # ==========================================================================
    
    # General security
    SECRET_KEY: str = Field(
        ..., 
        env="SECRET_KEY",
        description="Secret key for signing tokens and cookies"
    )
    PASSWORD_MIN_LENGTH: int = Field(
        default=12, 
        env="PASSWORD_MIN_LENGTH",
        description="Minimum password length"
    )
    SESSION_TIMEOUT_MINUTES: int = Field(
        default=60, 
        env="SESSION_TIMEOUT_MINUTES",
        description="Session timeout (minutes)"
    )
    MAX_LOGIN_ATTEMPTS: int = Field(
        default=5, 
        env="MAX_LOGIN_ATTEMPTS",
        description="Max login attempts before lockout"
    )
    ENABLE_RATE_LIMITING: bool = Field(
        default=True, 
        env="ENABLE_RATE_LIMITING",
        description="Enable rate limiting"
    )
    ENABLE_ADVANCED_SECURITY: bool = Field(
        default=True, 
        env="ENABLE_ADVANCED_SECURITY",
        description="Enable advanced security features"
    )
    
    # JWT Configuration
    JWT_SECRET_KEY: str = Field(
        ..., 
        env="JWT_SECRET_KEY",
        description="JWT secret key"
    )
    JWT_ALGORITHM: str = Field(
        default="HS256", 
        env="JWT_ALGORITHM",
        description="JWT algorithm"
    )
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60, 
        env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
        description="JWT access token expiration (minutes)"
    )
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=30, 
        env="JWT_REFRESH_TOKEN_EXPIRE_DAYS",
        description="JWT refresh token expiration (days)"
    )
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000", 
            "http://localhost:8080",
            "http://127.0.0.1:3000"
        ],
        env="CORS_ORIGINS",
        description="CORS allowed origins"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True, 
        env="CORS_ALLOW_CREDENTIALS",
        description="CORS allow credentials"
    )
    CORS_ALLOW_METHODS: List[str] = Field(
        default=["*"], 
        env="CORS_ALLOW_METHODS",
        description="CORS allowed methods"
    )
    CORS_ALLOW_HEADERS: List[str] = Field(
        default=["*"], 
        env="CORS_ALLOW_HEADERS",
        description="CORS allowed headers"
    )
    
    # ==========================================================================
    # AI MODEL CONFIGURATION
    # ==========================================================================
    
    # AI Provider configuration
    AI_PROVIDER: AIProvider = Field(
        default=AIProvider.GOOGLE, 
        env="AI_PROVIDER",
        description="Primary AI provider"
    )
    
    # Google Gemini settings
    GOOGLE_API_KEY: str = Field(
        default="", 
        env="GOOGLE_API_KEY",
        description="Google API key for Gemini models"
    )
    GEMINI_MODEL_DEFAULT: str = Field(
        default="gemini-pro", 
        env="GEMINI_MODEL_DEFAULT",
        description="Default Gemini model"
    )
    GEMINI_MODEL_VISION: str = Field(
        default="gemini-pro-vision", 
        env="GEMINI_MODEL_VISION",
        description="Gemini vision model"
    )
    GEMINI_MAX_TOKENS: int = Field(
        default=8192, 
        env="GEMINI_MAX_TOKENS",
        description="Gemini max tokens"
    )
    GEMINI_TEMPERATURE: float = Field(
        default=0.7, 
        env="GEMINI_TEMPERATURE",
        description="Gemini temperature"
    )
    GEMINI_TOP_P: float = Field(
        default=0.8, 
        env="GEMINI_TOP_P",
        description="Gemini top_p"
    )
    GEMINI_TOP_K: int = Field(
        default=40, 
        env="GEMINI_TOP_K",
        description="Gemini top_k"
    )
    
    # OpenAI settings (backup)
    OPENAI_API_KEY: Optional[str] = Field(
        default=None, 
        env="OPENAI_API_KEY",
        description="OpenAI API key (backup)"
    )
    OPENAI_MODEL_DEFAULT: str = Field(
        default="gpt-4", 
        env="OPENAI_MODEL_DEFAULT",
        description="Default OpenAI model"
    )
    OPENAI_MAX_TOKENS: int = Field(
        default=4096, 
        env="OPENAI_MAX_TOKENS",
        description="OpenAI max tokens"
    )
    
    # Anthropic settings (backup)
    ANTHROPIC_API_KEY: Optional[str] = Field(
        default=None, 
        env="ANTHROPIC_API_KEY",
        description="Anthropic API key (backup)"
    )
    ANTHROPIC_MODEL_DEFAULT: str = Field(
        default="claude-3-sonnet-20240229", 
        env="ANTHROPIC_MODEL_DEFAULT",
        description="Default Anthropic model"
    )
    
    # Local model settings
    MODEL_DIR: str = Field(
        default="/tmp/models/ai_model", 
        env="MODEL_DIR",
        description="Local model directory"
    )
    MODEL_ID: str = Field(
        default="gpt2", 
        env="MODEL_ID",
        description="Model ID for local/HF models"
    )
    HF_HOME: str = Field(
        default="/tmp/models/cache", 
        env="HF_HOME",
        description="Hugging Face cache directory"
    )
    
    # AI circuit breaker
    AI_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=5, 
        env="AI_CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        description="AI circuit breaker failure threshold"
    )
    AI_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=60, 
        env="AI_CIRCUIT_BREAKER_RECOVERY_TIMEOUT",
        description="AI circuit breaker recovery timeout (seconds)"
    )
    AI_DAILY_COST_LIMIT: float = Field(
        default=50.0, 
        env="AI_DAILY_COST_LIMIT",
        description="Daily AI cost limit (USD)"
    )
    
    # ==========================================================================
    # STORAGE SETTINGS
    # ==========================================================================
    
    # Storage provider configuration
    STORAGE_PROVIDER: StorageProvider = Field(
        default=StorageProvider.LOCAL, 
        env="STORAGE_PROVIDER",
        description="Primary storage provider"
    )
    
    # Local storage
    UPLOAD_DIR: str = Field(
        default="uploads", 
        env="UPLOAD_DIR",
        description="Local upload directory"
    )
    MAX_UPLOAD_SIZE: int = Field(
        default=100 * 1024 * 1024, 
        env="MAX_UPLOAD_SIZE",
        description="Max upload size (bytes)"
    )
    ALLOWED_FILE_TYPES: List[str] = Field(
        default=[
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif",
            ".mp4", ".mov", ".avi", ".mkv", ".webm",
            ".mp3", ".wav", ".aac", ".ogg",
            ".pdf", ".doc", ".docx", ".txt", ".md"
        ],
        description="Allowed file extensions"
    )
    
    # AWS S3
    AWS_ACCESS_KEY_ID: Optional[str] = Field(
        default=None, 
        env="AWS_ACCESS_KEY_ID",
        description="AWS access key ID"
    )
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(
        default=None, 
        env="AWS_SECRET_ACCESS_KEY",
        description="AWS secret access key"
    )
    AWS_REGION: str = Field(
        default="us-east-1", 
        env="AWS_REGION",
        description="AWS region"
    )
    AWS_S3_BUCKET: Optional[str] = Field(
        default=None, 
        env="AWS_S3_BUCKET",
        description="AWS S3 bucket name"
    )
    
    # Cloudflare R2
    R2_ACCESS_KEY_ID: Optional[str] = Field(
        default=None, 
        env="R2_ACCESS_KEY_ID",
        description="Cloudflare R2 access key ID"
    )
    R2_SECRET_ACCESS_KEY: Optional[str] = Field(
        default=None, 
        env="R2_SECRET_ACCESS_KEY",
        description="Cloudflare R2 secret access key"
    )
    R2_ENDPOINT_URL: Optional[str] = Field(
        default=None, 
        env="R2_ENDPOINT_URL",
        description="Cloudflare R2 endpoint URL"
    )
    R2_BUCKET: Optional[str] = Field(
        default=None, 
        env="R2_BUCKET",
        description="Cloudflare R2 bucket name"
    )
    
    # CDN configuration
    CDN_BASE_URL: Optional[str] = Field(
        default=None, 
        env="CDN_BASE_URL",
        description="CDN base URL"
    )
    CLOUDFLARE_ZONE_ID: Optional[str] = Field(
        default=None, 
        env="CLOUDFLARE_ZONE_ID",
        description="Cloudflare zone ID"
    )
    CLOUDFLARE_API_TOKEN: Optional[str] = Field(
        default=None, 
        env="CLOUDFLARE_API_TOKEN",
        description="Cloudflare API token"
    )
    
    # ==========================================================================
    # MONITORING & LOGGING
    # ==========================================================================
    
    # Logging
    LOG_LEVEL: str = Field(
        default="INFO", 
        env="LOG_LEVEL",
        description="Logging level"
    )
    LOG_FORMAT: str = Field(
        default="json", 
        env="LOG_FORMAT",
        description="Logging format (json, text)"
    )
    LOG_FILE: Optional[str] = Field(
        default=None, 
        env="LOG_FILE",
        description="Log file path"
    )
    
    # Monitoring
    ENABLE_METRICS: bool = Field(
        default=True, 
        env="ENABLE_METRICS",
        description="Enable metrics collection"
    )
    METRICS_PORT: int = Field(
        default=9090, 
        env="METRICS_PORT",
        description="Metrics server port"
    )
    ENABLE_TRACING: bool = Field(
        default=False, 
        env="ENABLE_TRACING",
        description="Enable distributed tracing"
    )
    
    # Error tracking
    SENTRY_DSN: Optional[str] = Field(
        default=None, 
        env="SENTRY_DSN",
        description="Sentry DSN for error tracking"
    )
    
    # ==========================================================================
    # FEATURE FLAGS
    # ==========================================================================
    
    # AI features
    ENABLE_AI_STUDY_MODE: bool = Field(
        default=True, 
        env="ENABLE_AI_STUDY_MODE",
        description="Enable AI Study Mode"
    )
    ENABLE_AI_QUIZ_GENERATION: bool = Field(
        default=True, 
        env="ENABLE_AI_QUIZ_GENERATION",
        description="Enable AI Quiz Generation"
    )
    ENABLE_AI_CONTENT_ANALYSIS: bool = Field(
        default=True, 
        env="ENABLE_AI_CONTENT_ANALYSIS",
        description="Enable AI Content Analysis"
    )
    ENABLE_AI_PERSONALIZATION: bool = Field(
        default=True, 
        env="ENABLE_AI_PERSONALIZATION",
        description="Enable AI Personalization"
    )
    
    # Feed features
    ENABLE_ADDICTIVE_FEED: bool = Field(
        default=True, 
        env="ENABLE_ADDICTIVE_FEED",
        description="Enable addictive feed algorithm"
    )
    ENABLE_FEED_ANALYTICS: bool = Field(
        default=True, 
        env="ENABLE_FEED_ANALYTICS",
        description="Enable feed analytics"
    )
    ENABLE_CONTENT_RECOMMENDATION: bool = Field(
        default=True, 
        env="ENABLE_CONTENT_RECOMMENDATION",
        description="Enable content recommendations"
    )
    
    # Storage features
    ENABLE_IMAGE_OPTIMIZATION: bool = Field(
        default=True, 
        env="ENABLE_IMAGE_OPTIMIZATION",
        description="Enable image optimization"
    )
    ENABLE_VIDEO_PROCESSING: bool = Field(
        default=True, 
        env="ENABLE_VIDEO_PROCESSING",
        description="Enable video processing"
    )
    ENABLE_CDN_INTEGRATION: bool = Field(
        default=True, 
        env="ENABLE_CDN_INTEGRATION",
        description="Enable CDN integration"
    )
    
    # Social features
    ENABLE_SOCIAL_FEATURES: bool = Field(
        default=True, 
        env="ENABLE_SOCIAL_FEATURES",
        description="Enable social features"
    )
    ENABLE_GAMIFICATION: bool = Field(
        default=True, 
        env="ENABLE_GAMIFICATION",
        description="Enable gamification"
    )
    ENABLE_COMMUNITY: bool = Field(
        default=True, 
        env="ENABLE_COMMUNITY",
        description="Enable community features"
    )
    
    # ==========================================================================
    # API CONFIGURATION
    # ==========================================================================
    
    # Rate limiting
    RATE_LIMIT_ENABLED: bool = Field(
        default=True, 
        env="RATE_LIMIT_ENABLED",
        description="Enable rate limiting"
    )
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=60, 
        env="RATE_LIMIT_PER_MINUTE",
        description="Rate limit per minute"
    )
    API_RATE_LIMIT_PER_MINUTE: int = Field(
        default=100, 
        env="API_RATE_LIMIT_PER_MINUTE",
        description="API rate limit per minute"
    )
    API_BURST_LIMIT: int = Field(
        default=20, 
        env="API_BURST_LIMIT",
        description="API burst limit"
    )
    MAX_CONCURRENT_REQUESTS: int = Field(
        default=1000, 
        env="MAX_CONCURRENT_REQUESTS",
        description="Max concurrent requests"
    )
    MAX_REQUEST_SIZE: int = Field(
        default=512 * 1024, 
        env="MAX_REQUEST_SIZE",
        description="Max request size in bytes"
    )
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = Field(
        default=20, 
        env="DEFAULT_PAGE_SIZE",
        description="Default pagination page size"
    )
    MAX_PAGE_SIZE: int = Field(
        default=50, 
        env="MAX_PAGE_SIZE",
        description="Maximum pagination page size"
    )
    
    # WebSocket configuration
    WS_MAX_CONNECTIONS: int = Field(
        default=1000, 
        env="WS_MAX_CONNECTIONS",
        description="WebSocket max connections"
    )
    WS_HEARTBEAT_INTERVAL: int = Field(
        default=30, 
        env="WS_HEARTBEAT_INTERVAL",
        description="WebSocket heartbeat interval"
    )
    WS_MESSAGE_QUEUE_SIZE: int = Field(
        default=100, 
        env="WS_MESSAGE_QUEUE_SIZE",
        description="WebSocket message queue size"
    )
    
    # ==========================================================================
    # EMAIL & NOTIFICATIONS
    # ==========================================================================
    
    # Email settings
    SMTP_HOST: Optional[str] = Field(
        default=None, 
        env="SMTP_HOST",
        description="SMTP host"
    )
    SMTP_PORT: int = Field(
        default=587, 
        env="SMTP_PORT",
        description="SMTP port"
    )
    SMTP_USERNAME: Optional[str] = Field(
        default=None, 
        env="SMTP_USERNAME",
        description="SMTP username"
    )
    SMTP_PASSWORD: Optional[str] = Field(
        default=None, 
        env="SMTP_PASSWORD",
        description="SMTP password"
    )
    SMTP_TLS: bool = Field(
        default=True, 
        env="SMTP_TLS",
        description="SMTP TLS enabled"
    )
    EMAIL_FROM: Optional[str] = Field(
        default=None, 
        env="EMAIL_FROM",
        description="Email from address"
    )
    
    # Push notifications
    APNS_KEY_ID: Optional[str] = Field(
        default=None, 
        env="APNS_KEY_ID",
        description="Apple Push Notification service key ID"
    )
    APNS_TEAM_ID: Optional[str] = Field(
        default=None, 
        env="APNS_TEAM_ID",
        description="Apple Push Notification service team ID"
    )
    APNS_BUNDLE_ID: Optional[str] = Field(
        default=None, 
        env="APNS_BUNDLE_ID",
        description="Apple Push Notification service bundle ID"
    )
    APNS_SANDBOX: bool = Field(
        default=True, 
        env="APNS_SANDBOX",
        description="Use APNs sandbox environment"
    )
    FCM_SERVER_KEY: Optional[str] = Field(
        default=None, 
        env="FCM_SERVER_KEY",
        description="Firebase Cloud Messaging server key"
    )

    # ==========================================================================
    # PYDANTIC CONFIG
    # ==========================================================================
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra='ignore'
    )

    # ==========================================================================
    # VALIDATORS
    # ==========================================================================
    
    @field_validator("CORS_ORIGINS", mode='before')
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @field_validator("MODEL_DIR")
    def validate_model_dir(cls, v):
        """Ensure model directory is absolute path."""
        return os.path.abspath(v)
    
    @field_validator("DATABASE_URL")
    def validate_database_url(cls, v):
        """Validate database URL format.
        
        Enforces PostgreSQL for production environments to ensure
        proper scalability, reliability, and data integrity.
        """
        # Extract environment to determine if we're in production/staging
        environment = os.getenv("ENVIRONMENT", "development").lower()
        
        # For production and staging, enforce PostgreSQL
        if environment in ["production", "staging"]:
            if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
                raise ValueError(f"DATABASE_URL in {environment} environment must be a PostgreSQL URL")
        
        # For all environments, validate the URL format
        if v.startswith(("postgresql://", "postgresql+asyncpg://")):
            # Validate PostgreSQL URL format
            if not (("/" in v and "@" in v) or v.endswith("?host=/cloudsql/")):
                raise ValueError("Invalid PostgreSQL URL format")
        elif v.startswith(("sqlite://", "sqlite+aiosqlite://")):
            # Allow SQLite only for development and testing
            if environment not in ["development", "testing"]:
                raise ValueError(f"SQLite is not supported in {environment} environment")
        else:
            raise ValueError("DATABASE_URL must be either PostgreSQL or SQLite (development only)")
            
        return v
    
    @field_validator("SECRET_KEY")
    def validate_secret_key(cls, v):
        """Validate secret key strength."""
        if len(v) < 32:
            raise ValueError("Secret key must be at least 32 characters")
        
        # Check for weak patterns
        if v in ['your-secret-key', 'change-me', 'secret']:
            raise ValueError("Secret key is too weak - use a secure random value")
        
        return v
    
    @field_validator("GEMINI_TEMPERATURE")
    def validate_temperature(cls, v):
        """Validate temperature parameter."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v
    
    @field_validator("GEMINI_TOP_P")
    def validate_top_p(cls, v):
        """Validate top_p parameter."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Top_p must be between 0.0 and 1.0")
        return v
    
    @field_validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Validate log level."""
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of: {allowed_levels}")
        return v.upper()
    
    @field_validator("EMAIL_FROM")
    def validate_email_format(cls, v):
        """Validate email format."""
        if v and '@' not in v:
            raise ValueError("Invalid email format")
        return v
    
    @model_validator(mode='after')
    def validate_environment_specific(self):
        """Validate environment-specific configurations."""
        environment = str(self.ENVIRONMENT).lower()
        
        # Production-specific validations
        if environment == 'production':
            # Require secure secret key in production
            if len(self.SECRET_KEY) < 64:
                logger.warning("Production secret key should be at least 64 characters")
            
            # Require PostgreSQL in production
            if 'sqlite' in self.DATABASE_URL.lower():
                raise ValueError("SQLite is not supported in production environment")
            
            # Require HTTPS CORS origins in production
            non_https_origins = [
                origin for origin in self.CORS_ORIGINS 
                if origin != '*' and not origin.startswith('https://')
            ]
            if non_https_origins:
                logger.warning(f"Non-HTTPS CORS origins in production: {non_https_origins}")
            
            # Debug mode should be disabled in production
            if self.DEBUG:
                logger.warning("Debug mode should be disabled in production")
        
        return self
    
    # ==========================================================================
    # HELPER METHODS
    # ==========================================================================
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return str(self.ENVIRONMENT).lower() == 'production'
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return str(self.ENVIRONMENT).lower() == 'development'
    
    def is_staging(self) -> bool:
        """Check if running in staging environment."""
        return str(self.ENVIRONMENT).lower() == 'staging'
    
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return str(self.ENVIRONMENT).lower() == 'testing'
    
    def get_database_url(self) -> str:
        """Get the appropriate database URL based on environment."""
        # Always use PostgreSQL for production and staging
        if self.is_production() or self.is_staging():
            # Validate the DATABASE_URL for production/staging
            if not self.DATABASE_URL or 'sqlite' in self.DATABASE_URL.lower():
                raise ValueError(f"Invalid DATABASE_URL for {self.ENVIRONMENT} environment. PostgreSQL is required.")
            return self.DATABASE_URL
        else:
            # For development, use PostgreSQL if configured, else SQLite
            if self.DATABASE_URL and 'postgresql' in self.DATABASE_URL.lower():
                return self.DATABASE_URL
            else:
                # Fall back to SQLite only in development
                return self.SQLITE_DATABASE_URL
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration dictionary."""
        return {
            'url': self.get_database_url(),
            'echo': self.DATABASE_ECHO,
            'pool_size': self.DATABASE_POOL_SIZE,
            'max_overflow': self.DATABASE_MAX_OVERFLOW,
            'pool_timeout': self.DATABASE_POOL_TIMEOUT,
            'pool_recycle': self.DATABASE_POOL_RECYCLE
        }
    
    def get_cors_config(self) -> Dict[str, Any]:
        """Get CORS configuration dictionary."""
        return {
            'allow_origins': self.CORS_ORIGINS,
            'allow_credentials': self.CORS_ALLOW_CREDENTIALS,
            'allow_methods': self.CORS_ALLOW_METHODS,
            'allow_headers': self.CORS_ALLOW_HEADERS
        }
    
    def get_ai_config(self) -> Dict[str, Any]:
        """Get AI configuration dictionary."""
        return {
            'google': {
                'api_key': self.GOOGLE_API_KEY,
                'models': {
                    'default': self.GEMINI_MODEL_DEFAULT,
                    'vision': self.GEMINI_MODEL_VISION
                },
                'generation_config': {
                    'max_output_tokens': self.GEMINI_MAX_TOKENS,
                    'temperature': self.GEMINI_TEMPERATURE,
                    'top_p': self.GEMINI_TOP_P,
                    'top_k': self.GEMINI_TOP_K
                }
            },
            'openai': {
                'api_key': self.OPENAI_API_KEY,
                'model': self.OPENAI_MODEL_DEFAULT,
                'max_tokens': self.OPENAI_MAX_TOKENS
            },
            'anthropic': {
                'api_key': self.ANTHROPIC_API_KEY,
                'model': self.ANTHROPIC_MODEL_DEFAULT
            },
            'circuit_breaker': {
                'failure_threshold': self.AI_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                'recovery_timeout': self.AI_CIRCUIT_BREAKER_RECOVERY_TIMEOUT
            }
        }
    
    def get_storage_config(self) -> Dict[str, Any]:
        """Get storage configuration dictionary."""
        return {
            'provider': self.STORAGE_PROVIDER,
            'local': {
                'upload_dir': self.UPLOAD_DIR,
                'max_upload_size': self.MAX_UPLOAD_SIZE,
                'allowed_file_types': self.ALLOWED_FILE_TYPES
            },
            'aws_s3': {
                'access_key_id': self.AWS_ACCESS_KEY_ID,
                'secret_access_key': self.AWS_SECRET_ACCESS_KEY,
                'region': self.AWS_REGION,
                'bucket': self.AWS_S3_BUCKET
            },
            'cloudflare_r2': {
                'access_key_id': self.R2_ACCESS_KEY_ID,
                'secret_access_key': self.R2_SECRET_ACCESS_KEY,
                'endpoint_url': self.R2_ENDPOINT_URL,
                'bucket': self.R2_BUCKET
            },
            'cdn': {
                'base_url': self.CDN_BASE_URL,
                'cloudflare_zone_id': self.CLOUDFLARE_ZONE_ID,
                'cloudflare_api_token': self.CLOUDFLARE_API_TOKEN
            }
        }
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring configuration dictionary."""
        return {
            'logging': {
                'level': self.LOG_LEVEL,
                'format': self.LOG_FORMAT,
                'file': self.LOG_FILE
            },
            'metrics': {
                'enabled': self.ENABLE_METRICS,
                'port': self.METRICS_PORT
            },
            'tracing': {
                'enabled': self.ENABLE_TRACING
            },
            'sentry': {
                'dsn': self.SENTRY_DSN,
                'environment': self.ENVIRONMENT,
                'release': self.APP_VERSION
            }
        }
    
    def get_feature_flags(self) -> Dict[str, bool]:
        """Get all feature flags as a dictionary."""
        return {
            'ai_study_mode': self.ENABLE_AI_STUDY_MODE,
            'ai_quiz_generation': self.ENABLE_AI_QUIZ_GENERATION,
            'ai_content_analysis': self.ENABLE_AI_CONTENT_ANALYSIS,
            'ai_personalization': self.ENABLE_AI_PERSONALIZATION,
            'addictive_feed': self.ENABLE_ADDICTIVE_FEED,
            'feed_analytics': self.ENABLE_FEED_ANALYTICS,
            'content_recommendation': self.ENABLE_CONTENT_RECOMMENDATION,
            'image_optimization': self.ENABLE_IMAGE_OPTIMIZATION,
            'video_processing': self.ENABLE_VIDEO_PROCESSING,
            'cdn_integration': self.ENABLE_CDN_INTEGRATION,
            'social_features': self.ENABLE_SOCIAL_FEATURES,
            'gamification': self.ENABLE_GAMIFICATION,
            'community': self.ENABLE_COMMUNITY
        }
    
    def get_email_config(self) -> Dict[str, Any]:
        """Get email configuration dictionary."""
        return {
            'smtp_host': self.SMTP_HOST,
            'smtp_port': self.SMTP_PORT,
            'smtp_username': self.SMTP_USERNAME,
            'smtp_password': self.SMTP_PASSWORD,
            'smtp_tls': self.SMTP_TLS,
            'email_from': self.EMAIL_FROM
        }
    
    def get_push_notification_config(self) -> Dict[str, Any]:
        """Get push notification configuration dictionary."""
        return {
            'apns': {
                'key_id': self.APNS_KEY_ID,
                'team_id': self.APNS_TEAM_ID,
                'bundle_id': self.APNS_BUNDLE_ID,
                'sandbox': self.APNS_SANDBOX
            },
            'fcm': {
                'server_key': self.FCM_SERVER_KEY
            }
        }


@lru_cache()
def get_settings() -> UnifiedSettings:
    """Get cached settings instance."""
    return UnifiedSettings()


# Global settings instance
unified_settings = get_settings()

# Apply environment-specific overrides
def apply_environment_overrides():
    """Apply environment-specific configuration overrides."""
    env = unified_settings.ENVIRONMENT
    
    # Production overrides
    if str(env).lower() == 'production':
        # These will override the values already loaded from .env
        # but are here as a safety net
        unified_settings.DEBUG = False
        unified_settings.LOG_LEVEL = "WARNING"
        unified_settings.DATABASE_ECHO = False
    
    # Staging overrides
    elif str(env).lower() == 'staging':
        unified_settings.DEBUG = False
        unified_settings.LOG_LEVEL = "INFO"
    
    # No overrides needed for development (uses defaults)
    # Development overrides would go here if needed


# Apply overrides
apply_environment_overrides()

# Export for use throughout the application
settings = unified_settings
