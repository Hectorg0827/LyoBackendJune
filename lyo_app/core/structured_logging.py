"""
Structured Logging Module for LYO Backend

Provides structured logging configuration for different environments.
"""

import logging
import logging.config
import re
import sys
from typing import Optional



class RedactClassroomWebSocketQuery(logging.Filter):
    """Remove Classroom URL query params from Uvicorn protocol/access logs.

    WebSocket [accepted] messages may be INFO records from uvicorn.error,
    bypassing --no-access-log. Replace the entire query, not only token=,
    because parameter ordering and future credential fields can change.
    """

    _query = re.compile(r"(/api/v1/classroom/ws/connect)\?[^\s\"\x27]+")

    @classmethod
    def _sanitize(cls, value):
        if not isinstance(value, str):
            return value
        return cls._query.sub(r"\1?[QUERY_REDACTED]", value)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._sanitize(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._sanitize(item) for item in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: self._sanitize(val) for key, val in record.args.items()}
        return True



def setup_logging(
    environment: str = "development",
    log_level: str = "INFO",
    json_logs: bool = False
) -> None:
    """
    Configure structured logging for the application.
    
    Args:
        environment: Current environment (development, staging, production)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Whether to use JSON format for logs (recommended for production)
    """
    
    # Determine log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure log format based on environment
    if json_logs:
        # JSON format for production (easier to parse with log aggregators)
        log_format = '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
    else:
        # Human-readable format for development
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific log levels for noisy libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Uvicorn logs WebSocket accepted URLs via uvicorn.error, *not*
    # uvicorn.access. Those URLs can contain credentials from older clients.
    # Children with their own INFO level bypass the parent logger's level.
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.protocols.websockets").setLevel(logging.WARNING)
    for name in ("uvicorn.error", "uvicorn.access", "uvicorn.protocols.websockets"):
        target = logging.getLogger(name)
        if not any(isinstance(item, RedactClassroomWebSocketQuery) for item in target.filters):
            target.addFilter(RedactClassroomWebSocketQuery())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    # Log the configuration
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging configured: environment={environment}, "
        f"level={log_level}, json_logs={json_logs}"
    )


class StructuredLogger:
    """
    A wrapper for structured logging with context.
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.context = {}
    
    def with_context(self, **kwargs) -> "StructuredLogger":
        """Add context to log messages."""
        new_logger = StructuredLogger(self.logger.name)
        new_logger.context = {**self.context, **kwargs}
        return new_logger
    
    def _format_message(self, message: str) -> str:
        """Format message with context."""
        if self.context:
            context_str = " ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{message} [{context_str}]"
        return message
    
    def debug(self, message: str, **kwargs):
        self.logger.debug(self._format_message(message), **kwargs)
    
    def info(self, message: str, **kwargs):
        self.logger.info(self._format_message(message), **kwargs)
    
    def warning(self, message: str, **kwargs):
        self.logger.warning(self._format_message(message), **kwargs)
    
    def error(self, message: str, **kwargs):
        self.logger.error(self._format_message(message), **kwargs)
    
    def critical(self, message: str, **kwargs):
        self.logger.critical(self._format_message(message), **kwargs)
    
    def exception(self, message: str, **kwargs):
        self.logger.exception(self._format_message(message), **kwargs)


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger for the given name.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)
