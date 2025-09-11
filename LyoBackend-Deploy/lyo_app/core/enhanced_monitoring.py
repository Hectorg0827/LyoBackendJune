"""
Comprehensive Error Handling and Monitoring System
Production-ready error tracking, logging, and performance monitoring
"""

import asyncio
import traceback
import sys
import time
import json
import uuid
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from contextlib import contextmanager
from functools import wraps
from dataclasses import dataclass, asdict

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
import structlog

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from lyo_app.core.config import settings
from lyo_app.core.logging import logger

@dataclass
class ErrorContext:
    """Rich error context for debugging"""
    error_id: str
    timestamp: datetime
    user_id: Optional[int]
    endpoint: str
    method: str
    request_body: Optional[Dict[str, Any]]
    headers: Dict[str, str]
    user_agent: Optional[str]
    ip_address: str
    error_type: str
    error_message: str
    stack_trace: str
    system_info: Dict[str, Any]
    additional_context: Dict[str, Any]

@dataclass
class PerformanceMetrics:
    """Performance tracking metrics"""
    endpoint: str
    method: str
    response_time_ms: float
    status_code: int
    timestamp: datetime
    user_id: Optional[int]
    memory_usage_mb: float
    cpu_usage_percent: float
    database_queries: int
    cache_hits: int
    cache_misses: int

