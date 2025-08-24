"""
Global error handling with Problem Details (RFC 7807) support.
Provides consistent error responses across all API endpoints.
"""

import logging
from typing import Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ProblemDetailsException(HTTPException):
    """Custom exception that supports Problem Details format."""
    
    def __init__(
        self,
        status_code: int,
        title: str,
        detail: str,
        type_uri: str = None,
        instance: str = None,
        **kwargs
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.title = title
        self.type_uri = type_uri or f"https://api.lyo.app/problems/{self.__class__.__name__}"
        self.instance = instance
        self.extensions = kwargs


class ValidationError(ProblemDetailsException):
    """Validation error with Problem Details format."""
    
    def __init__(self, detail: str, instance: str = None):
        super().__init__(
            status_code=422,
            title="Validation Error",
            detail=detail,
            type_uri="https://api.lyo.app/problems/ValidationError",
            instance=instance
        )


class AuthenticationError(ProblemDetailsException):
    """Authentication error with Problem Details format."""
    
    def __init__(self, detail: str = "Authentication required", instance: str = None):
        super().__init__(
            status_code=401,
            title="Authentication Error",
            detail=detail,
            type_uri="https://api.lyo.app/problems/AuthenticationError",
            instance=instance
        )


class AuthorizationError(ProblemDetailsException):
    """Authorization error with Problem Details format."""
    
    def __init__(self, detail: str = "Insufficient permissions", instance: str = None):
        super().__init__(
            status_code=403,
            title="Authorization Error",
            detail=detail,
            type_uri="https://api.lyo.app/problems/AuthorizationError",
            instance=instance
        )


class NotFoundError(ProblemDetailsException):
    """Not found error with Problem Details format."""
    
    def __init__(self, detail: str = "Resource not found", instance: str = None):
        super().__init__(
            status_code=404,
            title="Not Found",
            detail=detail,
            type_uri="https://api.lyo.app/problems/NotFoundError",
            instance=instance
        )


class ConflictError(ProblemDetailsException):
    """Conflict error with Problem Details format."""
    
    def __init__(self, detail: str = "Resource conflict", instance: str = None):
        super().__init__(
            status_code=409,
            title="Conflict",
            detail=detail,
            type_uri="https://api.lyo.app/problems/ConflictError",
            instance=instance
        )


class RateLimitError(ProblemDetailsException):
    """Rate limit error with Problem Details format."""
    
    def __init__(self, detail: str = "Rate limit exceeded", instance: str = None):
        super().__init__(
            status_code=429,
            title="Rate Limit Exceeded",
            detail=detail,
            type_uri="https://api.lyo.app/problems/RateLimitError",
            instance=instance
        )


def create_problem_details_response(
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    type_uri: str = None,
    instance: str = None,
    **extensions
) -> JSONResponse:
    """Create a Problem Details JSON response."""
    
    problem = {
        "type": type_uri or f"https://api.lyo.app/problems/{title.replace(' ', '')}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance or str(request.url)
    }
    
    # Add any extensions
    problem.update(extensions)
    
    return JSONResponse(
        status_code=status_code,
        content=problem,
        headers={"content-type": "application/problem+json"}
    )


async def problem_details_exception_handler(request: Request, exc: ProblemDetailsException) -> JSONResponse:
    """Handle ProblemDetailsException with proper formatting."""
    
    return create_problem_details_response(
        request=request,
        status_code=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        type_uri=exc.type_uri,
        instance=exc.instance,
        **exc.extensions
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle general HTTP exceptions with Problem Details format."""
    
    # Map HTTP status codes to appropriate titles
    titles = {
        400: "Bad Request",
        401: "Unauthorized", 
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable"
    }
    
    return create_problem_details_response(
        request=request,
        status_code=exc.status_code,
        title=titles.get(exc.status_code, "HTTP Error"),
        detail=str(exc.detail)
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors with Problem Details format."""
    
    # Format validation errors nicely
    errors = []
    for error in exc.errors():
        field = " -> ".join([str(x) for x in error["loc"]])
        errors.append(f"{field}: {error['msg']}")
    
    detail = "Validation failed: " + "; ".join(errors)
    
    return create_problem_details_response(
        request=request,
        status_code=422,
        title="Validation Error",
        detail=detail,
        type_uri="https://api.lyo.app/problems/ValidationError",
        errors=exc.errors()
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with Problem Details format."""
    
    logger.exception("Unhandled exception occurred")
    
    # Don't expose internal error details in production
    detail = "An unexpected error occurred"
    if hasattr(request.app.state, "settings"):
        if getattr(request.app.state.settings, "DEBUG", False):
            detail = f"Internal server error: {str(exc)}"
    
    return create_problem_details_response(
        request=request,
        status_code=500,
        title="Internal Server Error",
        detail=detail,
        type_uri="https://api.lyo.app/problems/InternalServerError"
    )


def setup_error_handlers(app) -> None:
    """Set up all error handlers on the FastAPI app."""
    
    app.add_exception_handler(ProblemDetailsException, problem_details_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("Error handlers configured with Problem Details support")
