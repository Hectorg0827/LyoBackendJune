"""
Global error handling and custom exceptions for LyoApp.
Provides consistent error responses and proper exception handling.
"""

from typing import Any, Dict, Optional, Union
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import logging

logger = logging.getLogger(__name__)


class LyoAppException(Exception):
    """Base exception for LyoApp."""
    
    def __init__(
        self,
        message: str,
        error_code: str = "LYOAPP_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(LyoAppException):
    """Authentication related errors."""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="AUTH_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details
        )


class AuthorizationError(LyoAppException):
    """Authorization related errors."""
    
    def __init__(self, message: str = "Access denied", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details
        )


class ValidationError(LyoAppException):
    """Validation related errors."""
    
    def __init__(self, message: str = "Validation failed", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )


class NotFoundError(LyoAppException):
    """Resource not found errors."""
    
    def __init__(self, message: str = "Resource not found", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details
        )


class ConflictError(LyoAppException):
    """Resource conflict errors."""
    
    def __init__(self, message: str = "Resource conflict", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="CONFLICT_ERROR",
            status_code=status.HTTP_409_CONFLICT,
            details=details
        )


class RateLimitError(LyoAppException):
    """Rate limiting errors."""
    
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_ERROR",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details
        )


class DatabaseError(LyoAppException):
    """Database related errors."""
    
    def __init__(self, message: str = "Database error", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class FileUploadError(LyoAppException):
    """File upload related errors."""
    
    def __init__(self, message: str = "File upload failed", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            error_code="FILE_UPLOAD_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


def create_error_response(
    error_code: str,
    message: str,
    status_code: int = 500,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None
) -> JSONResponse:
    """Create standardized error response."""
    
    error_response = {
        "error": {
            "code": error_code,
            "message": message,
            "timestamp": str(datetime.utcnow()),
        }
    }
    
    if details:
        error_response["error"]["details"] = details
    
    if request_id:
        error_response["error"]["request_id"] = request_id
    
    return JSONResponse(
        status_code=status_code,
        content=error_response
    )


async def lyoapp_exception_handler(request: Request, exc: LyoAppException) -> JSONResponse:
    """Handle LyoApp custom exceptions."""
    logger.error(f"LyoApp exception: {exc.error_code} - {exc.message}", exc_info=True)
    
    return create_error_response(
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        request_id=getattr(request.state, 'request_id', None)
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions."""
    logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
    
    return create_error_response(
        error_code="HTTP_ERROR",
        message=exc.detail if isinstance(exc.detail, str) else "HTTP error occurred",
        status_code=exc.status_code,
        details=exc.detail if isinstance(exc.detail, dict) else None,
        request_id=getattr(request.state, 'request_id', None)
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI validation exceptions."""
    logger.warning(f"Validation error: {exc.errors()}")
    
    # Format validation errors
    formatted_errors = []
    for error in exc.errors():
        formatted_errors.append({
            "field": " -> ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    return create_error_response(
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"validation_errors": formatted_errors},
        request_id=getattr(request.state, 'request_id', None)
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle SQLAlchemy database exceptions."""
    logger.error(f"Database error: {str(exc)}", exc_info=True)
    
    # Handle specific database errors
    if isinstance(exc, IntegrityError):
        return create_error_response(
            error_code="DATABASE_INTEGRITY_ERROR",
            message="Database integrity constraint violated",
            status_code=status.HTTP_409_CONFLICT,
            details={"database_error": "Duplicate or invalid data"},
            request_id=getattr(request.state, 'request_id', None)
        )
    
    return create_error_response(
        error_code="DATABASE_ERROR",
        message="Database operation failed",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={"database_error": "Internal database error"},
        request_id=getattr(request.state, 'request_id', None)
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    
    return create_error_response(
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={"error_type": type(exc).__name__},
        request_id=getattr(request.state, 'request_id', None)
    )


async def authentication_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle authentication errors."""
    logger.warning(f"Authentication error on {request.url}: {str(exc)}")
    
    return create_error_response(
        error_code="AUTHENTICATION_ERROR",
        message="Authentication failed",
        status_code=status.HTTP_401_UNAUTHORIZED,
        details={"path": str(request.url.path)},
        request_id=getattr(request.state, 'request_id', None)
    )


async def authorization_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle authorization errors."""
    logger.warning(f"Authorization error on {request.url}: {str(exc)}")
    
    return create_error_response(
        error_code="AUTHORIZATION_ERROR", 
        message="Access denied",
        status_code=status.HTTP_403_FORBIDDEN,
        details={"path": str(request.url.path)},
        request_id=getattr(request.state, 'request_id', None)
    )


async def rate_limit_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle rate limiting errors."""
    logger.warning(f"Rate limit exceeded on {request.url}")
    
    return create_error_response(
        error_code="RATE_LIMIT_EXCEEDED",
        message="Too many requests. Please try again later.",
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        details={"retry_after": "60"},
        request_id=getattr(request.state, 'request_id', None)
    )


def setup_error_handlers(app):
    """Set up all error handlers for the FastAPI app."""
    from datetime import datetime
    
    # Custom exceptions
    app.add_exception_handler(LyoAppException, lyoapp_exception_handler)
    
    # FastAPI exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # Database exceptions
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    
    # Specific authentication/authorization handlers
    try:
        from jose import JWTError
        app.add_exception_handler(JWTError, authentication_exception_handler)
    except ImportError:
        pass
    
    try:
        from slowapi.errors import RateLimitExceeded
        app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
    except ImportError:
        pass
    
    # General exceptions (catch-all)
    app.add_exception_handler(Exception, general_exception_handler)
