"""
Logging configuration for the LyoApp backend.
Provides structured logging with proper formatting and levels.
"""

import logging
import sys
from typing import Any, Dict

from .config import settings


def setup_logging() -> None:
    """Configure structured logging for the application."""
    
    # Configure the root logger
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    
    # Configure specific loggers
    loggers = [
        "uvicorn.access",
        "uvicorn.error", 
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "lyo_app",
    ]
    
    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name."""
    return logging.getLogger(name)


class StructuredMessage:
    """Helper class for structured logging messages."""
    
    def __init__(self, message: str, **kwargs: Any) -> None:
        self.message = message
        self.kwargs = kwargs
    
    def __str__(self) -> str:
        if self.kwargs:
            return f"{self.message} | {self.kwargs}"
        return self.message


def log_request(logger: logging.Logger, method: str, url: str, **kwargs: Any) -> None:
    """Log an HTTP request with structured data."""
    logger.info(StructuredMessage(f"{method} {url}", **kwargs))


def log_error(logger: logging.Logger, error: Exception, **kwargs: Any) -> None:
    """Log an error with structured data."""
    logger.error(
        StructuredMessage(f"Error: {type(error).__name__}: {str(error)}", **kwargs),
        exc_info=True
    )
