"""
Enhanced Error Handling System
Provides structured error responses, logging, and user-friendly messages.
"""

import logging
import traceback
from typing import Dict, Any, Optional, Union
from enum import Enum
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import time

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of errors for better classification and handling."""
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATABASE = "database"
    EXTERNAL_API = "external_api"
    BUSINESS_LOGIC = "business_logic"
    SYSTEM = "system"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"


class ErrorCode(Enum):
    """Standardized error codes for consistent API responses."""

    # Authentication & Authorization (1000-1999)
    INVALID_CREDENTIALS = ("1001", "Invalid username or password")
    TOKEN_EXPIRED = ("1002", "Authentication token has expired")
    TOKEN_INVALID = ("1003", "Invalid authentication token")
    INSUFFICIENT_PERMISSIONS = ("1004", "Insufficient permissions for this action")
    ACCOUNT_DISABLED = ("1005", "Account has been disabled")
    ACCOUNT_NOT_VERIFIED = ("1006", "Account email not verified")

    # Validation (2000-2999)
    MISSING_REQUIRED_FIELD = ("2001", "Required field is missing")
    INVALID_FORMAT = ("2002", "Invalid data format")
    VALUE_OUT_OF_RANGE = ("2003", "Value is outside acceptable range")
    DUPLICATE_VALUE = ("2004", "Value already exists")
    INVALID_REFERENCE = ("2005", "Referenced resource does not exist")

    # Database (3000-3999)
    CONNECTION_ERROR = ("3001", "Database connection failed")
    QUERY_ERROR = ("3002", "Database query failed")
    CONSTRAINT_VIOLATION = ("3003", "Database constraint violated")
    DEADLOCK_ERROR = ("3004", "Database deadlock detected")

    # Business Logic (4000-4999)
    RESOURCE_NOT_FOUND = ("4001", "Requested resource not found")
    RESOURCE_ALREADY_EXISTS = ("4002", "Resource already exists")
    OPERATION_NOT_ALLOWED = ("4003", "Operation not allowed in current state")
    QUOTA_EXCEEDED = ("4004", "Usage quota exceeded")
    FEATURE_DISABLED = ("4005", "Feature is currently disabled")

    # External Services (5000-5999)
    EXTERNAL_API_ERROR = ("5001", "External service error")
    EXTERNAL_API_TIMEOUT = ("5002", "External service timeout")
    EXTERNAL_API_RATE_LIMIT = ("5003", "External service rate limit exceeded")

    # System (6000-6999)
    INTERNAL_ERROR = ("6001", "Internal server error")
    CONFIGURATION_ERROR = ("6002", "Configuration error")
    SERVICE_UNAVAILABLE = ("6003", "Service temporarily unavailable")

    def __init__(self, code: str, message: str):
        self.code = code
        self.default_message = message


class ErrorResponse(BaseModel):
    """Standardized error response model."""
    success: bool = False
    error: Dict[str, Any]
    timestamp: float
    request_id: Optional[str] = None

    class Config:
        json_encoders = {
            float: lambda v: round(v, 3)
        }


class ErrorDetail(BaseModel):
    """Detailed error information."""
    code: str
    message: str
    category: str
    details: Optional[Dict[str, Any]] = None
    field: Optional[str] = None


class EnhancedErrorHandler:
    """Enhanced error handler with structured logging and user-friendly responses."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def handle_error(
        self,
        error: Exception,
        request: Optional[Request] = None,
        user_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """
        Handle and format errors with appropriate HTTP status codes and user-friendly messages.

        Args:
            error: The exception that occurred
            request: FastAPI request object for context
            user_id: User ID for logging context
            additional_context: Additional context for error handling

        Returns:
            JSONResponse with standardized error format
        """

        # Classify the error
        error_info = self._classify_error(error)

        # Log the error with context
        await self._log_error(
            error=error,
            error_info=error_info,
            request=request,
            user_id=user_id,
            additional_context=additional_context
        )

        # Create user-friendly response
        response_data = ErrorResponse(
            error={
                "code": error_info["code"],
                "message": error_info["user_message"],
                "category": error_info["category"].value,
                "details": error_info.get("details", {}),
                "field": error_info.get("field")
            },
            timestamp=time.time(),
            request_id=getattr(request.state, 'request_id', None) if request else None
        )

        return JSONResponse(
            status_code=error_info["status_code"],
            content=response_data.dict()
        )

    def _classify_error(self, error: Exception) -> Dict[str, Any]:
        """Classify error and determine appropriate response."""

        # HTTP Exceptions (preserve original status and message)
        if isinstance(error, HTTPException):
            return {
                "code": "HTTP_EXCEPTION",
                "user_message": error.detail,
                "status_code": error.status_code,
                "category": ErrorCategory.SYSTEM,
                "details": {}
            }

        # Database errors
        error_str = str(error).lower()
        if any(keyword in error_str for keyword in ["connection", "pool", "timeout"]):
            return {
                "code": ErrorCode.CONNECTION_ERROR.code,
                "user_message": "Database temporarily unavailable. Please try again.",
                "status_code": 503,
                "category": ErrorCategory.DATABASE,
                "details": {"original_error": str(error)}
            }

        if "unique constraint" in error_str or "duplicate key" in error_str:
            return {
                "code": ErrorCode.DUPLICATE_VALUE.code,
                "user_message": "This item already exists.",
                "status_code": 409,
                "category": ErrorCategory.VALIDATION,
                "details": {"original_error": str(error)}
            }

        # Authentication errors
        if "invalid credentials" in error_str or "wrong password" in error_str:
            return {
                "code": ErrorCode.INVALID_CREDENTIALS.code,
                "user_message": "Invalid email or password.",
                "status_code": 401,
                "category": ErrorCategory.AUTHENTICATION,
                "details": {}
            }

        if "token expired" in error_str:
            return {
                "code": ErrorCode.TOKEN_EXPIRED.code,
                "user_message": "Your session has expired. Please log in again.",
                "status_code": 401,
                "category": ErrorCategory.AUTHENTICATION,
                "details": {}
            }

        # Validation errors
        if "validation" in error_str or "pydantic" in error_str:
            return {
                "code": ErrorCode.INVALID_FORMAT.code,
                "user_message": "Please check your input data and try again.",
                "status_code": 422,
                "category": ErrorCategory.VALIDATION,
                "details": {"original_error": str(error)}
            }

        # External API errors
        if any(keyword in error_str for keyword in ["api", "external", "timeout", "rate limit"]):
            return {
                "code": ErrorCode.EXTERNAL_API_ERROR.code,
                "user_message": "Service temporarily unavailable. Please try again later.",
                "status_code": 503,
                "category": ErrorCategory.EXTERNAL_API,
                "details": {"original_error": str(error)}
            }

        # Default to internal server error
        return {
            "code": ErrorCode.INTERNAL_ERROR.code,
            "user_message": "Something went wrong. Please try again later.",
            "status_code": 500,
            "category": ErrorCategory.SYSTEM,
            "details": {"original_error": str(error)}
        }

    async def _log_error(
        self,
        error: Exception,
        error_info: Dict[str, Any],
        request: Optional[Request] = None,
        user_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ):
        """Log error with structured context."""

        # Build log context
        log_context = {
            "error_code": error_info["code"],
            "error_category": error_info["category"].value,
            "status_code": error_info["status_code"],
            "user_message": error_info["user_message"],
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc()
        }

        if user_id:
            log_context["user_id"] = user_id

        if request:
            log_context.update({
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "client_ip": getattr(request.client, 'host', None) if request.client else None
            })

        if additional_context:
            log_context.update(additional_context)

        # Log based on severity
        if error_info["status_code"] >= 500:
            self.logger.error("Server Error", extra=log_context)
        elif error_info["status_code"] >= 400:
            self.logger.warning("Client Error", extra=log_context)
        else:
            self.logger.info("Handled Error", extra=log_context)


