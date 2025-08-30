"""
Unified Error Handling System
----------------------------
Provides consistent error responses, logging, and monitoring for all API endpoints.
This ensures that errors are properly categorized, logged, and presented to users
with appropriate messages.

Features:
- Consistent error response structure
- User-friendly error messages
- Detailed error logging for debugging
- Error categorization
- Integration with monitoring systems
"""

import sys
import traceback
import logging
from typing import Dict, Any, Optional, List, Type, Union
from enum import Enum

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from pydantic import ValidationError

try:
    # Optional Sentry integration
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

# Configure logger
logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Error categories for better error handling and monitoring."""
    
    # Authentication and authorization errors
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    
    # Data validation and input errors
    VALIDATION = "validation"
    MALFORMED_REQUEST = "malformed_request"
    
    # Resource-related errors
    RESOURCE_NOT_FOUND = "resource_not_found"
    RESOURCE_CONFLICT = "resource_conflict"
    RESOURCE_GONE = "resource_gone"
    
    # Database errors
    DATABASE_ERROR = "database_error"
    DATABASE_CONSTRAINT = "database_constraint"
    DATABASE_CONNECTION = "database_connection"
    
    # External service errors
    EXTERNAL_SERVICE = "external_service"
    DEPENDENCY_ERROR = "dependency_error"
    
    # Rate limiting and quota errors
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    
    # Internal server errors
    INTERNAL_SERVER_ERROR = "internal_server_error"
    UNHANDLED_EXCEPTION = "unhandled_exception"
    
    # Feature and configuration errors
    FEATURE_DISABLED = "feature_disabled"
    CONFIGURATION_ERROR = "configuration_error"
    
    # AI-specific errors
    AI_SERVICE_ERROR = "ai_service_error"
    AI_CONTENT_POLICY = "ai_content_policy"
    AI_QUOTA_EXCEEDED = "ai_quota_exceeded"


class ErrorDetail:
    """Structured error detail for consistent error responses."""
    
    def __init__(
        self,
        message: str,
        code: str,
        category: ErrorCategory,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize error detail with message, code, and optional field/details."""
        self.message = message
        self.code = code
        self.category = category
        self.field = field
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error detail to dictionary for response."""
        result = {
            "message": self.message,
            "code": self.code,
            "category": self.category
        }
        
        if self.field:
            result["field"] = self.field
        
        if self.details:
            result["details"] = self.details
        
        return result


class ErrorResponse:
    """Standard error response structure."""
    
    def __init__(
        self,
        error_message: str,
        status_code: int = 400,
        error_code: str = "bad_request",
        error_category: ErrorCategory = ErrorCategory.VALIDATION,
        error_details: Optional[Dict[str, Any]] = None,
        error_fields: Optional[List[ErrorDetail]] = None,
        request_id: Optional[str] = None
    ):
        """Initialize error response with message and optional details."""
        self.error_message = error_message
        self.status_code = status_code
        self.error_code = error_code
        self.error_category = error_category
        self.error_details = error_details or {}
        self.error_fields = error_fields or []
        self.request_id = request_id
    
    def to_response(self) -> JSONResponse:
        """Convert to FastAPI JSON response."""
        response_body = {
            "error": {
                "message": self.error_message,
                "code": self.error_code,
                "category": self.error_category
            }
        }
        
        if self.error_fields:
            response_body["error"]["fields"] = [
                field.to_dict() for field in self.error_fields
            ]
        
        if self.error_details:
            response_body["error"]["details"] = self.error_details
        
        if self.request_id:
            response_body["request_id"] = self.request_id
        
        return JSONResponse(
            status_code=self.status_code,
            content=response_body
        )


class ErrorHandler:
    """Unified error handler for consistent error responses."""
    
    def __init__(self):
        """Initialize error handler."""
        self.debug_mode = False
        self.environment = "development"
    
    def configure(self, debug_mode: bool, environment: str):
        """Configure error handler with settings."""
        self.debug_mode = debug_mode
        self.environment = environment
    
    def create_error_response(
        self,
        error_message: str,
        status_code: int = 400,
        error_code: str = "bad_request",
        error_category: ErrorCategory = ErrorCategory.VALIDATION,
        error_details: Optional[Dict[str, Any]] = None,
        error_fields: Optional[List[ErrorDetail]] = None,
        request_id: Optional[str] = None
    ) -> ErrorResponse:
        """Create a standard error response."""
        return ErrorResponse(
            error_message=error_message,
            status_code=status_code,
            error_code=error_code,
            error_category=error_category,
            error_details=error_details,
            error_fields=error_fields,
            request_id=request_id
        )
    
    def _get_request_id(self, request: Optional[Request] = None) -> Optional[str]:
        """Extract request ID from request headers."""
        if request and "X-Request-ID" in request.headers:
            return request.headers["X-Request-ID"]
        return None
    
    async def handle_request_validation_error(
        self, request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle FastAPI request validation errors."""
        logger.warning(f"Validation error: {exc}")
        
        error_fields = []
        for error in exc.errors():
            location = error.get("loc", [])
            field = location[-1] if location else None
            field_type = location[0] if location else None
            
            if field_type == "body":
                field_loc = ".".join(str(loc) for loc in location[1:])
                error_detail = ErrorDetail(
                    message=error.get("msg", "Validation error"),
                    code="invalid_field",
                    category=ErrorCategory.VALIDATION,
                    field=field_loc,
                    details={"type": error.get("type", "")}
                )
            elif field_type in ["query", "path", "header"]:
                error_detail = ErrorDetail(
                    message=error.get("msg", "Invalid parameter"),
                    code=f"invalid_{field_type}_parameter",
                    category=ErrorCategory.VALIDATION,
                    field=field,
                    details={"type": error.get("type", "")}
                )
            else:
                error_detail = ErrorDetail(
                    message=error.get("msg", "Validation error"),
                    code="validation_error",
                    category=ErrorCategory.VALIDATION,
                    details={"type": error.get("type", "")}
                )
            
            error_fields.append(error_detail)
        
        error_response = self.create_error_response(
            error_message="Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="validation_error",
            error_category=ErrorCategory.VALIDATION,
            error_fields=error_fields,
            request_id=self._get_request_id(request)
        )
        
        return error_response.to_response()
    
    async def handle_database_error(
        self, request: Request, exc: SQLAlchemyError
    ) -> JSONResponse:
        """Handle database-related errors."""
        logger.error(f"Database error: {exc}")
        
        # Track in Sentry if available
        if SENTRY_AVAILABLE:
            sentry_sdk.capture_exception(exc)
        
        error_code = "database_error"
        error_category = ErrorCategory.DATABASE_ERROR
        error_message = "A database error occurred"
        error_details = {}
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        # Handle specific database errors
        if isinstance(exc, IntegrityError):
            error_code = "database_constraint_violation"
            error_category = ErrorCategory.DATABASE_CONSTRAINT
            
            # Check for common integrity error patterns
            error_str = str(exc).lower()
            if "unique constraint" in error_str or "unique violation" in error_str:
                error_message = "This record already exists"
                error_code = "duplicate_record"
                status_code = status.HTTP_409_CONFLICT
            elif "foreign key constraint" in error_str:
                error_message = "Referenced record does not exist"
                error_code = "invalid_reference"
                status_code = status.HTTP_400_BAD_REQUEST
            else:
                error_message = "Database constraint violation"
        
        # Add detailed error info in development mode only
        if self.debug_mode:
            error_details["exception"] = str(exc)
        
        error_response = self.create_error_response(
            error_message=error_message,
            status_code=status_code,
            error_code=error_code,
            error_category=error_category,
            error_details=error_details,
            request_id=self._get_request_id(request)
        )
        
        return error_response.to_response()
    
    async def handle_not_found_error(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle 404 not found errors."""
        logger.info(f"Resource not found: {request.url.path}")
        
        error_response = self.create_error_response(
            error_message=f"Resource not found: {request.url.path}",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="resource_not_found",
            error_category=ErrorCategory.RESOURCE_NOT_FOUND,
            request_id=self._get_request_id(request)
        )
        
        return error_response.to_response()
    
    async def handle_method_not_allowed(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle 405 method not allowed errors."""
        logger.info(f"Method not allowed: {request.method} {request.url.path}")
        
        error_response = self.create_error_response(
            error_message=f"Method {request.method} not allowed for this endpoint",
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            error_code="method_not_allowed",
            error_category=ErrorCategory.VALIDATION,
            request_id=self._get_request_id(request)
        )
        
        return error_response.to_response()
    
    async def handle_general_exception(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle any unhandled exceptions."""
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc}",
            exc_info=True
        )
        
        # Track in Sentry if available
        if SENTRY_AVAILABLE:
            sentry_sdk.capture_exception(exc)
        
        error_message = "An internal server error occurred"
        error_details = {}
        
        # Add detailed error info in development mode
        if self.debug_mode:
            error_details = {
                "exception": str(exc),
                "traceback": traceback.format_exception(
                    type(exc), exc, exc.__traceback__
                )
            }
        
        error_response = self.create_error_response(
            error_message=error_message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="internal_server_error",
            error_category=ErrorCategory.INTERNAL_SERVER_ERROR,
            error_details=error_details,
            request_id=self._get_request_id(request)
        )
        
        return error_response.to_response()
    
    async def handle_validation_exception(
        self, request: Request, exc: ValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors."""
        logger.warning(f"Pydantic validation error: {exc}")
        
        error_fields = []
        for error in exc.errors():
            location = error.get("loc", [])
            field = ".".join(str(loc) for loc in location) if location else None
            
            error_detail = ErrorDetail(
                message=error.get("msg", "Validation error"),
                code="invalid_field",
                category=ErrorCategory.VALIDATION,
                field=field,
                details={"type": error.get("type", "")}
            )
            
            error_fields.append(error_detail)
        
        error_response = self.create_error_response(
            error_message="Data validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="validation_error",
            error_category=ErrorCategory.VALIDATION,
            error_fields=error_fields,
            request_id=self._get_request_id(request)
        )
        
        return error_response.to_response()
    
    def register_exception_handlers(self, app: FastAPI):
        """Register all exception handlers with the FastAPI app."""
        # FastAPI specific exceptions
        app.exception_handler(RequestValidationError)(self.handle_request_validation_error)
        
        # Database exceptions
        app.exception_handler(SQLAlchemyError)(self.handle_database_error)
        
        # Not found & method not allowed
        app.add_exception_handler(status.HTTP_404_NOT_FOUND, self.handle_not_found_error)
        app.add_exception_handler(status.HTTP_405_METHOD_NOT_ALLOWED, self.handle_method_not_allowed)
        
        # Pydantic validation exceptions
        app.exception_handler(ValidationError)(self.handle_validation_exception)
        
        # General exception handler (catch-all)
        app.exception_handler(Exception)(self.handle_general_exception)


# Global error handler instance
error_handler = ErrorHandler()


def setup_error_handlers(app: FastAPI, debug_mode: bool = False, environment: str = "development"):
    """Set up error handlers for the FastAPI application."""
    error_handler.configure(debug_mode=debug_mode, environment=environment)
    error_handler.register_exception_handlers(app)
    
    logger.info(f"Error handlers configured (debug={debug_mode}, env={environment})")


def create_error_response(
    message: str,
    status_code: int = 400,
    error_code: str = "bad_request",
    category: ErrorCategory = ErrorCategory.VALIDATION,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """
    Create a standard error response.
    
    This is a convenience function that can be used directly in API handlers.
    
    Example:
        @app.get("/users/{user_id}")
        async def get_user(user_id: int):
            user = await get_user_by_id(user_id)
            if not user:
                return create_error_response(
                    message="User not found",
                    status_code=404,
                    error_code="user_not_found",
                    category=ErrorCategory.RESOURCE_NOT_FOUND
                )
            return user
    """
    return error_handler.create_error_response(
        error_message=message,
        status_code=status_code,
        error_code=error_code,
        error_category=category,
        error_details=details
    ).to_response()


# Export for use throughout the application
__all__ = [
    'ErrorCategory',
    'ErrorDetail',
    'ErrorResponse',
    'ErrorHandler',
    'error_handler',
    'setup_error_handlers',
    'create_error_response'
]
