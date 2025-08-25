"""
Environment-specific configuration management for LyoBackend
Provides configuration overrides and environment-specific settings
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class EnvironmentConfig:
    """Environment-specific configuration"""
    name: str
    debug: bool = False
    log_level: str = "INFO"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    redis_max_connections: int = 20
    celery_worker_concurrency: int = 4
    websocket_max_connections: int = 100
    api_rate_limit: str = "100/minute"
    cors_origins: list = field(default_factory=list)
    allowed_hosts: list = field(default_factory=list)
    enable_metrics: bool = True
    enable_tracing: bool = True
    enable_health_checks: bool = True
    
    # Feature flags
    enable_ai_generation: bool = True
    enable_push_notifications: bool = True
    enable_websockets: bool = True
    enable_feeds: bool = True
    enable_community: bool = True
    enable_gamification: bool = True
    
    # External service configurations
    model_download_timeout: int = 300  # 5 minutes
    external_api_timeout: int = 30
    max_course_generation_time: int = 600  # 10 minutes
    
    # Security settings
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    password_min_length: int = 8
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15

# Environment configurations
ENVIRONMENTS = {
    "development": EnvironmentConfig(
        name="development",
        debug=True,
        log_level="DEBUG",
        database_pool_size=2,
        database_max_overflow=5,
        redis_max_connections=10,
        celery_worker_concurrency=2,
        websocket_max_connections=50,
        api_rate_limit="1000/minute",  # More permissive for dev
        cors_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allowed_hosts=["localhost", "127.0.0.1"],
        enable_metrics=False,
        enable_tracing=False,
        model_download_timeout=600,  # Longer for dev
        jwt_access_token_expire_minutes=60,  # Longer for dev convenience
        max_login_attempts=10,  # More permissive for dev
    ),
    
    "staging": EnvironmentConfig(
        name="staging",
        debug=False,
        log_level="INFO",
        database_pool_size=5,
        database_max_overflow=10,
        redis_max_connections=20,
        celery_worker_concurrency=4,
        websocket_max_connections=100,
        api_rate_limit="500/minute",
        cors_origins=[
            "https://staging.lyoapp.com",
            "https://staging-admin.lyoapp.com"
        ],
        allowed_hosts=["staging.lyoapp.com"],
        enable_metrics=True,
        enable_tracing=True,
        model_download_timeout=300,
    ),
    
    "production": EnvironmentConfig(
        name="production",
        debug=False,
        log_level="WARNING",
        database_pool_size=10,
        database_max_overflow=20,
        redis_max_connections=50,
        celery_worker_concurrency=8,
        websocket_max_connections=500,
        api_rate_limit="100/minute",
        cors_origins=[
            "https://lyoapp.com",
            "https://admin.lyoapp.com",
            "https://app.lyoapp.com"
        ],
        allowed_hosts=["lyoapp.com", "api.lyoapp.com"],
        enable_metrics=True,
        enable_tracing=True,
        model_download_timeout=300,
        jwt_access_token_expire_minutes=15,  # Shorter for security
        max_login_attempts=3,  # Stricter for production
        lockout_duration_minutes=30,  # Longer lockout
    )
}

class EnvironmentManager:
    """Manages environment-specific configurations"""
    
    def __init__(self):
        self.current_env = os.getenv("ENVIRONMENT", "development").lower()
        self.config = ENVIRONMENTS.get(self.current_env, ENVIRONMENTS["development"])
        
    def get_config(self) -> EnvironmentConfig:
        """Get current environment configuration"""
        return self.config
    
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.current_env == "development"
    
    def is_staging(self) -> bool:
        """Check if running in staging mode"""
        return self.current_env == "staging"
    
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.current_env == "production"
    
    def get_feature_flags(self) -> Dict[str, bool]:
        """Get all feature flags for current environment"""
        config = self.config
        return {
            "ai_generation": config.enable_ai_generation,
            "push_notifications": config.enable_push_notifications,
            "websockets": config.enable_websockets,
            "feeds": config.enable_feeds,
            "community": config.enable_community,
            "gamification": config.enable_gamification,
        }
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a specific feature is enabled"""
        feature_flags = self.get_feature_flags()
        return feature_flags.get(feature, False)
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration for current environment"""
        config = self.config
        return {
            "pool_size": config.database_pool_size,
            "max_overflow": config.database_max_overflow,
            "echo": config.debug,
        }
    
    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration for current environment"""
        config = self.config
        return {
            "max_connections": config.redis_max_connections,
            "decode_responses": True,
        }
    
    def get_celery_config(self) -> Dict[str, Any]:
        """Get Celery configuration for current environment"""
        config = self.config
        return {
            "worker_concurrency": config.celery_worker_concurrency,
            "task_serializer": "json",
            "accept_content": ["json"],
            "result_serializer": "json",
            "timezone": "UTC",
            "enable_utc": True,
            "task_track_started": True,
            "task_time_limit": config.max_course_generation_time,
            "worker_prefetch_multiplier": 1 if self.is_production() else 4,
        }
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration for current environment"""
        config = self.config
        return {
            "jwt_access_token_expire_minutes": config.jwt_access_token_expire_minutes,
            "jwt_refresh_token_expire_days": config.jwt_refresh_token_expire_days,
            "password_min_length": config.password_min_length,
            "max_login_attempts": config.max_login_attempts,
            "lockout_duration_minutes": config.lockout_duration_minutes,
        }
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration for current environment"""
        config = self.config
        
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                },
                "json": {
                    "format": '{"timestamp": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}'
                }
            },
            "handlers": {
                "default": {
                    "formatter": "json" if self.is_production() else "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout"
                }
            },
            "root": {
                "level": config.log_level,
                "handlers": ["default"]
            }
        }
        
        return log_config

# Global environment manager instance
env_manager = EnvironmentManager()

def get_environment_config() -> EnvironmentConfig:
    """Get current environment configuration"""
    return env_manager.get_config()

def is_feature_enabled(feature: str) -> bool:
    """Check if a feature is enabled in current environment"""
    return env_manager.is_feature_enabled(feature)

def get_feature_flags() -> Dict[str, bool]:
    """Get all feature flags for current environment"""
    return env_manager.get_feature_flags()
