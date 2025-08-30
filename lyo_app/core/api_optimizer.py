"""API Optimization and Performance Enhancement System
Response compression, pagination, and API performance optimizations
"""

import gzip
import json
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional, Union, Callable, TypeVar, Generic
from functools import wraps
from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from pydantic.generics import GenericModel

from lyo_app.core.config import settings
from lyo_app.core.cache import get_cache, cached
from lyo_app.core.performance_monitor import get_performance_monitor, monitor_performance

logger = logging.getLogger(__name__)

T = TypeVar('T')

class PaginationParams(BaseModel):
    """Standard pagination parameters"""
    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field(default=None, description="Sort field")
    sort_order: str = Field(default="desc", regex="^(asc|desc)$", description="Sort order")

class PaginatedResponse(GenericModel, Generic[T]):
    """Generic paginated response"""
    data: List[T]
    pagination: Dict[str, Any] = Field(..., description="Pagination metadata")

    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        page: int,
        per_page: int,
        base_url: str = "",
        additional_data: Optional[Dict[str, Any]] = None
    ) -> "PaginatedResponse[T]":
        """Create paginated response with metadata"""
        total_pages = (total + per_page - 1) // per_page

        pagination = {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "next_page": page + 1 if page < total_pages else None,
            "prev_page": page - 1 if page > 1 else None
        }

        # Add navigation URLs if base_url provided
        if base_url:
            if pagination["next_page"]:
                pagination["next_url"] = f"{base_url}?page={pagination['next_page']}&per_page={per_page}"
            if pagination["prev_page"]:
                pagination["prev_url"] = f"{base_url}?page={pagination['prev_page']}&per_page={per_page}"

        if additional_data:
            pagination.update(additional_data)

        return cls(data=items, pagination=pagination)

class CompressedJSONResponse(JSONResponse):
    """JSON response with gzip compression"""

    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: str = None,
        background = None
    ):
        super().__init__(content, status_code, headers, media_type, background)

        # Check if compression should be applied
        if self._should_compress(content):
            self.headers["Content-Encoding"] = "gzip"
            self._compressed = True
        else:
            self._compressed = False

    def _should_compress(self, content: Any) -> bool:
        """Determine if response should be compressed"""
        if not settings.API_COMPRESSION_ENABLED:
            return False

        # Compress if content is large enough
        content_size = len(json.dumps(content).encode('utf-8'))
        return content_size > settings.API_COMPRESSION_MIN_SIZE

    async def __call__(self, scope, receive, send):
        """Override to handle compression"""
        if self._compressed:
            # Compress the body
            body_bytes = json.dumps(self.content, default=str).encode('utf-8')
            compressed_body = gzip.compress(body_bytes)

            # Update content length
            self.headers["Content-Length"] = str(len(compressed_body))
            self.body = compressed_body

        await super().__call__(scope, receive, send)