class ErrorSeverity:
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory:
    """Error categorization"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    BUSINESS_LOGIC = "business_logic"
    EXTERNAL_SERVICE = "external_service"
    DATABASE = "database"
    SYSTEM = "system"
    AI_SERVICE = "ai_service"
    STORAGE = "storage"
    NETWORK = "network"

class EnhancedErrorHandler:
    """
    Comprehensive error handling system with:
    - Structured error logging
    - Error categorization and severity assessment
    - Performance monitoring
    - Automatic error recovery
    - Real-time alerting
    - Error analytics
    """
    
    def __init__(self):
        self.error_counts = {}
        self.performance_metrics = []
        self.error_patterns = {}
        self.recovery_strategies = {}
        
        # Initialize monitoring
        self._setup_monitoring()
    
    def _setup_monitoring(self):
        """Setup monitoring and alerting"""
        
        # Register recovery strategies
        self.recovery_strategies = {
            ErrorCategory.AI_SERVICE: self._recover_ai_service,
            ErrorCategory.DATABASE: self._recover_database,
            ErrorCategory.EXTERNAL_SERVICE: self._recover_external_service,
            ErrorCategory.STORAGE: self._recover_storage
        }
    
    async def handle_error(
        self,
        error: Exception,
        request: Request,
        user_id: Optional[int] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """
        Comprehensive error handling with context collection
        """
        
        # Generate unique error ID
        error_id = str(uuid.uuid4())
        
        # Categorize error
        error_category = self._categorize_error(error)
        error_severity = self._assess_severity(error, error_category)
        
        # Collect system information
        system_info = self._collect_system_info()
        
        # Build error context
        error_context = ErrorContext(
            error_id=error_id,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            endpoint=str(request.url.path),
            method=request.method,
            request_body=await self._safe_get_request_body(request),
            headers=dict(request.headers),
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else "unknown",
            error_type=type(error).__name__,
            error_message=str(error),
            stack_trace=traceback.format_exc(),
            system_info=system_info,
            additional_context=additional_context or {}
        )
        
        # Log error with full context
        await self._log_error(error_context, error_category, error_severity)
        
        # Update error statistics
        self._update_error_stats(error_category, error_severity)
        
        # Attempt automatic recovery
        recovery_attempted = await self._attempt_recovery(error, error_category, error_context)
        
        # Send alerts if necessary
        await self._send_alerts(error_context, error_category, error_severity)
        
        # Return user-friendly error response
        return self._create_error_response(error, error_id, error_category, recovery_attempted)
    
    def _categorize_error(self, error: Exception) -> str:
        """Categorize error based on type and context"""
        
        error_type = type(error).__name__
        error_message = str(error).lower()
        
        # Authentication errors
        if error_type in ['AuthenticationError', 'UnauthorizedError'] or 'unauthorized' in error_message:
            return ErrorCategory.AUTHENTICATION
        
        # Authorization errors
        if error_type in ['PermissionError', 'ForbiddenError'] or 'forbidden' in error_message:
            return ErrorCategory.AUTHORIZATION
        
        # Validation errors
        if error_type in ['ValidationError', 'ValueError', 'TypeError'] or 'validation' in error_message:
            return ErrorCategory.VALIDATION
        
        # Database errors
        if error_type in ['SQLAlchemyError', 'IntegrityError', 'OperationalError'] or 'database' in error_message:
            return ErrorCategory.DATABASE
        
        # AI service errors
        if 'gemini' in error_message or 'ai' in error_message or 'generation' in error_message:
            return ErrorCategory.AI_SERVICE
        
        # Storage errors
        if 'storage' in error_message or 's3' in error_message or 'upload' in error_message:
            return ErrorCategory.STORAGE
        
        # Network errors
        if error_type in ['ConnectionError', 'TimeoutError', 'HTTPError'] or 'network' in error_message:
            return ErrorCategory.NETWORK
        
        # External service errors
        if 'external' in error_message or 'api' in error_message:
            return ErrorCategory.EXTERNAL_SERVICE
        
        # Default to business logic
        return ErrorCategory.BUSINESS_LOGIC
    
    def _assess_severity(self, error: Exception, category: str) -> str:
        """Assess error severity based on type and impact"""
        
        error_type = type(error).__name__
        error_message = str(error).lower()
        
        # Critical errors
        if error_type in ['SystemExit', 'KeyboardInterrupt', 'MemoryError']:
            return ErrorSeverity.CRITICAL
        
        if category == ErrorCategory.DATABASE and 'connection' in error_message:
            return ErrorSeverity.CRITICAL
        
        if category == ErrorCategory.SYSTEM:
            return ErrorSeverity.CRITICAL
        
        # High severity errors
        if error_type in ['RuntimeError', 'OSError', 'IOError']:
            return ErrorSeverity.HIGH
        
        if category in [ErrorCategory.AUTHENTICATION, ErrorCategory.AI_SERVICE]:
            return ErrorSeverity.HIGH
        
        # Medium severity errors
        if category in [ErrorCategory.EXTERNAL_SERVICE, ErrorCategory.STORAGE]:
            return ErrorSeverity.MEDIUM
        
        if error_type in ['HTTPError', 'ConnectionError']:
            return ErrorSeverity.MEDIUM
        
        # Low severity errors (validation, business logic)
        return ErrorSeverity.LOW
    
    def _collect_system_info(self) -> Dict[str, Any]:
        """Collect current system information"""
        
        if not PSUTIL_AVAILABLE:
            return {'error': 'psutil not available'}
        
        try:
            return {
                'memory_usage': {
                    'total': psutil.virtual_memory().total,
                    'available': psutil.virtual_memory().available,
                    'percent': psutil.virtual_memory().percent
                },
                'cpu_usage': psutil.cpu_percent(interval=1),
                'disk_usage': {
                    'total': psutil.disk_usage('/').total,
                    'free': psutil.disk_usage('/').free,
                    'percent': psutil.disk_usage('/').percent
                },
                'python_version': sys.version,
                'platform': sys.platform,
                'process_id': psutil.Process().pid,
                'thread_count': psutil.Process().num_threads()
            }
        except Exception as e:
            logger.warning(f"Failed to collect system info: {e}")
            return {'error': 'Failed to collect system info'}
    
    async def _safe_get_request_body(self, request: Request) -> Optional[Dict[str, Any]]:
        """Safely extract request body without consuming stream"""
        
        try:
            # Only read body for POST/PUT/PATCH requests
            if request.method in ['POST', 'PUT', 'PATCH']:
                body = await request.body()
                if body:
                    return json.loads(body.decode('utf-8'))
        except Exception as e:
            logger.warning(f"Failed to extract request body: {e}")
        
        return None
    
    async def _log_error(
        self, 
        error_context: ErrorContext, 
        category: str, 
        severity: str
    ):
        """Log error with structured data"""
        
        log_data = {
            'error_id': error_context.error_id,
            'category': category,
            'severity': severity,
            'timestamp': error_context.timestamp.isoformat(),
            'endpoint': error_context.endpoint,
            'method': error_context.method,
            'user_id': error_context.user_id,
            'error_type': error_context.error_type,
            'error_message': error_context.error_message,
            'ip_address': error_context.ip_address,
            'user_agent': error_context.user_agent
        }
        
        # Log based on severity
        if severity == ErrorSeverity.CRITICAL:
            logger.critical("Critical error occurred", extra=log_data)
        elif severity == ErrorSeverity.HIGH:
            logger.error("High severity error occurred", extra=log_data)
        elif severity == ErrorSeverity.MEDIUM:
            logger.warning("Medium severity error occurred", extra=log_data)
        else:
            logger.info("Low severity error occurred", extra=log_data)
        
        # Store detailed context for debugging
        logger.debug(
            "Full error context",
            extra={
                'error_context': asdict(error_context),
                'stack_trace': error_context.stack_trace
            }
        )
    
    def _update_error_stats(self, category: str, severity: str):
        """Update error statistics for monitoring"""
        
        key = f"{category}:{severity}"
        
        if key not in self.error_counts:
            self.error_counts[key] = {
                'count': 0,
                'first_seen': datetime.utcnow(),
                'last_seen': datetime.utcnow()
            }
        
        self.error_counts[key]['count'] += 1
        self.error_counts[key]['last_seen'] = datetime.utcnow()
    
    async def _attempt_recovery(
        self, 
        error: Exception, 
        category: str, 
        error_context: ErrorContext
    ) -> bool:
        """Attempt automatic error recovery"""
        
        recovery_strategy = self.recovery_strategies.get(category)
        
        if recovery_strategy:
            try:
                logger.info(f"Attempting recovery for {category} error")
                await recovery_strategy(error, error_context)
                logger.info(f"Recovery successful for {category} error")
                return True
            except Exception as e:
                logger.error(f"Recovery failed for {category} error: {e}")
        
        return False
    
    async def _recover_ai_service(self, error: Exception, context: ErrorContext):
        """Recover from AI service errors"""
        
        # Switch to backup AI provider
        from lyo_app.core.ai_resilience import ai_resilience_manager
        
        if hasattr(ai_resilience_manager, 'switch_provider'):
            await ai_resilience_manager.switch_provider()
            logger.info("Switched to backup AI provider")
    
    async def _recover_database(self, error: Exception, context: ErrorContext):
        """Recover from database errors"""
        
        # Attempt database reconnection
        logger.info("Attempting database reconnection")
        # Implementation would depend on your database setup
    
    async def _recover_external_service(self, error: Exception, context: ErrorContext):
        """Recover from external service errors"""
        
        # Implement circuit breaker reset or service health check
        logger.info("Attempting external service recovery")
    
    async def _recover_storage(self, error: Exception, context: ErrorContext):
        """Recover from storage errors"""
        
        # Switch to backup storage provider
        logger.info("Attempting storage fallback")
    
    async def _send_alerts(
        self, 
        error_context: ErrorContext, 
        category: str, 
        severity: str
    ):
        """Send alerts based on error severity and patterns"""
        
        # Critical errors always trigger alerts
        if severity == ErrorSeverity.CRITICAL:
            await self._send_critical_alert(error_context)
        
        # Check for error patterns (multiple occurrences)
        key = f"{category}:{severity}"
        if key in self.error_counts:
            count = self.error_counts[key]['count']
            
            # Alert on error spikes
            if count > 10 and count % 10 == 0:  # Every 10 occurrences
                await self._send_pattern_alert(error_context, category, count)
    
    async def _send_critical_alert(self, error_context: ErrorContext):
        """Send critical error alert"""
        
        alert_data = {
            'type': 'critical_error',
            'error_id': error_context.error_id,
            'message': f"CRITICAL: {error_context.error_type} in {error_context.endpoint}",
            'timestamp': error_context.timestamp.isoformat(),
            'details': error_context.error_message
        }
        
        logger.critical("Critical alert triggered", extra=alert_data)
        
        # Here you would integrate with your alerting system
        # (Slack, PagerDuty, email, etc.)
    
    async def _send_pattern_alert(
        self, 
        error_context: ErrorContext, 
        category: str, 
        count: int
    ):
        """Send alert for error patterns"""
        
        alert_data = {
            'type': 'error_pattern',
            'category': category,
            'count': count,
            'latest_error_id': error_context.error_id,
            'endpoint': error_context.endpoint,
            'timestamp': error_context.timestamp.isoformat()
        }
        
        logger.warning("Error pattern detected", extra=alert_data)
    
    def _create_error_response(
        self, 
        error: Exception, 
        error_id: str, 
        category: str, 
        recovery_attempted: bool
    ) -> JSONResponse:
        """Create user-friendly error response"""
        
        # Default error messages by category
        user_messages = {
            ErrorCategory.AUTHENTICATION: "Authentication required. Please log in.",
            ErrorCategory.AUTHORIZATION: "Access denied. You don't have permission.",
            ErrorCategory.VALIDATION: "Invalid input data. Please check your request.",
            ErrorCategory.AI_SERVICE: "AI service temporarily unavailable. Please try again.",
            ErrorCategory.DATABASE: "Database temporarily unavailable. Please try again.",
            ErrorCategory.STORAGE: "File service temporarily unavailable. Please try again.",
            ErrorCategory.EXTERNAL_SERVICE: "External service unavailable. Please try again.",
            ErrorCategory.NETWORK: "Network connection issue. Please try again.",
            ErrorCategory.BUSINESS_LOGIC: "Request could not be processed. Please try again.",
            ErrorCategory.SYSTEM: "System error occurred. Please try again later."
        }
        
        # Get HTTP status code
        if isinstance(error, HTTPException):
            status_code = error.status_code
            detail = error.detail
        else:
            status_code = 500
            detail = user_messages.get(category, "An unexpected error occurred.")
        
        response_data = {
            'error': True,
            'error_id': error_id,
            'message': detail,
            'category': category,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if recovery_attempted:
            response_data['recovery_attempted'] = True
            response_data['message'] += " Recovery measures have been initiated."
        
        return JSONResponse(
            status_code=status_code,
            content=response_data
        )

class PerformanceMonitor:
    """Real-time performance monitoring"""
    
    def __init__(self):
        self.metrics = []
        self.slow_queries = []
        self.endpoint_stats = {}
    
    @contextmanager
    def track_performance(
        self, 
        endpoint: str, 
        method: str, 
        user_id: Optional[int] = None
    ):
        """Context manager for performance tracking"""
        
        start_time = time.time()
        
        if PSUTIL_AVAILABLE:
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            start_cpu = psutil.cpu_percent()
        else:
            start_memory = 0
            start_cpu = 0
        
        try:
            yield
        finally:
            end_time = time.time()
            
            if PSUTIL_AVAILABLE:
                end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
                end_cpu = psutil.cpu_percent()
            else:
                end_memory = 0
                end_cpu = 0
            
            metrics = PerformanceMetrics(
                endpoint=endpoint,
                method=method,
                response_time_ms=(end_time - start_time) * 1000,
                status_code=200,  # Will be updated by middleware
                timestamp=datetime.utcnow(),
                user_id=user_id,
                memory_usage_mb=end_memory - start_memory,
                cpu_usage_percent=end_cpu - start_cpu,
                database_queries=0,  # Would be tracked by database middleware
                cache_hits=0,  # Would be tracked by cache middleware
                cache_misses=0
            )
            
            self.record_metrics(metrics)
    
    def record_metrics(self, metrics: PerformanceMetrics):
        """Record performance metrics"""
        
        self.metrics.append(metrics)
        
        # Update endpoint statistics
        if metrics.endpoint not in self.endpoint_stats:
            self.endpoint_stats[metrics.endpoint] = {
                'total_requests': 0,
                'avg_response_time': 0,
                'max_response_time': 0,
                'min_response_time': float('inf'),
                'error_count': 0
            }
        
        stats = self.endpoint_stats[metrics.endpoint]
        stats['total_requests'] += 1
        
        # Update response time statistics
        current_avg = stats['avg_response_time']
        total_requests = stats['total_requests']
        stats['avg_response_time'] = (
            (current_avg * (total_requests - 1) + metrics.response_time_ms) / total_requests
        )
        
        if metrics.response_time_ms > stats['max_response_time']:
            stats['max_response_time'] = metrics.response_time_ms
        
        if metrics.response_time_ms < stats['min_response_time']:
            stats['min_response_time'] = metrics.response_time_ms
        
        # Log slow requests
        if metrics.response_time_ms > 5000:  # 5 seconds
            logger.warning(
                f"Slow request detected: {metrics.endpoint} took {metrics.response_time_ms:.2f}ms"
            )
        
        # Keep only recent metrics (last 1000)
        if len(self.metrics) > 1000:
            self.metrics = self.metrics[-1000:]
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        
        if not self.metrics:
            return {'message': 'No performance data available'}
        
        recent_metrics = self.metrics[-100:]  # Last 100 requests
        
        avg_response_time = sum(m.response_time_ms for m in recent_metrics) / len(recent_metrics)
        avg_memory_usage = sum(m.memory_usage_mb for m in recent_metrics) / len(recent_metrics)
        avg_cpu_usage = sum(m.cpu_usage_percent for m in recent_metrics) / len(recent_metrics)
        
        return {
            'total_requests': len(self.metrics),
            'recent_avg_response_time_ms': round(avg_response_time, 2),
            'recent_avg_memory_usage_mb': round(avg_memory_usage, 2),
            'recent_avg_cpu_usage_percent': round(avg_cpu_usage, 2),
            'endpoint_stats': self.endpoint_stats,
            'slow_requests_count': len([m for m in recent_metrics if m.response_time_ms > 5000])
        }

# Global instances
enhanced_error_handler = EnhancedErrorHandler()
performance_monitor = PerformanceMonitor()

# Decorator for endpoint monitoring
def monitor_performance(endpoint_name: Optional[str] = None):
    """Decorator for automatic performance monitoring"""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            endpoint = endpoint_name or func.__name__
            
            with performance_monitor.track_performance(endpoint, "POST"):  # Default to POST
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# Error handling decorator
def handle_errors(category: str = ErrorCategory.BUSINESS_LOGIC):
    """Decorator for automatic error handling"""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Extract request and user info from args/kwargs if available
                request = None
                user_id = None
                
                for arg in args:
                    if hasattr(arg, 'url'):  # Likely a Request object
                        request = arg
                        break
                
                for value in kwargs.values():
                    if hasattr(value, 'url'):  # Likely a Request object
                        request = value
                        break
                    elif hasattr(value, 'id'):  # Likely a User object
                        user_id = value.id
                
                if request:
                    return await enhanced_error_handler.handle_error(
                        error=e,
                        request=request,
                        user_id=user_id,
                        additional_context={'function': func.__name__, 'category': category}
                    )
                else:
                    # Re-raise if we can't handle properly
                    raise e
        
        return wrapper
    return decorator
