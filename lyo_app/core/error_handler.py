"""Enhanced Error Handling and Response System
Comprehensive error management with structured logging and user-friendly responses
"""

import json
import logging
import traceback
from typing import Dict, Any, Optional, Union, List
from datetime import datetime
from enum import Enum
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

from lyo_app.core.config import settings
from lyo_app.core.performance_monitor import get_performance_monitor

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Use structlog for structured logging if available
try:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logger = structlog.get_logger()
except ImportError:
    # Fallback to standard logging
    logger = logging.getLogger(__name__)

class ErrorCode(Enum):
    """Standardized error codes for consistent error handling"""

    # Authentication & Authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"

    # Resource Errors
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFLICT = "CONFLICT"

    # System Errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Business Logic Errors
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"

class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class LyoException(Exception):
    """Custom exception class for LyoBackend"""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        status_code: int = 500,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.severity = severity
        self.details = details or {}
        self.user_message = user_message or message
        self.timestamp = datetime.utcnow()

class ErrorResponse(BaseModel):
    """Standardized error response model"""
    success: bool = False
    error: Dict[str, Any]
    timestamp: str
    request_id: Optional[str] = None

    @classmethod
    def from_exception(
        cls,
        exception: LyoException,
        request_id: Optional[str] = None
    ) -> "ErrorResponse":
        """Create error response from LyoException"""
        return cls(
            error={
                "code": exception.error_code.value,
                "message": exception.user_message,
                "details": exception.details
            },
            timestamp=exception.timestamp.isoformat(),
            request_id=request_id
        )

class ErrorHandler:
    """Centralized error handling system"""

    def __init__(self):
        self.performance_monitor = get_performance_monitor()
        self.error_counts = {}
        self._error_cleanup_task = None

    async def handle_exception(
        self,
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """Handle exceptions and return appropriate JSON response"""

        # Generate request ID for tracking
        request_id = getattr(request.state, 'request_id', None) or str(datetime.utcnow().timestamp())

        # Log the error with structured data
        await self._log_error(request, exc, request_id)

        # Track error metrics
        await self._track_error_metrics(exc)

        # Convert to LyoException if not already
        if isinstance(exc, LyoException):
            lyo_exc = exc
        else:
            lyo_exc = self._convert_to_lyo_exception(exc)

        # Create error response
        error_response = ErrorResponse.from_exception(lyo_exc, request_id)

        return JSONResponse(
            status_code=lyo_exc.status_code,
            content=error_response.dict()
        )

    def _convert_to_lyo_exception(self, exc: Exception) -> LyoException:
        """Convert standard exceptions to LyoException"""

        if isinstance(exc, HTTPException):
            # Convert FastAPI HTTPException
            error_code = self._map_http_status_to_error_code(exc.status_code)
            return LyoException(
                message=str(exc.detail),
                error_code=error_code,
                status_code=exc.status_code,
                severity=ErrorSeverity.MEDIUM
            )

        # Handle database errors
        if "database" in str(type(exc)).lower() or "sql" in str(type(exc)).lower():
            return LyoException(
                message="Database operation failed",
                error_code=ErrorCode.DATABASE_ERROR,
                status_code=500,
                severity=ErrorSeverity.HIGH,
                details={"original_error": str(exc)},
                user_message="A database error occurred. Please try again later."
            )

        # Handle validation errors
        if "validation" in str(type(exc)).lower():
            return LyoException(
                message="Input validation failed",
                error_code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
                severity=ErrorSeverity.LOW,
                details={"original_error": str(exc)}
            )

        # Default internal server error
        return LyoException(
            message="An unexpected error occurred",
            error_code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            details={
                "original_error": str(exc),
                "traceback": traceback.format_exc()
            },
            user_message="Something went wrong. Please try again later."
        )

    def _map_http_status_to_error_code(self, status_code: int) -> ErrorCode:
        """Map HTTP status codes to error codes"""
        mapping = {
            400: ErrorCode.VALIDATION_ERROR,
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            409: ErrorCode.CONFLICT,
            429: ErrorCode.RATE_LIMIT_EXCEEDED,
            500: ErrorCode.INTERNAL_ERROR
        }
        return mapping.get(status_code, ErrorCode.INTERNAL_ERROR)

    async def _log_error(
        self,
        request: Request,
        exc: Exception,
        request_id: str
    ):
        """Log error with structured data"""
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "user_agent": request.headers.get("user-agent"),
            "client_ip": self._get_client_ip(request),
            "timestamp": datetime.utcnow().isoformat(),
            "error_type": type(exc).__name__,
            "error_message": str(exc)
        }

        if isinstance(exc, LyoException):
            log_data.update({
                "error_code": exc.error_code.value,
                "severity": exc.severity.value,
                "status_code": exc.status_code,
                "details": exc.details
            })

        # Add traceback for server errors
        if hasattr(exc, '__traceback__'):
            log_data["traceback"] = traceback.format_exc()

        # Log with appropriate level based on severity
        if isinstance(exc, LyoException):
            if exc.severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]:
                logger.error("Critical error occurred", **log_data)
            elif exc.severity == ErrorSeverity.MEDIUM:
                logger.warning("Error occurred", **log_data)
            else:
                logger.info("Minor error occurred", **log_data)
        else:
            logger.error("Unhandled exception", **log_data)

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request"""
        # Check for forwarded headers
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fallback to client host
        return getattr(request.client, 'host', 'unknown')

    async def _track_error_metrics(self, exc: Exception):
        """Track error metrics for monitoring"""
        error_type = type(exc).__name__

        if error_type not in self.error_counts:
            self.error_counts[error_type] = 0
        self.error_counts[error_type] += 1

        # Track in performance monitor
        await self.performance_monitor.track_business_metric("error_occurred")

        # Clean up old error counts periodically
        if not self._error_cleanup_task:
            self._error_cleanup_task = asyncio.create_task(self._cleanup_error_counts())

    async def _cleanup_error_counts(self):
        """Clean up old error counts to prevent memory leaks"""
        while True:
            await asyncio.sleep(3600)  # Clean up every hour
            # Reset counts older than 24 hours (simplified)
            self.error_counts.clear()

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics for monitoring"""
        return {
            "error_counts": self.error_counts.copy(),
            "total_errors": sum(self.error_counts.values()),
            "unique_error_types": len(self.error_counts)
        }

