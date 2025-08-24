"""
Market-Ready Exception Handling V2
=================================

Production-grade exception handling with proper error responses and logging.
"""

import traceback
from typing import Any, Dict, Optional, List
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
from redis.exceptions import RedisError
import asyncio

from lyo_app.core.config_v2 import settings
from lyo_app.core.logging_v2 import logger


class LyoAppException(Exception):
    """Base exception for LyoApp-specific errors."""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict] = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(LyoAppException):
    """Raised when request validation fails."""
    pass


class AuthenticationError(LyoAppException):
    """Raised when authentication fails."""
    pass


class AuthorizationError(LyoAppException):
    """Raised when authorization fails."""
    pass


class NotFoundError(LyoAppException):
    """Raised when requested resource is not found."""
    pass


class ConflictError(LyoAppException):
    """Raised when there's a conflict with existing data."""
    pass


class RateLimitError(LyoAppException):
    """Raised when rate limit is exceeded."""
    pass


class ServiceUnavailableError(LyoAppException):
    """Raised when external service is unavailable."""
    pass


class DatabaseError(LyoAppException):
    """Raised when database operation fails."""
    pass


class CacheError(LyoAppException):
    """Raised when cache operation fails."""
    pass


class AIServiceError(LyoAppException):
    """Raised when AI service operation fails."""
    pass


class ContentModerationError(LyoAppException):
    """Raised when content moderation fails."""
    pass


def create_error_response(
    status_code: int,
    message: str,
    error_code: Optional[str] = None,
    details: Optional[Any] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create standardized error response."""
    
    error_response = {
        "error": {
            "message": message,
            "status_code": status_code,
        }
    }
    
    if error_code:
        error_response["error"]["code"] = error_code
    
    if details:
        error_response["error"]["details"] = details
    
    if request_id:
        error_response["request_id"] = request_id
    
    if not settings.is_production():
        # Include additional debug info in development
        error_response["error"]["timestamp"] = "2025-08-14T00:00:00Z"
        error_response["error"]["environment"] = settings.ENVIRONMENT
    
    return error_response


async def lyoapp_exception_handler(request: Request, exc: LyoAppException) -> JSONResponse:
    """Handle LyoApp-specific exceptions."""
    
    # Map exception types to HTTP status codes
    status_code_map = {
        ValidationError: status.HTTP_400_BAD_REQUEST,
        AuthenticationError: status.HTTP_401_UNAUTHORIZED,
        AuthorizationError: status.HTTP_403_FORBIDDEN,
        NotFoundError: status.HTTP_404_NOT_FOUND,
        ConflictError: status.HTTP_409_CONFLICT,
        RateLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
        ServiceUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
        DatabaseError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        CacheError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        AIServiceError: status.HTTP_502_BAD_GATEWAY,
        ContentModerationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    
    status_code = status_code_map.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    request_id = getattr(request.state, "request_id", None)
    
    # Log the exception
    logger.error(
        f"{type(exc).__name__}: {exc.message}",
        error_code=exc.error_code,
        details=exc.details,
        request_id=request_id,
        path=request.url.path,
        method=request.method,
    )
    
    return JSONResponse(
        status_code=status_code,
        content=create_error_response(
            status_code=status_code,
            message=exc.message,
            error_code=exc.error_code,
            details=exc.details,
            request_id=request_id,
        )
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions."""
    
    request_id = getattr(request.state, "request_id", None)
    
    # Log non-4xx errors
    if exc.status_code >= 500:
        logger.error(
            f"HTTP {exc.status_code}: {exc.detail}",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            status_code=exc.status_code,
            message=exc.detail,
            request_id=request_id,
        )
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors."""
    
    request_id = getattr(request.state, "request_id", None)
    
    # Format validation errors
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
        })
    
    logger.warning(
        f"Validation error: {len(errors)} fields failed validation",
        errors=errors,
        request_id=request_id,
        path=request.url.path,
        method=request.method,
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=create_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Request validation failed",
            error_code="VALIDATION_ERROR",
            details={"fields": errors},
            request_id=request_id,
        )
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle SQLAlchemy database exceptions."""
    
    request_id = getattr(request.state, "request_id", None)
    
    logger.error(
        f"Database error: {str(exc)}",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        exception_type=type(exc).__name__,
    )
    
    # Don't expose internal database errors in production
    message = "Database operation failed"
    if not settings.is_production():
        message = f"Database error: {str(exc)}"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=message,
            error_code="DATABASE_ERROR",
            request_id=request_id,
        )
    )


async def redis_exception_handler(request: Request, exc: RedisError) -> JSONResponse:
    """Handle Redis cache exceptions."""
    
    request_id = getattr(request.state, "request_id", None)
    
    logger.error(
        f"Cache error: {str(exc)}",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        exception_type=type(exc).__name__,
    )
    
    # Cache errors shouldn't break the request, but log them
    message = "Cache operation failed - continuing without cache"
    if not settings.is_production():
        message = f"Redis error: {str(exc)}"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=message,
            error_code="CACHE_ERROR",
            request_id=request_id,
        )
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    
    request_id = getattr(request.state, "request_id", None)
    
    # Log full traceback for debugging
    logger.error(
        f"Unhandled exception: {str(exc)}",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        exception_type=type(exc).__name__,
        traceback=traceback.format_exc() if not settings.is_production() else None,
    )
    
    # Generic error message for production
    message = "An unexpected error occurred"
    if not settings.is_production():
        message = f"Unhandled exception: {str(exc)}"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=message,
            error_code="INTERNAL_ERROR",
            request_id=request_id,
        )
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Setup all exception handlers for the FastAPI app."""
    
    # LyoApp-specific exceptions
    app.add_exception_handler(LyoAppException, lyoapp_exception_handler)
    
    # FastAPI exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # External service exceptions
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(RedisError, redis_exception_handler)
    
    # Generic exception handler (must be last)
    app.add_exception_handler(Exception, generic_exception_handler)
    
    logger.info("Exception handlers configured")
