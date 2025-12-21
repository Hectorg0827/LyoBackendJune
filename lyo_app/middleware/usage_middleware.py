import time
import asyncio
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from lyo_app.tenants.usage import log_usage_async

logger = logging.getLogger(__name__)

class UsageMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track API usage per organization.
    
    Intercepts requests and logs them to the database if an organization_id
    is present in the request state (set by authentication dependencies).
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start timer
        start_time = time.time()
        
        # Process request
        try:
            response = await call_next(request)
        except Exception:
            # If application errors, we still want to log it if possible,
            # but usually the error handler returns a response.
            # If exception bubbles up, we re-raise.
            # For accurate duration logging, we rely on standard exception handlers.
            raise
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Check for organization_id in request state
        # Set by api_key_auth.get_api_key_org or jwt_auth dependencies
        organization_id = getattr(request.state, "organization_id", None)
        
        if organization_id:
            # Extract metrics
            tokens_used = getattr(request.state, "tokens_used", 0)
            cost_usd = getattr(request.state, "cost_usd", 0.0)
            api_key_id = getattr(request.state, "api_key_id", None)
            user_id = getattr(request.state, "user_id", None)
            
            # Log usage asynchronously (fire-and-forget)
            # Using create_task to ensure it doesn't block the response
            asyncio.create_task(
                log_usage_async(
                    organization_id=organization_id,
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    latency_ms=duration_ms,
                    tokens_used=tokens_used,
                    cost_usd=cost_usd,
                    api_key_id=api_key_id,
                    user_id=user_id
                )
            )
            
        return response