class BusinessLogicError(Exception):
    """Custom exception for business logic errors."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
        field: Optional[str] = None
    ):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        self.field = field


class ValidationError(BusinessLogicError):
    """Custom exception for validation errors."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=ErrorCode.INVALID_FORMAT,
            status_code=422,
            details=details,
            field=field
        )


class NotFoundError(BusinessLogicError):
    """Custom exception for resource not found errors."""

    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"{resource_type} not found"
        if resource_id:
            message += f" with ID {resource_id}"

        super().__init__(
            message=message,
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            details=details
        )


class PermissionError(BusinessLogicError):
    """Custom exception for permission errors."""

    def __init__(
        self,
        message: str = "You don't have permission to perform this action",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=ErrorCode.INSUFFICIENT_PERMISSIONS,
            status_code=403,
            details=details
        )


# Global error handler instance
enhanced_error_handler = EnhancedErrorHandler()


def create_error_response(
    error_code: ErrorCode,
    message: Optional[str] = None,
    status_code: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    field: Optional[str] = None,
    request_id: Optional[str] = None
) -> JSONResponse:
    """Create a standardized error response."""

    response_data = ErrorResponse(
        error={
            "code": error_code.code,
            "message": message or error_code.default_message,
            "category": ErrorCategory.SYSTEM.value,  # Default category
            "details": details or {},
            "field": field
        },
        timestamp=time.time(),
        request_id=request_id
    )

    return JSONResponse(
        status_code=status_code or 400,
        content=response_data.dict()
    )
