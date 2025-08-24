"""RFC 9457 Problem Details error handling for HTTP APIs."""

import traceback
from typing import Any, Dict, Optional, Type
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

logger = logging.getLogger(__name__)


class ProblemDetail(Exception):
    """Base exception for RFC 9457 Problem Details."""
    
    def __init__(
        self,
        *,
        type_: str,
        title: str,
        status: int,
        detail: str,
        instance: Optional[str] = None,
        **extensions: Any
    ):
        self.type = type_
        self.title = title
        self.status = status
        self.detail = detail
        self.instance = instance
        self.extensions = extensions
        super().__init__(detail)


class ValidationProblem(ProblemDetail):
    """RFC 9457 Problem for validation errors."""
    
    def __init__(self, detail: str, instance: Optional[str] = None, **extensions):
        super().__init__(
            type_="https://api.lyo.app/problems/validation-error",
            title="Validation Error",
            status=400,
            detail=detail,
            instance=instance,
            **extensions
        )


class AuthenticationProblem(ProblemDetail):
    """RFC 9457 Problem for authentication errors."""
    
    def __init__(self, detail: str = "Authentication required", instance: Optional[str] = None):
        super().__init__(
            type_="https://api.lyo.app/problems/authentication-required",
            title="Authentication Required", 
            status=401,
            detail=detail,
            instance=instance
        )


class AuthorizationProblem(ProblemDetail):
    """RFC 9457 Problem for authorization errors."""
    
    def __init__(self, detail: str = "Access denied", instance: Optional[str] = None):
        super().__init__(
            type_="https://api.lyo.app/problems/access-denied",
            title="Access Denied",
            status=403,
            detail=detail,
            instance=instance
        )


class ResourceNotFoundProblem(ProblemDetail):
    """RFC 9457 Problem for resource not found."""
    
    def __init__(self, resource_type: str, resource_id: str, instance: Optional[str] = None):
        super().__init__(
            type_="https://api.lyo.app/problems/resource-not-found",
            title="Resource Not Found",
            status=404,
            detail=f"{resource_type} with id '{resource_id}' not found",
            instance=instance,
            resourceType=resource_type,
            resourceId=resource_id
        )


class ConflictProblem(ProblemDetail):
    """RFC 9457 Problem for conflict errors."""
    
    def __init__(self, detail: str, instance: Optional[str] = None, **extensions):
        super().__init__(
            type_="https://api.lyo.app/problems/conflict",
            title="Conflict",
            status=409,
            detail=detail,
            instance=instance,
            **extensions
        )


class RateLimitProblem(ProblemDetail):
    """RFC 9457 Problem for rate limiting."""
    
    def __init__(self, retry_after: int, instance: Optional[str] = None):
        super().__init__(
            type_="https://api.lyo.app/problems/rate-limit-exceeded",
            title="Rate Limit Exceeded",
            status=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds",
            instance=instance,
            retryAfter=retry_after
        )


class ServerProblem(ProblemDetail):
    """RFC 9457 Problem for server errors."""
    
    def __init__(self, detail: str = "Internal server error", instance: Optional[str] = None):
        super().__init__(
            type_="https://api.lyo.app/problems/server-error",
            title="Internal Server Error",
            status=500,
            detail=detail,
            instance=instance
        )


class ModelNotAvailableProblem(ProblemDetail):
    """RFC 9457 Problem for model availability issues."""
    
    def __init__(self, model_name: str, instance: Optional[str] = None):
        super().__init__(
            type_="https://api.lyo.app/problems/model-unavailable",
            title="AI Model Unavailable",
            status=503,
            detail=f"AI model '{model_name}' is not available. Please try again later.",
            instance=instance,
            modelName=model_name
        )


def create_problem_response(problem: ProblemDetail, request: Request) -> JSONResponse:
    """Create a JSONResponse from a ProblemDetail."""
    content = {
        "type": problem.type,
        "title": problem.title,
        "status": problem.status,
        "detail": problem.detail,
        "instance": problem.instance or str(request.url)
    }
    
    # Add extensions
    content.update(problem.extensions)
    
    return JSONResponse(
        status_code=problem.status,
        content=content,
        headers={"Content-Type": "application/problem+json"}
    )


def map_exception_to_problem(exc: Exception, request: Request) -> ProblemDetail:
    """Map common exceptions to ProblemDetail instances."""
    instance = str(request.url)
    
    if isinstance(exc, ProblemDetail):
        return exc
        
    elif isinstance(exc, HTTPException):
        return ProblemDetail(
            type_=f"https://api.lyo.app/problems/http-{exc.status_code}",
            title=exc.detail,
            status=exc.status_code,
            detail=exc.detail,
            instance=instance
        )
        
    elif isinstance(exc, StarletteHTTPException):
        return ProblemDetail(
            type_=f"https://api.lyo.app/problems/http-{exc.status_code}",
            title="HTTP Error",
            status=exc.status_code,
            detail=exc.detail,
            instance=instance
        )
        
    elif isinstance(exc, RequestValidationError):
        errors = []
        for error in exc.errors():
            loc = " -> ".join(str(x) for x in error["loc"]) 
            errors.append(f"{loc}: {error['msg']}")
        
        return ValidationProblem(
            detail="Validation failed: " + "; ".join(errors),
            instance=instance,
            validationErrors=exc.errors()
        )
        
    elif isinstance(exc, ValueError):
        return ValidationProblem(
            detail=str(exc),
            instance=instance
        )
        
    elif isinstance(exc, PermissionError):
        return AuthorizationProblem(
            detail=str(exc),
            instance=instance
        )
        
    else:
        # Log the full traceback for debugging
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        
        return ServerProblem(
            detail="An unexpected error occurred",
            instance=instance
        )


async def problem_details_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler that returns RFC 9457 Problem Details responses.
    
    This handler catches all exceptions and converts them to standardized
    Problem Details responses as per RFC 9457.
    """
    problem = map_exception_to_problem(exc, request)
    
    # Log errors appropriately
    if problem.status >= 500:
        logger.error(
            f"Server error: {problem.title} - {problem.detail}",
            extra={
                "url": str(request.url),
                "method": request.method,
                "status": problem.status,
                "type": problem.type
            }
        )
    elif problem.status >= 400:
        logger.warning(
            f"Client error: {problem.title} - {problem.detail}",
            extra={
                "url": str(request.url),
                "method": request.method, 
                "status": problem.status,
                "type": problem.type
            }
        )
    
    return create_problem_response(problem, request)
