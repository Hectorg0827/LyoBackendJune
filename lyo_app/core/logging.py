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
    
    # Application loggers stay useful at INFO in production. Third-party
    # database internals do not: SQLAlchemy emits every reflected statement at
    # INFO, which can exceed Railway's 500 logs/sec cap during schema startup
    # and hide the errors we actually need. Debug mode intentionally restores
    # verbose SQL logging for local diagnosis.
    app_level = logging.DEBUG if settings.debug else logging.INFO
    for logger_name in ("uvicorn.access", "uvicorn.error", "lyo_app"):
        logging.getLogger(logger_name).setLevel(app_level)

    sql_level = logging.DEBUG if settings.debug else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level)
    logging.getLogger("sqlalchemy.pool").setLevel(sql_level)


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


# Default logger instance for convenience
logger = get_logger("lyo_app")