class ValidationErrorHandler:
    """Handle Pydantic validation errors with detailed feedback"""

    @staticmethod
    def format_validation_errors(errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format Pydantic validation errors into user-friendly format"""
        formatted_errors = {}

        for error in errors:
            field = error.get('loc', ['unknown'])[-1]
            message = error.get('msg', 'Validation error')

            if field not in formatted_errors:
                formatted_errors[field] = []

            formatted_errors[field].append({
                "message": message,
                "type": error.get('type', 'unknown'),
                "context": error.get('ctx', {})
            })

        return {
            "validation_errors": formatted_errors,
            "total_errors": len(errors)
        }

class RateLimitHandler:
    """Handle rate limiting with proper error responses"""

    def __init__(self):
        self.rate_limits = {}

    async def check_rate_limit(
        self,
        request: Request,
        limit: int = 100,
        window_seconds: int = 60
    ) -> bool:
        """Check if request exceeds rate limit"""
        client_ip = self._get_client_ip(request)
        current_time = datetime.utcnow().timestamp()

        if client_ip not in self.rate_limits:
            self.rate_limits[client_ip] = []

        # Clean old requests
        self.rate_limits[client_ip] = [
            req_time for req_time in self.rate_limits[client_ip]
            if current_time - req_time < window_seconds
        ]

        # Check limit
        if len(self.rate_limits[client_ip]) >= limit:
            return False

        # Add current request
        self.rate_limits[client_ip].append(current_time)
        return True

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP for rate limiting"""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return getattr(request.client, 'host', 'unknown')

    def get_rate_limit_error(self) -> LyoException:
        """Get rate limit exceeded error"""
        return LyoException(
            message="Rate limit exceeded",
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=429,
            severity=ErrorSeverity.MEDIUM,
            user_message="Too many requests. Please slow down and try again later."
        )

# Global error handler instance
error_handler = ErrorHandler()
rate_limiter = RateLimitHandler()

# Middleware functions
async def error_handling_middleware(request: Request, call_next):
    """FastAPI middleware for centralized error handling"""
    try:
        # Check rate limit
        if not await rate_limiter.check_rate_limit(request):
            raise rate_limiter.get_rate_limit_error()

        response = await call_next(request)
        return response

    except Exception as exc:
        return await error_handler.handle_exception(request, exc)

async def request_id_middleware(request: Request, call_next):
    """Middleware to add request ID to all requests"""
    request_id = str(datetime.utcnow().timestamp())
    request.state.request_id = request_id

    response = await call_next(request)

    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id
    return response

# Utility functions for raising common errors
def raise_not_found(resource: str, resource_id: Optional[str] = None) -> None:
    """Raise not found error"""
    message = f"{resource} not found"
    if resource_id:
        message += f" with ID {resource_id}"

    raise LyoException(
        message=message,
        error_code=ErrorCode.NOT_FOUND,
        status_code=404,
        severity=ErrorSeverity.LOW
    )

def raise_validation_error(details: Dict[str, Any]) -> None:
    """Raise validation error"""
    raise LyoException(
        message="Validation failed",
        error_code=ErrorCode.VALIDATION_ERROR,
        status_code=400,
        severity=ErrorSeverity.LOW,
        details=details
    )

def raise_unauthorized(message: str = "Authentication required") -> None:
    """Raise unauthorized error"""
    raise LyoException(
        message=message,
        error_code=ErrorCode.UNAUTHORIZED,
        status_code=401,
        severity=ErrorSeverity.MEDIUM
    )

def raise_forbidden(message: str = "Insufficient permissions") -> None:
    """Raise forbidden error"""
    raise LyoException(
        message=message,
        error_code=ErrorCode.FORBIDDEN,
        status_code=403,
        severity=ErrorSeverity.MEDIUM
    )

def raise_conflict(message: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Raise conflict error"""
    raise LyoException(
        message=message,
        error_code=ErrorCode.CONFLICT,
        status_code=409,
        severity=ErrorSeverity.MEDIUM,
        details=details
    )

# Health check endpoint data
async def get_error_health_status() -> Dict[str, Any]:
    """Get error handling system health status"""
    stats = error_handler.get_error_statistics()

    return {
        "status": "healthy" if stats["total_errors"] < 100 else "warning",
        "error_statistics": stats,
        "rate_limiter_active": True,
        "timestamp": datetime.utcnow().isoformat()
    }
