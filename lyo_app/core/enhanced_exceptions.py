"""
Enhanced error handling middleware with comprehensive exception handling.
Provides consistent error responses and proper exception handling.
"""

import logging
import traceback
from typing import Any, Dict, Optional, Union

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base API exception."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "API_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class DatabaseError(APIError):
    """Database-related errors."""
    
    def __init__(self, message: str = "Database operation failed", **kwargs):
        super().__init__(message, status_code=500, error_code="DATABASE_ERROR", **kwargs)


class AuthenticationError(APIError):
    """Authentication-related errors."""
    
    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(message, status_code=401, error_code="AUTH_ERROR", **kwargs)


class AuthorizationError(APIError):
    """Authorization-related errors."""
    
    def __init__(self, message: str = "Access denied", **kwargs):
        super().__init__(message, status_code=403, error_code="ACCESS_DENIED", **kwargs)


class AppValidationError(APIError):
    """Validation-related errors."""
    
    def __init__(self, message: str = "Validation failed", **kwargs):
        super().__init__(message, status_code=422, error_code="VALIDATION_ERROR", **kwargs)


class RateLimitError(APIError):
    """Rate limiting errors."""
    
    def __init__(self, message: str = "Rate limit exceeded", **kwargs):
        super().__init__(message, status_code=429, error_code="RATE_LIMIT_EXCEEDED", **kwargs)


async def error_handler_middleware(request: Request, call_next):
    """Global error handling middleware."""
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        return await handle_exception(request, exc)


async def handle_exception(request: Request, exc: Exception) -> JSONResponse:
    """Handle different types of exceptions with consistent responses."""
    
    # Log the exception with context
    logger.error(
        f"Exception in {request.method} {request.url.path}: {exc}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client_host": request.client.host if request.client else "unknown",
            "exception_type": exc.__class__.__name__
        }
    )
    
    # API errors (our custom exceptions)
    if isinstance(exc, APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details
                }
            }
        )
    
    # FastAPI/Starlette HTTP exceptions
    elif isinstance(exc, StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail
                }
            }
        )
    
    # Pydantic validation errors
    elif isinstance(exc, (ValidationError, RequestValidationError)):
        errors = exc.errors() if hasattr(exc, 'errors') else [{"msg": str(exc)}]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {
                        "errors": errors
                    }
                }
            }
        )
    
    # Database errors
    elif isinstance(exc, IntegrityError):
        logger.error(f"Database integrity error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": {
                    "code": "DATABASE_CONFLICT",
                    "message": "The requested operation conflicts with existing data"
                }
            }
        )
    
    elif isinstance(exc, OperationalError):
        logger.error(f"Database operational error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "Database service is temporarily unavailable"
                }
            }
        )
    
    # Unexpected errors
    else:
        logger.error(f"Unexpected error: {exc}\n{traceback.format_exc()}")
        
        # Don't expose internal errors in production
        if settings.environment == "production":
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred"
                    }
                }
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": str(exc),
                        "details": {
                            "type": exc.__class__.__name__,
                            "traceback": traceback.format_exc().split('\n')
                        }
                    }
                }
            )


def setup_error_handlers(app):
    """Set up custom error handlers for the FastAPI app."""
    
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        return await handle_exception(request, exc)
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return await handle_exception(request, exc)
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return await handle_exception(request, exc)
    
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        return await handle_exception(request, exc)
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        return await handle_exception(request, exc)
