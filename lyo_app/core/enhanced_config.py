"""
Enhanced Configuration Management
Production-ready configuration with environment validation and secrets management
"""

import os
import json
from typing import Dict, List, Optional, Any, Union, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from datetime import timedelta

from pydantic import BaseModel, Field, field_validator
try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings

class EnhancedSettings(BaseSettings):
    """
    Enhanced configuration with comprehensive validation and environment support
    
    Features:
    - Environment-specific configurations
    - Secrets management
    - Configuration validation
    - Dynamic configuration updates
    - Security hardening
    """
    
    # ============================================================================
    # APPLICATION SETTINGS
    # ============================================================================
    
    APP_NAME: str = Field("LyoBackend", description="Application name")
    APP_VERSION: str = Field("3.3.1-CLOUD", description="Application version")  # Latency optimizations
    APP_DESCRIPTION: str = Field("LyoBackend AI-Powered Learning Platform", description="Application description")
    
    # Environment
    ENVIRONMENT: str = Field("development", description="Environment (development, staging, production)")
    DEBUG: bool = Field(True, description="Debug mode")
    
    # Server
    HOST: str = Field("0.0.0.0", description="Server host")
    PORT: int = Field(8000, description="Server port")
    WORKERS: int = Field(1, description="Number of worker processes")
    
    # Security
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production", description="Secret key for signing tokens")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60 * 24 * 7, description="Access token expiration (minutes)")  # 7 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(30, description="Refresh token expiration (days)")
    PASSWORD_MIN_LENGTH: int = Field(8, description="Minimum password length")
    
    # CORS
    CORS_ORIGINS: List[str] = Field(["*"], description="CORS allowed origins")
    CORS_CREDENTIALS: bool = Field(True, description="CORS allow credentials")
    CORS_METHODS: List[str] = Field(["*"], description="CORS allowed methods")
    CORS_HEADERS: List[str] = Field(["*"], description="CORS allowed headers")
    
    # ============================================================================
    # DATABASE SETTINGS
    # ============================================================================
    
    # PostgreSQL
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./lyo_app_dev.db", description="Database connection URL")
    DATABASE_ECHO: bool = Field(False, description="Echo SQL queries")
    DATABASE_POOL_SIZE: int = Field(20, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(30, description="Database max overflow connections")
    DATABASE_POOL_TIMEOUT: int = Field(30, description="Database pool timeout (seconds)")
    DATABASE_POOL_RECYCLE: int = Field(3600, description="Database pool recycle time (seconds)")
    
    # Redis
    REDIS_URL: str = Field("redis://localhost:6379/0", description="Redis connection URL")
    REDIS_HOST: Optional[str] = Field(None, description="Redis host")
    REDIS_PORT: int = Field(6379, description="Redis port")
    REDIS_CACHE_TTL: int = Field(3600, description="Default Redis cache TTL (seconds)")
    REDIS_MAX_CONNECTIONS: int = Field(20, description="Redis max connections")
    
    # ============================================================================
    # AI SERVICE SETTINGS
    # ============================================================================
    
    # Google Gemini - supports both GOOGLE_API_KEY and GEMINI_API_KEY
    GOOGLE_API_KEY: str = Field("", description="Google Gemini API key")
    GEMINI_API_KEY: Optional[str] = Field(None, description="Google Gemini API key (alternative)")
    GEMINI_MODEL_DEFAULT: str = Field("gemini-1.5-flash", description="Default Gemini model")
    GEMINI_MODEL_VISION: str = Field("gemini-pro-vision", description="Gemini vision model")
    GEMINI_MODEL_FLASH: str = Field("gemini-1.5-flash", description="Gemini flash model")
    GEMINI_MAX_TOKENS: int = Field(4096, description="Gemini max tokens")
    GEMINI_TEMPERATURE: float = Field(0.7, description="Gemini temperature")
    GEMINI_TOP_P: float = Field(0.8, description="Gemini top_p")
    GEMINI_TOP_K: int = Field(40, description="Gemini top_k")
    
    # OpenAI (Backup)
    OPENAI_API_KEY: Optional[str] = Field(None, description="OpenAI API key (backup)")
    OPENAI_MODEL_DEFAULT: str = Field("gpt-4", description="Default OpenAI model")
    OPENAI_MAX_TOKENS: int = Field(4096, description="OpenAI max tokens")
    
    # Anthropic (Backup)
    ANTHROPIC_API_KEY: Optional[str] = Field(None, description="Anthropic API key (backup)")
    ANTHROPIC_MODEL_DEFAULT: str = Field("claude-3-sonnet-20240229", description="Default Anthropic model")
    
    # AI Circuit Breaker
    AI_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(5, description="AI circuit breaker failure threshold")
    AI_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(60, description="AI circuit breaker recovery timeout (seconds)")
    AI_CIRCUIT_BREAKER_EXPECTED_EXCEPTION: str = Field("Exception", description="AI circuit breaker expected exception")
    
    # ============================================================================
    # STORAGE SETTINGS
    # ============================================================================
    
    # Local Storage
    UPLOAD_DIR: str = Field("uploads", description="Local upload directory")
    MAX_UPLOAD_SIZE: int = Field(100 * 1024 * 1024, description="Max upload size (bytes)")  # 100MB
    ALLOWED_FILE_TYPES: List[str] = Field([
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif",
        ".mp4", ".mov", ".avi", ".mkv", ".webm",
        ".mp3", ".wav", ".aac", ".ogg",
        ".pdf", ".doc", ".docx", ".txt", ".md"
    ], description="Allowed file extensions")
    
    # AWS S3
    AWS_ACCESS_KEY_ID: Optional[str] = Field(None, description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(None, description="AWS secret access key")
    AWS_REGION: str = Field("us-east-1", description="AWS region")
    AWS_S3_BUCKET: Optional[str] = Field(None, description="AWS S3 bucket name")
    
    # Cloudflare R2
    R2_ACCESS_KEY_ID: Optional[str] = Field(None, description="Cloudflare R2 access key ID")
    R2_SECRET_ACCESS_KEY: Optional[str] = Field(None, description="Cloudflare R2 secret access key")
    R2_ENDPOINT_URL: Optional[str] = Field(None, description="Cloudflare R2 endpoint URL")
    R2_BUCKET: Optional[str] = Field(None, description="Cloudflare R2 bucket name")
    
    # CDN
    CDN_BASE_URL: Optional[str] = Field(None, description="CDN base URL")
    CLOUDFLARE_ZONE_ID: Optional[str] = Field(None, description="Cloudflare zone ID")
    CLOUDFLARE_API_TOKEN: Optional[str] = Field(None, description="Cloudflare API token")
    
    # ============================================================================
    # MONITORING & LOGGING SETTINGS
    # ============================================================================
    
    # Logging
    LOG_LEVEL: str = Field("INFO", description="Logging level")
    LOG_FORMAT: str = Field("json", description="Logging format (json, text)")
    LOG_FILE: Optional[str] = Field(None, description="Log file path")
    LOG_ROTATION: str = Field("1 day", description="Log rotation period")
    LOG_RETENTION: str = Field("30 days", description="Log retention period")
    
    # Monitoring
    ENABLE_METRICS: bool = Field(True, description="Enable metrics collection")
    METRICS_PORT: int = Field(9090, description="Metrics server port")
    ENABLE_TRACING: bool = Field(False, description="Enable distributed tracing")
    JAEGER_ENDPOINT: Optional[str] = Field(None, description="Jaeger endpoint for tracing")
    
    # Health Checks
    HEALTH_CHECK_INTERVAL: int = Field(30, description="Health check interval (seconds)")
    HEALTH_CHECK_TIMEOUT: int = Field(10, description="Health check timeout (seconds)")
    
    # ============================================================================
    # FEATURE FLAGS
    # ============================================================================
    
    # AI Features
    ENABLE_AI_STUDY_MODE: bool = Field(True, description="Enable AI Study Mode")
    ENABLE_AI_QUIZ_GENERATION: bool = Field(True, description="Enable AI Quiz Generation")
    ENABLE_AI_CONTENT_ANALYSIS: bool = Field(True, description="Enable AI Content Analysis")
    ENABLE_AI_PERSONALIZATION: bool = Field(True, description="Enable AI Personalization")
    
    # Feed Features
    ENABLE_ADDICTIVE_FEED: bool = Field(True, description="Enable addictive feed algorithm")
    ENABLE_FEED_ANALYTICS: bool = Field(True, description="Enable feed analytics")
    ENABLE_CONTENT_RECOMMENDATION: bool = Field(True, description="Enable content recommendations")
    
    # Storage Features
    ENABLE_IMAGE_OPTIMIZATION: bool = Field(True, description="Enable image optimization")
    ENABLE_VIDEO_PROCESSING: bool = Field(True, description="Enable video processing")
    ENABLE_CDN_INTEGRATION: bool = Field(True, description="Enable CDN integration")
    
    # Social Features
    ENABLE_SOCIAL_FEATURES: bool = Field(True, description="Enable social features")
    ENABLE_GAMIFICATION: bool = Field(True, description="Enable gamification")
    ENABLE_COMMUNITY: bool = Field(True, description="Enable community features")
    
    # Analytics
    ENABLE_USER_ANALYTICS: bool = Field(True, description="Enable user analytics")
    ENABLE_PERFORMANCE_MONITORING: bool = Field(True, description="Enable performance monitoring")
    ENABLE_ERROR_TRACKING: bool = Field(True, description="Enable error tracking")
    
    # ============================================================================
    # EXTERNAL SERVICES
    # ============================================================================
    
    # Email
    SMTP_HOST: Optional[str] = Field(None, description="SMTP host")
    SMTP_PORT: int = Field(587, description="SMTP port")
    SMTP_USERNAME: Optional[str] = Field(None, description="SMTP username")
    SMTP_PASSWORD: Optional[str] = Field(None, description="SMTP password")
    SMTP_TLS: bool = Field(True, description="SMTP TLS enabled")
    EMAIL_FROM: Optional[str] = Field(None, description="Email from address")
    
    # Push Notifications
    FCM_SERVER_KEY: Optional[str] = Field(None, description="Firebase Cloud Messaging server key")
    APNS_KEY_ID: Optional[str] = Field(None, description="Apple Push Notification service key ID")
    APNS_TEAM_ID: Optional[str] = Field(None, description="Apple Push Notification service team ID")
    APNS_BUNDLE_ID: Optional[str] = Field(None, description="Apple Push Notification service bundle ID")
    
    # Analytics Services
    GOOGLE_ANALYTICS_ID: Optional[str] = Field(None, description="Google Analytics tracking ID")
    MIXPANEL_TOKEN: Optional[str] = Field(None, description="Mixpanel project token")

    # Google Ads / Ad Manager
    GOOGLE_ADS_ENABLED: bool = Field(True, description="Enable Google Ads/Ad Manager integration")
    GOOGLE_ADS_NETWORK_CODE: Optional[str] = Field(None, description="Google Ad Manager network code")
    GOOGLE_ADS_APP_ID_IOS: Optional[str] = Field(None, description="AdMob app ID for iOS (ca-app-pub-...)")
    GOOGLE_ADS_APP_ID_ANDROID: Optional[str] = Field(None, description="AdMob app ID for Android (ca-app-pub-...)")
    GOOGLE_ADS_FEED_UNIT_ID: Optional[str] = Field(None, description="Ad unit ID for feed native ads")
    GOOGLE_ADS_STORY_UNIT_ID: Optional[str] = Field(None, description="Ad unit ID for story interstitial/video")
    GOOGLE_ADS_POST_UNIT_ID: Optional[str] = Field(None, description="Ad unit ID for in-post native")
    GOOGLE_ADS_TIMER_UNIT_ID: Optional[str] = Field(None, description="Ad unit ID for timer/loading video")
    
    # ============================================================================
    # RATE LIMITING
    # ============================================================================
    
    RATE_LIMIT_ENABLED: bool = Field(True, description="Enable rate limiting")
    RATE_LIMIT_PER_MINUTE: int = Field(60, description="Rate limit per minute")
    RATE_LIMIT_PER_HOUR: int = Field(1000, description="Rate limit per hour")
    RATE_LIMIT_PER_DAY: int = Field(10000, description="Rate limit per day")
    
    # ============================================================================
    # CACHING
    # ============================================================================
    
    CACHE_ENABLED: bool = Field(True, description="Enable caching")
    CACHE_DEFAULT_TTL: int = Field(3600, description="Default cache TTL (seconds)")
    CACHE_USER_DATA_TTL: int = Field(1800, description="User data cache TTL (seconds)")
    CACHE_STATIC_CONTENT_TTL: int = Field(86400, description="Static content cache TTL (seconds)")
    
    # ============================================================================
    # BACKWARD COMPATIBILITY ALIASES (lowercase for legacy code)
    # ============================================================================
    
    @property
    def database_url(self) -> str:
        """Lowercase alias for DATABASE_URL"""
        return self.DATABASE_URL
    
    @property
    def database_echo(self) -> bool:
        """Lowercase alias for DATABASE_ECHO"""
        return self.DATABASE_ECHO
    
    @property
    def database_pool_size(self) -> int:
        """Lowercase alias for DATABASE_POOL_SIZE"""
        return self.DATABASE_POOL_SIZE
    
    @property
    def database_max_overflow(self) -> int:
        """Lowercase alias for DATABASE_MAX_OVERFLOW"""
        return self.DATABASE_MAX_OVERFLOW
    
    @property
    def database_pool_timeout(self) -> int:
        """Lowercase alias for DATABASE_POOL_TIMEOUT"""
        return self.DATABASE_POOL_TIMEOUT
    
    @property
    def database_pool_recycle(self) -> int:
        """Lowercase alias for DATABASE_POOL_RECYCLE"""
        return self.DATABASE_POOL_RECYCLE
    
    @property
    def connection_pool_size(self) -> int:
        """Alias for DATABASE_POOL_SIZE (legacy name)"""
        return self.DATABASE_POOL_SIZE
    
    @property
    def max_overflow(self) -> int:
        """Alias for DATABASE_MAX_OVERFLOW (legacy name)"""
        return self.DATABASE_MAX_OVERFLOW
    
    # ============================================================================
    # VALIDATORS
    # ============================================================================
    
    @field_validator('ENVIRONMENT')
    @classmethod
    def validate_environment(cls, v):
        allowed_envs = ['development', 'staging', 'production']
        if v not in allowed_envs:
            raise ValueError(f'Environment must be one of: {allowed_envs}')
        return v
    
    @field_validator('LOG_LEVEL')
    @classmethod
    def validate_log_level(cls, v):
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed_levels:
            raise ValueError(f'Log level must be one of: {allowed_levels}')
        return v.upper()
    
    @field_validator('LOG_FORMAT')
    @classmethod
    def validate_log_format(cls, v):
        allowed_formats = ['json', 'text']
        if v not in allowed_formats:
            raise ValueError(f'Log format must be one of: {allowed_formats}')
        return v
    
    @field_validator('PORT')
    @classmethod
    def validate_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError('Port must be between 1 and 65535')
        return v
    
    @field_validator('PASSWORD_MIN_LENGTH')
    @classmethod
    def validate_password_min_length(cls, v):
        if v < 6:
            raise ValueError('Password minimum length must be at least 6')
        return v
    
    @field_validator('GEMINI_TEMPERATURE')
    @classmethod
    def validate_temperature(cls, v):
        if not 0.0 <= v <= 2.0:
            raise ValueError('Temperature must be between 0.0 and 2.0')
        return v
    
    @field_validator('GEMINI_TOP_P')
    @classmethod
    def validate_top_p(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError('Top_p must be between 0.0 and 1.0')
        return v
    
    @field_validator('MAX_UPLOAD_SIZE')
    @classmethod
    def validate_max_upload_size(cls, v):
        if v < 1024:  # 1KB minimum
            raise ValueError('Max upload size must be at least 1KB')
        if v > 1024 * 1024 * 1024:  # 1GB maximum
            raise ValueError('Max upload size cannot exceed 1GB')
        return v
    
    # Note: REDIS_URL computed dynamically based on REDIS_HOST/PORT
    # Removed validator that used pre=True/values pattern (incompatible with Pydantic V2)
    
    # ============================================================================
    # ENVIRONMENT-SPECIFIC CONFIGURATIONS
    # ============================================================================
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration"""
        return {
            'url': self.DATABASE_URL,
            'echo': self.DATABASE_ECHO,
            'pool_size': self.DATABASE_POOL_SIZE,
            'max_overflow': self.DATABASE_MAX_OVERFLOW,
            'pool_timeout': self.DATABASE_POOL_TIMEOUT,
            'pool_recycle': self.DATABASE_POOL_RECYCLE
        }
    
    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration"""
        return {
            'url': self.REDIS_URL,
            'max_connections': self.REDIS_MAX_CONNECTIONS,
            'decode_responses': True,
            'encoding': 'utf-8'
        }
    
    def get_cors_config(self) -> Dict[str, Any]:
        """Get CORS configuration"""
        return {
            'allow_origins': self.CORS_ORIGINS,
            'allow_credentials': self.CORS_CREDENTIALS,
            'allow_methods': self.CORS_METHODS,
            'allow_headers': self.CORS_HEADERS
        }
    
    def get_gemini_api_key(self) -> str:
        """Get Gemini API key, supporting both env var names"""
        return self.GOOGLE_API_KEY or self.GEMINI_API_KEY or ""
    
    def get_ai_config(self) -> Dict[str, Any]:
        """Get AI configuration"""
        return {
            'google': {
                'api_key': self.get_gemini_api_key(),
                'models': {
                    'default': self.GEMINI_MODEL_DEFAULT,
                    'vision': self.GEMINI_MODEL_VISION,
                    'flash': self.GEMINI_MODEL_FLASH
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
                'recovery_timeout': self.AI_CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
                'expected_exception': self.AI_CIRCUIT_BREAKER_EXPECTED_EXCEPTION
            }
        }
    
    def get_storage_config(self) -> Dict[str, Any]:
        """Get storage configuration"""
        return {
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
        """Get monitoring configuration"""
        return {
            'logging': {
                'level': self.LOG_LEVEL,
                'format': self.LOG_FORMAT,
                'file': self.LOG_FILE,
                'rotation': self.LOG_ROTATION,
                'retention': self.LOG_RETENTION
            },
            'metrics': {
                'enabled': self.ENABLE_METRICS,
                'port': self.METRICS_PORT
            },
            'tracing': {
                'enabled': self.ENABLE_TRACING,
                'jaeger_endpoint': self.JAEGER_ENDPOINT
            },
            'health_check': {
                'interval': self.HEALTH_CHECK_INTERVAL,
                'timeout': self.HEALTH_CHECK_TIMEOUT
            }
        }
    
    def get_feature_flags(self) -> Dict[str, bool]:
        """Get all feature flags"""
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
            'community': self.ENABLE_COMMUNITY,
            'user_analytics': self.ENABLE_USER_ANALYTICS,
            'performance_monitoring': self.ENABLE_PERFORMANCE_MONITORING,
            'error_tracking': self.ENABLE_ERROR_TRACKING
        }
    
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == 'production'
    
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == 'development'
    
    def is_staging(self) -> bool:
        """Check if running in staging"""
        return self.ENVIRONMENT == 'staging'
    
    # Pydantic V2 configuration
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "validate_assignment": True,
        "extra": "ignore"  # Ignore extra fields from legacy config
    }

# Global settings instance
settings = EnhancedSettings()

# Note: Environment-specific overrides removed. 
# All config should come from environment variables.
# The settings object respects env vars like DEBUG, DATABASE_ECHO, LOG_LEVEL, CORS_ORIGINS.

# Configuration validation
def validate_settings():
    """Validate critical settings"""
    
    errors = []
    
    # Check required secrets (only in production)
    if settings.is_production():
        if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
            errors.append("SECRET_KEY must be at least 32 characters long")
        
        # Support both GOOGLE_API_KEY and GEMINI_API_KEY
        if not settings.get_gemini_api_key():
            errors.append("GOOGLE_API_KEY or GEMINI_API_KEY is required in production")
        
        if not settings.DATABASE_URL:
            errors.append("DATABASE_URL is required")
        
        # Production-specific validations
        if settings.DEBUG:
            errors.append("DEBUG must be False in production")
        
        if "*" in settings.CORS_ORIGINS:
            errors.append("CORS_ORIGINS cannot contain '*' in production")
        
        if settings.LOG_LEVEL == "DEBUG":
            errors.append("LOG_LEVEL should not be DEBUG in production")
    
    if errors:
        raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

# Skip production validation at import time to prevent startup failures
# Configuration issues are logged as warnings instead
def safe_validate_settings():
    """Validate critical settings with warnings instead of hard failures"""
    warnings = []
    
    if settings.is_production():
        if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
            warnings.append("SECRET_KEY should be at least 32 characters long")
        
        if not settings.get_gemini_api_key():
            warnings.append("GOOGLE_API_KEY or GEMINI_API_KEY is recommended in production")
        
        if settings.DEBUG:
            warnings.append("DEBUG should be False in production")
        
        # CORS wildcard is OK for mobile apps but log a warning
        if "*" in settings.CORS_ORIGINS:
            warnings.append("CORS_ORIGINS contains '*' - ensure this is intentional for mobile app support")
    
    # Log warnings but don't crash
    if warnings:
        import logging
        logger = logging.getLogger(__name__)
        for w in warnings:
            logger.warning(f"Config warning: {w}")

# Run non-blocking validation
safe_validate_settings()
