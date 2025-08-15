"""
Market-Ready Logging System V2
=============================

Production-grade structured logging with Google Cloud integration.
Supports JSON structured logs, request correlation, and PII redaction.
"""

import logging
import logging.config
import sys
import time
import uuid
from typing import Any, Dict, Optional
from contextvars import ContextVar
from datetime import datetime
import json
import re

import structlog
from structlog.stdlib import LoggerFactory

from lyo_app.core.config_v2 import settings

# Context variables for request correlation
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


class PIIRedactor:
    """Redact personally identifiable information from logs."""
    
    # Patterns for PII detection
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    PHONE_PATTERN = re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')
    SSN_PATTERN = re.compile(r'\b\d{3}[-]?\d{2}[-]?\d{4}\b')
    CREDIT_CARD_PATTERN = re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b')
    
    @classmethod
    def redact_message(cls, message: str) -> str:
        """Redact PII from log message."""
        if not isinstance(message, str):
            return message
        
        # Redact different types of PII
        message = cls.EMAIL_PATTERN.sub('[EMAIL_REDACTED]', message)
        message = cls.PHONE_PATTERN.sub('[PHONE_REDACTED]', message)
        message = cls.SSN_PATTERN.sub('[SSN_REDACTED]', message)
        message = cls.CREDIT_CARD_PATTERN.sub('[CARD_REDACTED]', message)
        
        return message
    
    @classmethod
    def redact_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redact PII from dictionary data."""
        if not isinstance(data, dict):
            return data
        
        redacted = {}
        sensitive_keys = {'password', 'token', 'secret', 'key', 'auth', 'credential'}
        
        for key, value in data.items():
            if isinstance(key, str) and any(sensitive in key.lower() for sensitive in sensitive_keys):
                redacted[key] = '[REDACTED]'
            elif isinstance(value, str):
                redacted[key] = cls.redact_message(value)
            elif isinstance(value, dict):
                redacted[key] = cls.redact_dict(value)
            else:
                redacted[key] = value
        
        return redacted


def add_correlation_info(logger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add correlation information to log entries."""
    # Add request ID if available
    request_id = request_id_ctx.get()
    if request_id:
        event_dict["request_id"] = request_id
    
    # Add user ID if available
    user_id = user_id_ctx.get()
    if user_id:
        event_dict["user_id"] = user_id
    
    # Add timestamp
    event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
    
    # Add service info
    event_dict["service"] = "lyo-backend"
    event_dict["version"] = settings.APP_VERSION
    event_dict["environment"] = settings.ENVIRONMENT
    
    return event_dict


def redact_pii_processor(logger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Process logs to redact PII information."""
    if not settings.is_production():
        return event_dict  # Skip PII redaction in development
    
    # Redact message
    if "event" in event_dict:
        event_dict["event"] = PIIRedactor.redact_message(event_dict["event"])
    
    # Redact other fields
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = PIIRedactor.redact_message(value)
        elif isinstance(value, dict):
            event_dict[key] = PIIRedactor.redact_dict(value)
    
    return event_dict


def setup_logging():
    """Configure application logging."""
    
    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        add_correlation_info,
        redact_pii_processor,
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]
    
    if settings.STRUCTURED_LOGGING:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=not settings.is_production()),
        ])
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            min_level=getattr(logging, settings.LOG_LEVEL.upper())
        ),
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            } if settings.STRUCTURED_LOGGING else {
                "class": "logging.Formatter",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": sys.stdout,
            },
        },
        "root": {
            "level": settings.LOG_LEVEL.upper(),
            "handlers": ["default"],
        },
        "loggers": {
            "uvicorn": {
                "level": "INFO",
                "handlers": ["default"],
                "propagate": False,
            },
            "sqlalchemy": {
                "level": "WARNING",
                "handlers": ["default"],
                "propagate": False,
            },
            "httpx": {
                "level": "WARNING",
                "handlers": ["default"],
                "propagate": False,
            },
        },
    }
    
    logging.config.dictConfig(logging_config)


class RequestLogger:
    """Request-specific logger with correlation tracking."""
    
    def __init__(self, request_id: Optional[str] = None, user_id: Optional[str] = None):
        self.request_id = request_id or str(uuid.uuid4())
        self.user_id = user_id
        self.logger = structlog.get_logger(__name__)
    
    def __enter__(self):
        """Set context variables."""
        request_id_ctx.set(self.request_id)
        if self.user_id:
            user_id_ctx.set(self.user_id)
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clear context variables."""
        request_id_ctx.set(None)
        user_id_ctx.set(None)


class SecurityLogger:
    """Specialized logger for security events."""
    
    def __init__(self):
        self.logger = structlog.get_logger("security")
    
    def log_auth_attempt(self, user_id: Optional[str], success: bool, ip_address: str, user_agent: str):
        """Log authentication attempt."""
        self.logger.info(
            "Authentication attempt",
            user_id=user_id,
            success=success,
            ip_address=ip_address,
            user_agent=PIIRedactor.redact_message(user_agent),
            event_type="auth_attempt",
        )
    
    def log_permission_denied(self, user_id: Optional[str], resource: str, action: str):
        """Log permission denied event."""
        self.logger.warning(
            "Permission denied",
            user_id=user_id,
            resource=resource,
            action=action,
            event_type="permission_denied",
        )
    
    def log_suspicious_activity(self, user_id: Optional[str], activity: str, details: Dict[str, Any]):
        """Log suspicious activity."""
        self.logger.warning(
            "Suspicious activity detected",
            user_id=user_id,
            activity=activity,
            details=PIIRedactor.redact_dict(details),
            event_type="suspicious_activity",
        )
    
    def log_rate_limit_exceeded(self, user_id: Optional[str], endpoint: str, ip_address: str):
        """Log rate limit exceeded."""
        self.logger.warning(
            "Rate limit exceeded",
            user_id=user_id,
            endpoint=endpoint,
            ip_address=ip_address,
            event_type="rate_limit_exceeded",
        )


class PerformanceLogger:
    """Logger for performance metrics."""
    
    def __init__(self):
        self.logger = structlog.get_logger("performance")
    
    def log_request_timing(self, method: str, path: str, duration: float, status_code: int):
        """Log request timing information."""
        self.logger.info(
            "Request completed",
            method=method,
            path=path,
            duration_ms=round(duration * 1000, 2),
            status_code=status_code,
            event_type="request_timing",
        )
    
    def log_slow_query(self, query: str, duration: float, params: Optional[Dict] = None):
        """Log slow database queries."""
        self.logger.warning(
            "Slow query detected",
            query=query[:200] + "..." if len(query) > 200 else query,
            duration_ms=round(duration * 1000, 2),
            params=PIIRedactor.redact_dict(params) if params else None,
            event_type="slow_query",
        )
    
    def log_cache_stats(self, hit_rate: float, total_requests: int):
        """Log cache performance statistics."""
        self.logger.info(
            "Cache performance",
            hit_rate=hit_rate,
            total_requests=total_requests,
            event_type="cache_stats",
        )


# Global logger instances
logger = structlog.get_logger(__name__)
security_logger = SecurityLogger()
performance_logger = PerformanceLogger()


# Utility functions
def set_request_context(request_id: str, user_id: Optional[str] = None):
    """Set request context for correlation."""
    request_id_ctx.set(request_id)
    if user_id:
        user_id_ctx.set(user_id)


def get_request_id() -> Optional[str]:
    """Get current request ID from context."""
    return request_id_ctx.get()


def get_user_id() -> Optional[str]:
    """Get current user ID from context."""
    return user_id_ctx.get()
