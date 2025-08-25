"""
Production Configuration Manager
Enterprise-grade configuration management with environment-specific settings
"""

import os
from typing import Dict, Any, Optional, List
from pydantic import BaseSettings, validator, Field
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class Environment(str, Enum):
    """Deployment environments"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    """Log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO" 
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ProductionSettings(BaseSettings):
    """Production-ready configuration"""
    
    # Environment
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = False
    
    # Application
    APP_NAME: str = "LyoApp World-Class Backend"
    APP_VERSION: str = "2.0.0"
    SECRET_KEY: str = Field(..., min_length=32)
    ENCRYPTION_KEY: Optional[str] = None
    
    # API Configuration
    API_PREFIX: str = "/api/v2"
    ALLOWED_HOSTS: List[str] = ["*"]
    CORS_ORIGINS: List[str] = ["*"]
    
    # Database URLs
    DATABASE_URL: str = Field(..., description="PostgreSQL database URL")
    MONGODB_URL: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URL")
    REDIS_URL: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    INFLUXDB_URL: str = Field(default="http://localhost:8086", description="InfluxDB connection URL")
    
    # Database Configuration
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    
    # Cache Configuration
    REDIS_MAX_CONNECTIONS: int = 100
    CACHE_DEFAULT_TTL: int = 300  # 5 minutes
    CACHE_MAX_MEMORY_MB: int = 1024  # 1GB
    
    # Security Configuration
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ACCESS_TOKEN_EXPIRE: int = 900  # 15 minutes
    JWT_REFRESH_TOKEN_EXPIRE: int = 604800  # 7 days
    PASSWORD_MIN_LENGTH: int = 12
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION: int = 900  # 15 minutes
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    DEFAULT_RATE_LIMIT: str = "1000/hour"
    AI_RATE_LIMIT: str = "100/hour"
    
    # AI Configuration
    GOOGLE_AI_API_KEY: Optional[str] = None
    VERTEX_AI_PROJECT: Optional[str] = None
    VERTEX_AI_REGION: str = "us-central1"
    AI_CACHE_ENABLED: bool = True
    AI_CACHE_TTL: int = 3600  # 1 hour
    
    # Google Cloud Configuration
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    
    # Firebase Configuration
    FIREBASE_PROJECT_ID: Optional[str] = None
    FIREBASE_CREDENTIALS_PATH: Optional[str] = None
    
    # InfluxDB Configuration
    INFLUXDB_TOKEN: Optional[str] = None
    INFLUXDB_ORG: str = "lyo-org"
    INFLUXDB_BUCKET: str = "lyo-metrics"
    
    # Observability Configuration
    JAEGER_HOST: str = "localhost"
    JAEGER_PORT: int = 14268
    PROMETHEUS_ENABLED: bool = True
    METRICS_PORT: int = 9090
    
    # Logging Configuration
    LOG_LEVEL: LogLevel = LogLevel.INFO
    LOG_FORMAT: str = "json"
    LOG_FILE: Optional[str] = None
    STRUCTURED_LOGGING: bool = True
    
    # Email Configuration
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    
    # File Upload Configuration
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_FILE_TYPES: List[str] = ["image/jpeg", "image/png", "image/gif", "application/pdf"]
    UPLOAD_PATH: str = "/tmp/uploads"
    
    # Background Jobs Configuration
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    
    # Health Check Configuration
    HEALTH_CHECK_INTERVAL: int = 30  # seconds
    HEALTH_CHECK_TIMEOUT: int = 10   # seconds
    
    # Performance Configuration
    WORKER_CONNECTIONS: int = 1000
    WORKER_PROCESSES: int = 1
    WORKER_TIMEOUT: int = 30
    KEEP_ALIVE: int = 2
    
    # Feature Flags
    ENABLE_2FA: bool = True
    ENABLE_DEVICE_TRACKING: bool = True
    ENABLE_THREAT_DETECTION: bool = True
    ENABLE_COST_OPTIMIZATION: bool = True
    ENABLE_DISTRIBUTED_TRACING: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        
    @validator("ENVIRONMENT", pre=True)
    def validate_environment(cls, v):
        if isinstance(v, str):
            return Environment(v.lower())
        return v
    
    @validator("SECRET_KEY", pre=True)
    def validate_secret_key(cls, v):
        if not v or len(v) < 32:
            if cls.ENVIRONMENT == Environment.PRODUCTION:
                raise ValueError("SECRET_KEY must be at least 32 characters in production")
            # Generate a key for development
            import secrets
            return secrets.token_urlsafe(32)
        return v
    
    @validator("JWT_SECRET_KEY", pre=True, always=True)
    def validate_jwt_secret(cls, v, values):
        if not v:
            return values.get("SECRET_KEY")
        return v
    
    @validator("ENCRYPTION_KEY", pre=True, always=True)
    def validate_encryption_key(cls, v, values):
        if not v:
            if values.get("ENVIRONMENT") == Environment.PRODUCTION:
                raise ValueError("ENCRYPTION_KEY required in production")
            # Generate for development
            from cryptography.fernet import Fernet
            return Fernet.generate_key().decode()
        return v
    
    @validator("CORS_ORIGINS", pre=True)
    def validate_cors_origins(cls, v, values):
        if values.get("ENVIRONMENT") == Environment.PRODUCTION:
            if "*" in v:
                logger.warning("CORS_ORIGINS should not contain '*' in production")
        return v
    
    @validator("ALLOWED_HOSTS", pre=True) 
    def validate_allowed_hosts(cls, v, values):
        if values.get("ENVIRONMENT") == Environment.PRODUCTION:
            if "*" in v:
                logger.warning("ALLOWED_HOSTS should not contain '*' in production")
        return v
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == Environment.PRODUCTION
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == Environment.DEVELOPMENT
    
    @property
    def database_config(self) -> Dict[str, Any]:
        """Database configuration dictionary"""
        return {
            "url": self.DATABASE_URL,
            "pool_size": self.DB_POOL_SIZE,
            "max_overflow": self.DB_MAX_OVERFLOW,
            "pool_timeout": self.DB_POOL_TIMEOUT,
            "pool_recycle": self.DB_POOL_RECYCLE,
            "echo": self.DEBUG and not self.is_production
        }
    
    @property
    def cache_config(self) -> Dict[str, Any]:
        """Cache configuration dictionary"""
        return {
            "url": self.REDIS_URL,
            "max_connections": self.REDIS_MAX_CONNECTIONS,
            "default_ttl": self.CACHE_DEFAULT_TTL,
            "max_memory_mb": self.CACHE_MAX_MEMORY_MB
        }
    
    @property
    def security_config(self) -> Dict[str, Any]:
        """Security configuration dictionary"""
        return {
            "jwt_secret": self.JWT_SECRET_KEY,
            "jwt_access_expire": self.JWT_ACCESS_TOKEN_EXPIRE,
            "jwt_refresh_expire": self.JWT_REFRESH_TOKEN_EXPIRE,
            "password_min_length": self.PASSWORD_MIN_LENGTH,
            "max_login_attempts": self.MAX_LOGIN_ATTEMPTS,
            "lockout_duration": self.LOCKOUT_DURATION,
            "enable_2fa": self.ENABLE_2FA,
            "enable_device_tracking": self.ENABLE_DEVICE_TRACKING,
            "enable_threat_detection": self.ENABLE_THREAT_DETECTION
        }
    
    @property
    def observability_config(self) -> Dict[str, Any]:
        """Observability configuration dictionary"""
        return {
            "jaeger_host": self.JAEGER_HOST,
            "jaeger_port": self.JAEGER_PORT,
            "prometheus_enabled": self.PROMETHEUS_ENABLED,
            "metrics_port": self.METRICS_PORT,
            "log_level": self.LOG_LEVEL.value,
            "structured_logging": self.STRUCTURED_LOGGING,
            "enable_tracing": self.ENABLE_DISTRIBUTED_TRACING
        }
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Get environment information for health checks"""
        return {
            "environment": self.ENVIRONMENT.value,
            "app_name": self.APP_NAME,
            "app_version": self.APP_VERSION,
            "debug": self.DEBUG,
            "features": {
                "2fa_enabled": self.ENABLE_2FA,
                "device_tracking": self.ENABLE_DEVICE_TRACKING,
                "threat_detection": self.ENABLE_THREAT_DETECTION,
                "cost_optimization": self.ENABLE_COST_OPTIMIZATION,
                "distributed_tracing": self.ENABLE_DISTRIBUTED_TRACING,
                "rate_limiting": self.RATE_LIMIT_ENABLED
            }
        }


# Global settings instance
_settings: Optional[ProductionSettings] = None


def get_settings() -> ProductionSettings:
    """Get application settings singleton"""
    global _settings
    if _settings is None:
        _settings = ProductionSettings()
        logger.info(
            "Settings initialized",
            environment=_settings.ENVIRONMENT.value,
            debug=_settings.DEBUG
        )
    return _settings


# Convenience function for backward compatibility
def get_config() -> ProductionSettings:
    """Alias for get_settings()"""
    return get_settings()


# Environment-specific configuration presets
DEVELOPMENT_OVERRIDES = {
    "DEBUG": True,
    "LOG_LEVEL": "DEBUG",
    "RATE_LIMIT_ENABLED": False,
    "ENABLE_THREAT_DETECTION": False,
    "CORS_ORIGINS": ["http://localhost:3000", "http://127.0.0.1:3000"],
    "ALLOWED_HOSTS": ["localhost", "127.0.0.1"]
}

PRODUCTION_OVERRIDES = {
    "DEBUG": False,
    "LOG_LEVEL": "INFO", 
    "RATE_LIMIT_ENABLED": True,
    "ENABLE_THREAT_DETECTION": True,
    "WORKER_PROCESSES": 4,
    "DB_POOL_SIZE": 50,
    "DB_MAX_OVERFLOW": 100,
    "REDIS_MAX_CONNECTIONS": 200
}


def configure_for_environment(environment: Environment) -> Dict[str, Any]:
    """Get configuration overrides for specific environment"""
    
    if environment == Environment.DEVELOPMENT:
        return DEVELOPMENT_OVERRIDES
    elif environment == Environment.PRODUCTION:
        return PRODUCTION_OVERRIDES
    elif environment == Environment.TESTING:
        return {
            **DEVELOPMENT_OVERRIDES,
            "DATABASE_URL": "sqlite:///./test.db",
            "REDIS_URL": "redis://localhost:6379/1",  # Use different Redis DB
            "LOG_LEVEL": "WARNING"
        }
    else:  # STAGING
        return {
            **PRODUCTION_OVERRIDES,
            "DEBUG": True,
            "LOG_LEVEL": "DEBUG"
        }


if __name__ == "__main__":
    # Configuration validation
    settings = get_settings()
    
    print(f"Environment: {settings.ENVIRONMENT.value}")
    print(f"Debug: {settings.DEBUG}")
    print(f"Database: {settings.DATABASE_URL[:50]}...")
    print(f"Features: {settings.get_environment_info()['features']}")
    
    print("\nConfiguration validation complete!")
