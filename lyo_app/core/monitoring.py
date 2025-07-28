"""
Performance monitoring and metrics collection for LyoApp backend.
Provides request tracking, API usage monitoring, and performance analytics.
"""

import time
import logging
import structlog
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from lyo_app.core.config import settings

# Configure structured logging
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
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Prometheus metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=(.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0, float("inf"))
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'Number of HTTP requests currently being processed'
)

# External API metrics
external_api_calls_total = Counter(
    'external_api_calls_total',
    'Total external API calls',
    ['service', 'endpoint', 'status']
)

external_api_duration_seconds = Histogram(
    'external_api_duration_seconds',
    'External API call duration in seconds',
    ['service', 'endpoint'],
    buckets=(.1, .25, .5, 1.0, 2.5, 5.0, 10.0, 30.0, float("inf"))
)

# Database metrics
database_queries_total = Counter(
    'database_queries_total',
    'Total database queries',
    ['operation', 'table']
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query duration in seconds',
    ['operation', 'table'],
    buckets=(.001, .005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0, float("inf"))
)

# Application metrics
active_users = Gauge(
    'active_users_total',
    'Number of active users'
)

cache_operations_total = Counter(
    'cache_operations_total',
    'Total cache operations',
    ['operation', 'result']
)

# API quota metrics
api_quota_usage = Gauge(
    'api_quota_usage',
    'API quota usage percentage',
    ['service']
)

# Error metrics
errors_total = Counter(
    'errors_total',
    'Total errors',
    ['error_type', 'endpoint']
)


class PerformanceMonitor:
    """Performance monitoring and metrics collection."""
    
    def __init__(self):
        self.request_stats = {}
        self.api_stats = {}
        
    async def track_request(self, request: Request, call_next):
        """Track HTTP request performance."""
        start_time = time.time()
        request_id = str(uuid4())
        
        # Add request ID to request state
        request.state.request_id = request_id
        
        # Extract endpoint pattern
        endpoint = self._get_endpoint_pattern(request)
        
        # Increment in-progress counter
        http_requests_in_progress.inc()
        
        # Log request start
        logger.info(
            "request_started",
            request_id=request_id,
            method=request.method,
            endpoint=endpoint,
            client_ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown")
        )
        
        try:
            # Process request
            response = await call_next(request)
            status_code = response.status_code
            
        except Exception as e:
            # Track error
            errors_total.labels(
                error_type=e.__class__.__name__,
                endpoint=endpoint
            ).inc()
            
            logger.error(
                "request_error",
                request_id=request_id,
                error=str(e),
                error_type=e.__class__.__name__
            )
            raise
            
        finally:
            # Calculate duration
            duration = time.time() - start_time
            
            # Update metrics
            http_requests_total.labels(
                method=request.method,
                endpoint=endpoint,
                status_code=getattr(response, 'status_code', 500)
            ).inc()
            
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=endpoint
            ).observe(duration)
            
            http_requests_in_progress.dec()
            
            # Log request completion
            logger.info(
                "request_completed",
                request_id=request_id,
                duration_seconds=duration,
                status_code=getattr(response, 'status_code', 500),
                response_size_bytes=getattr(response, 'content_length', 0)
            )
        
        return response
    
    def track_external_api_call(self, service: str, endpoint: str, duration: float, status: str):
        """Track external API call metrics."""
        external_api_calls_total.labels(
            service=service,
            endpoint=endpoint,
            status=status
        ).inc()
        
        external_api_duration_seconds.labels(
            service=service,
            endpoint=endpoint
        ).observe(duration)
    
    def track_database_query(self, operation: str, table: str, duration: float):
        """Track database query metrics."""
        database_queries_total.labels(
            operation=operation,
            table=table
        ).inc()
        
        database_query_duration_seconds.labels(
            operation=operation,
            table=table
        ).observe(duration)
    
    def track_cache_operation(self, operation: str, result: str):
        """Track cache operation metrics."""
        cache_operations_total.labels(
            operation=operation,
            result=result
        ).inc()
    
    def update_api_quota_usage(self, service: str, usage_percentage: float):
        """Update API quota usage metrics."""
        api_quota_usage.labels(service=service).set(usage_percentage)
    
    def update_active_users(self, count: int):
        """Update active users count."""
        active_users.set(count)
    
    def _get_endpoint_pattern(self, request: Request) -> str:
        """Extract endpoint pattern from request."""
        path = request.url.path
        
        # Replace common ID patterns with placeholders
        import re
        path = re.sub(r'/\d+', '/{id}', path)
        path = re.sub(r'/[a-f0-9-]{36}', '/{uuid}', path)
        path = re.sub(r'/[a-f0-9]{24}', '/{objectid}', path)
        
        return path
    
    def get_metrics_data(self) -> str:
        """Get Prometheus metrics data."""
        return generate_latest()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get application health status."""
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": settings.app_version,
            "environment": settings.environment,
            "metrics": {
                "requests_in_progress": http_requests_in_progress._value.get(),
                "total_requests": sum(
                    metric.samples[0].value 
                    for metric in http_requests_total.collect()
                    for sample in metric.samples
                ),
                "uptime_seconds": time.time() - self._start_time if hasattr(self, '_start_time') else 0
            }
        }


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


async def performance_middleware(request: Request, call_next):
    """FastAPI middleware for performance monitoring."""
    return await performance_monitor.track_request(request, call_next)


@asynccontextmanager
async def track_external_api_call(service: str, endpoint: str):
    """Context manager for tracking external API calls."""
    start_time = time.time()
    status = "success"
    
    try:
        yield
    except Exception as e:
        status = "error"
        logger.error(f"External API call failed: {service}/{endpoint} - {e}")
        raise
    finally:
        duration = time.time() - start_time
        performance_monitor.track_external_api_call(service, endpoint, duration, status)


@asynccontextmanager
async def track_database_query(operation: str, table: str):
    """Context manager for tracking database queries."""
    start_time = time.time()
    
    try:
        yield
    finally:
        duration = time.time() - start_time
        performance_monitor.track_database_query(operation, table, duration)


def setup_performance_monitoring(app):
    """Setup performance monitoring for FastAPI app."""
    
    # Add middleware
    app.middleware("http")(performance_middleware)
    
    # Add metrics endpoint
    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(
            performance_monitor.get_metrics_data(),
            media_type=CONTENT_TYPE_LATEST
        )
    
    # Add health endpoint
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return performance_monitor.get_health_status()
    
    # Initialize start time
    performance_monitor._start_time = time.time()
    
    logger.info("Performance monitoring initialized")