class APIOptimizer:
    """API performance optimization utilities"""

    def __init__(self):
        self.cache = get_cache()
        self.performance_monitor = get_performance_monitor()
        self.response_cache_ttl = 300  # 5 minutes default

    @staticmethod
    def should_compress_response(request: Request, response_size: int) -> bool:
        """Determine if response should be compressed"""
        # Check client accepts gzip
        accept_encoding = request.headers.get("accept-encoding", "")
        if "gzip" not in accept_encoding:
            return False

        # Check minimum size threshold
        return response_size > getattr(settings, 'API_COMPRESSION_MIN_SIZE', 1024)

    async def optimize_response(
        self,
        request: Request,
        data: Any,
        cache_key: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> Response:
        """Optimize API response with compression and caching"""
        start_time = time.time()

        # Check cache first
        if cache_key:
            cached_response = await self.cache.get(cache_key)
            if cached_response:
                await self.performance_monitor.track_cache_operation("api_response", hit=True)
                return CompressedJSONResponse(cached_response)

        # Create response
        response = CompressedJSONResponse(data)

        # Cache the response if cache key provided
        if cache_key:
            cache_ttl = ttl or self.response_cache_ttl
            await self.cache.set(cache_key, data, cache_ttl)
            await self.performance_monitor.track_cache_operation("api_response", hit=False)

        # Track response time
        response_time = time.time() - start_time
        await self.performance_monitor.track_api_request(
            request.method,
            request.url.path,
            response.status_code,
            response_time
        )

        return response

    async def create_paginated_query(
        self,
        base_query: Any,
        pagination: PaginationParams,
        total_count: int
    ) -> Dict[str, Any]:
        """Create optimized paginated database query"""
        offset = (pagination.page - 1) * pagination.per_page

        # Apply sorting
        if pagination.sort_by:
            sort_column = getattr(base_query.column_descriptions[0]['entity'], pagination.sort_by, None)
            if sort_column is not None:
                if pagination.sort_order == "desc":
                    base_query = base_query.order_by(sort_column.desc())
                else:
                    base_query = base_query.order_by(sort_column.asc())

        # Apply pagination
        paginated_query = base_query.offset(offset).limit(pagination.per_page)

        return {
            "query": paginated_query,
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": total_count,
                "total_pages": (total_count + pagination.per_page - 1) // pagination.per_page
            }
        }

class ResponseOptimizer:
    """Response optimization and formatting utilities"""

    @staticmethod
    def optimize_json_response(data: Any) -> Dict[str, Any]:
        """Optimize JSON response for better performance"""
        if isinstance(data, dict):
            # Remove null values if configured
            if getattr(settings, 'API_REMOVE_NULL_VALUES', False):
                data = {k: v for k, v in data.items() if v is not None}

            # Limit nested object depth
            max_depth = getattr(settings, 'API_MAX_NESTING_DEPTH', 5)
            data = ResponseOptimizer._limit_nesting_depth(data, max_depth)

        return data

    @staticmethod
    def _limit_nesting_depth(obj: Any, max_depth: int, current_depth: int = 0) -> Any:
        """Limit nesting depth of objects"""
        if current_depth >= max_depth:
            if isinstance(obj, (list, tuple)):
                return f"Array with {len(obj)} items"
            elif isinstance(obj, dict):
                return f"Object with {len(obj)} keys"
            else:
                return str(type(obj).__name__)

        if isinstance(obj, dict):
            return {
                k: ResponseOptimizer._limit_nesting_depth(v, max_depth, current_depth + 1)
                for k, v in obj.items()
            }
        elif isinstance(obj, (list, tuple)):
            return [
                ResponseOptimizer._limit_nesting_depth(item, max_depth, current_depth + 1)
                for item in obj
            ]
        else:
            return obj

    @staticmethod
    def create_conditional_response(
        request: Request,
        data: Any,
        etag: Optional[str] = None
    ) -> Response:
        """Create conditional response with ETag support"""
        if etag:
            # Check If-None-Match header
            if_none_match = request.headers.get("if-none-match")
            if if_none_match and if_none_match == etag:
                return Response(status_code=304)  # Not Modified

        response = CompressedJSONResponse(data)
        if etag:
            response.headers["ETag"] = etag

        return response

class StreamingResponseOptimizer:
    """Streaming response optimization for large datasets"""

    @staticmethod
    async def create_streaming_response(
        generator: Callable,
        media_type: str = "application/json",
        chunk_size: int = 8192
    ) -> StreamingResponse:
        """Create optimized streaming response"""

        async def stream_generator():
            async for chunk in generator():
                if isinstance(chunk, (dict, list)):
                    chunk = json.dumps(chunk, default=str).encode('utf-8')
                elif isinstance(chunk, str):
                    chunk = chunk.encode('utf-8')

                # Yield chunk with size optimization
                for i in range(0, len(chunk), chunk_size):
                    yield chunk[i:i + chunk_size]

        return StreamingResponse(
            stream_generator(),
            media_type=media_type,
            headers={"Transfer-Encoding": "chunked"}
        )

class APIEndpointOptimizer:
    """Optimize API endpoints with caching and performance monitoring"""

    def __init__(self):
        self.api_optimizer = APIOptimizer()
        self.response_optimizer = ResponseOptimizer()

    def optimize_endpoint(
        self,
        cache_key_prefix: str = "",
        cache_ttl: int = 300,
        compress: bool = True
    ):
        """Decorator to optimize API endpoints"""
        def decorator(func: Callable):
            @wraps(func)
            @monitor_performance
            async def wrapper(*args, **kwargs):
                # Extract request from args
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

                if not request:
                    # Try to get from kwargs
                    request = kwargs.get('request')

                # Generate cache key
                cache_key = None
                if cache_key_prefix and request:
                    cache_key = f"{cache_key_prefix}:{request.method}:{request.url.path}"

                # Call the original function
                result = await func(*args, **kwargs)

                # Optimize response
                if isinstance(result, dict):
                    optimized_data = self.response_optimizer.optimize_json_response(result)

                    if request and compress:
                        # Create optimized response
                        response = await self.api_optimizer.optimize_response(
                            request,
                            optimized_data,
                            cache_key,
                            cache_ttl
                        )
                        return response
                    else:
                        return CompressedJSONResponse(optimized_data)

                return result

            return wrapper
        return decorator

# Global instances
api_optimizer = APIOptimizer()
response_optimizer = ResponseOptimizer()
endpoint_optimizer = APIEndpointOptimizer()

# Utility functions for common optimizations
def paginate_response(
    items: List[T],
    total: int,
    params: PaginationParams,
    base_url: str = ""
) -> PaginatedResponse[T]:
    """Create paginated response"""
    return PaginatedResponse.create(items, total, params.page, params.per_page, base_url)

async def cached_api_response(
    request: Request,
    data: Any,
    cache_key: str,
    ttl: int = 300
) -> Response:
    """Create cached API response"""
    return await api_optimizer.optimize_response(request, data, cache_key, ttl)

def optimize_database_query(query: Any, pagination: Optional[PaginationParams] = None) -> Any:
    """Optimize database query with pagination and selection"""
    if pagination:
        offset = (pagination.page - 1) * pagination.per_page
        query = query.offset(offset).limit(pagination.per_page)

        if pagination.sort_by:
            # This would need to be implemented based on the specific model
            pass

    return query

# Performance monitoring decorators
def monitor_endpoint(endpoint_name: str):
    """Decorator to monitor endpoint performance"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status_code = 200

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status_code = getattr(e, 'status_code', 500)
                raise
            finally:
                duration = time.time() - start_time
                await get_performance_monitor().track_api_request(
                    "UNKNOWN",  # Would need to extract from request
                    endpoint_name,
                    status_code,
                    duration
                )

        return wrapper
    return decorator

# Configuration defaults
DEFAULT_API_CONFIG = {
    "compression_enabled": True,
    "compression_min_size": 1024,  # 1KB
    "max_nesting_depth": 5,
    "remove_null_values": False,
    "default_page_size": 20,
    "max_page_size": 100,
    "cache_ttl": 300
}

# Initialize API optimization settings
def initialize_api_optimization():
    """Initialize API optimization system"""
    # Set default configuration if not already set
    for key, value in DEFAULT_API_CONFIG.items():
        config_key = f"API_{key.upper()}"
        if not hasattr(settings, config_key):
            setattr(settings, config_key, value)

    logger.info("API optimization system initialized")

# Health check for API optimization
async def get_api_optimization_health() -> Dict[str, Any]:
    """Get API optimization system health status"""
    cache_stats = api_optimizer.cache.get_stats()

    return {
        "status": "healthy",
        "cache_stats": cache_stats,
        "compression_enabled": getattr(settings, 'API_COMPRESSION_ENABLED', True),
        "timestamp": time.time()
    }
