"""
Comprehensive Monitoring and Health Check System
Provides real-time monitoring, alerting, and health checks for all backend components
Enhanced with existing Prometheus metrics and structured logging
"""

import asyncio
import time
import psutil
import logging
import structlog
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import deque, defaultdict
from datetime import datetime, timedelta
from enum import Enum
from contextlib import asynccontextmanager
from uuid import uuid4
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiofiles
import os

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

# Prometheus metrics (existing)
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

# Enhanced metrics for comprehensive monitoring
system_cpu_usage = Gauge('system_cpu_usage_percent', 'CPU usage percentage')
system_memory_usage = Gauge('system_memory_usage_percent', 'Memory usage percentage')
system_disk_usage = Gauge('system_disk_usage_percent', 'Disk usage percentage')
database_connections_active = Gauge('database_connections_active', 'Active database connections')
ai_requests_total = Counter('ai_requests_total', 'Total AI requests', ['model', 'status'])
cache_hits_total = Counter('cache_hits_total', 'Cache hits', ['cache_type'])

@dataclass
class AlertConfig:
    name: str
    threshold: float
    comparison: str  # "gt", "lt", "eq", "gte", "lte"
    duration: int = 300  # seconds - how long condition must persist
    cooldown: int = 1800  # seconds - minimum time between alerts
    severity: str = "warning"  # "info", "warning", "error", "critical"
    channels: List[str] = field(default_factory=lambda: ["log"])  # "log", "email", "webhook"

@dataclass
class MetricPoint:
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)

class SystemMonitor:
    """Enhanced system resource monitoring with comprehensive metrics collection"""
    
    def __init__(self):
        self.cpu_history = deque(maxlen=60)  # Last 60 measurements
        self.memory_history = deque(maxlen=60)
        self.disk_history = deque(maxlen=60)
        self.network_history = deque(maxlen=60)
        self.last_network_stats = None
    
    async def collect_metrics(self) -> Dict[str, Any]:
        """Collect comprehensive system metrics"""
        
        timestamp = time.time()
        
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
        
        self.cpu_history.append(MetricPoint(cpu_percent, timestamp))
        system_cpu_usage.set(cpu_percent)
        
        # Memory metrics
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available = memory.available
        memory_used = memory.used
        
        self.memory_history.append(MetricPoint(memory_percent, timestamp))
        system_memory_usage.set(memory_percent)
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        disk_free = disk.free
        
        self.disk_history.append(MetricPoint(disk_percent, timestamp))
        system_disk_usage.set(disk_percent)
        
        # Network metrics
        network = psutil.net_io_counters()
        network_metrics = {
            "bytes_sent": network.bytes_sent,
            "bytes_recv": network.bytes_recv,
            "packets_sent": network.packets_sent,
            "packets_recv": network.packets_recv
        }
        
        # Calculate network rate if we have previous data
        network_rates = {}
        if self.last_network_stats:
            time_delta = timestamp - self.last_network_stats["timestamp"]
            if time_delta > 0:
                network_rates = {
                    "bytes_sent_per_sec": (network.bytes_sent - self.last_network_stats["bytes_sent"]) / time_delta,
                    "bytes_recv_per_sec": (network.bytes_recv - self.last_network_stats["bytes_recv"]) / time_delta,
                }
        
        self.last_network_stats = {**network_metrics, "timestamp": timestamp}
        self.network_history.append(MetricPoint(
            network_rates.get("bytes_recv_per_sec", 0), timestamp
        ))
        
        return {
            "timestamp": timestamp,
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count,
                "load_avg": load_avg,
                "history_avg": sum(p.value for p in self.cpu_history) / len(self.cpu_history) if self.cpu_history else 0
            },
            "memory": {
                "percent": memory_percent,
                "available_bytes": memory_available,
                "used_bytes": memory_used,
                "total_bytes": memory.total,
                "history_avg": sum(p.value for p in self.memory_history) / len(self.memory_history) if self.memory_history else 0
            },
            "disk": {
                "percent": disk_percent,
                "free_bytes": disk_free,
                "used_bytes": disk.used,
                "total_bytes": disk.total,
                "history_avg": sum(p.value for p in self.disk_history) / len(self.disk_history) if self.disk_history else 0
            },
            "network": {
                **network_metrics,
                **network_rates,
                "history_avg_recv": sum(p.value for p in self.network_history) / len(self.network_history) if self.network_history else 0
            }
        }

class AlertManager:
    """Intelligent alerting system with multiple notification channels"""
    
    def __init__(self):
        self.alerts: Dict[str, AlertConfig] = {}
        self.alert_states: Dict[str, Dict[str, Any]] = {}
        self.notification_history = deque(maxlen=1000)
    
    def register_alert(self, alert: AlertConfig):
        """Register a new alert"""
        self.alerts[alert.name] = alert
        self.alert_states[alert.name] = {
            "triggered": False,
            "last_triggered": 0,
            "last_notified": 0,
            "condition_start": None
        }
        logger.info(f"Registered alert: {alert.name}")
    
    async def check_alerts(self, metrics: Dict[str, Any]):
        """Check all alerts against current metrics"""
        
        current_time = time.time()
        
        for alert_name, alert in self.alerts.items():
            state = self.alert_states[alert_name]
            
            # Extract metric value
            metric_value = self._extract_metric_value(metrics, alert_name)
            if metric_value is None:
                continue
            
            # Check condition
            condition_met = self._evaluate_condition(metric_value, alert.threshold, alert.comparison)
            
            if condition_met:
                if state["condition_start"] is None:
                    state["condition_start"] = current_time
                
                # Check if condition has persisted long enough
                if current_time - state["condition_start"] >= alert.duration:
                    # Check cooldown period
                    if current_time - state["last_notified"] >= alert.cooldown:
                        await self._send_alert(alert, metric_value, metrics)
                        state["last_notified"] = current_time
                        state["last_triggered"] = current_time
                        state["triggered"] = True
            else:
                # Condition not met, reset
                state["condition_start"] = None
                if state["triggered"]:
                    # Send recovery notification
                    await self._send_recovery_notification(alert, metric_value)
                    state["triggered"] = False
    
    def _extract_metric_value(self, metrics: Dict[str, Any], alert_name: str) -> Optional[float]:
        """Extract metric value based on alert name"""
        
        # Define metric paths
        metric_paths = {
            "cpu_high": ["cpu", "percent"],
            "memory_high": ["memory", "percent"],
            "disk_high": ["disk", "percent"],
            "response_time_high": ["avg_response_time"],
            "error_rate_high": ["error_rate"]
        }
        
        if alert_name not in metric_paths:
            return None
        
        # Navigate through nested dictionary
        value = metrics
        for key in metric_paths[alert_name]:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return float(value) if isinstance(value, (int, float)) else None
    
    def _evaluate_condition(self, value: float, threshold: float, comparison: str) -> bool:
        """Evaluate alert condition"""
        
        comparisons = {
            "gt": value > threshold,
            "gte": value >= threshold,
            "lt": value < threshold,
            "lte": value <= threshold,
            "eq": value == threshold
        }
        
        return comparisons.get(comparison, False)
    
    async def _send_alert(self, alert: AlertConfig, metric_value: float, full_metrics: Dict[str, Any]):
        """Send alert notification"""
        
        message = {
            "alert_name": alert.name,
            "severity": alert.severity,
            "metric_value": metric_value,
            "threshold": alert.threshold,
            "timestamp": time.time(),
            "full_metrics": full_metrics
        }
        
        # Log alert
        if "log" in alert.channels:
            log_level = getattr(logging, alert.severity.upper(), logging.WARNING)
            logger.log(log_level, f"ALERT: {alert.name} - Value: {metric_value}, Threshold: {alert.threshold}")
        
        self.notification_history.append(message)
    
    async def _send_recovery_notification(self, alert: AlertConfig, metric_value: float):
        """Send recovery notification"""
        
        message = f"RECOVERY: {alert.name} - Value normalized to {metric_value}"
        logger.info(message)
        
        recovery_msg = {
            "alert_name": alert.name,
            "type": "recovery",
            "metric_value": metric_value,
            "timestamp": time.time()
        }
        
        self.notification_history.append(recovery_msg)

class EnhancedPerformanceMonitor:
    """Enhanced performance monitoring with comprehensive metrics"""
    
    def __init__(self):
        self.system_monitor = SystemMonitor()
        self.alert_manager = AlertManager()
        self.request_metrics = defaultdict(list)
        self.monitoring_active = False
        self.metrics_history = deque(maxlen=2880)  # 24 hours at 30-second intervals
        
        self._setup_default_alerts()
    
    def _setup_default_alerts(self):
        """Setup default system alerts"""
        
        default_alerts = [
            AlertConfig("cpu_high", 80.0, "gt", duration=300, severity="warning"),
            AlertConfig("memory_high", 85.0, "gt", duration=300, severity="warning"),
            AlertConfig("disk_high", 90.0, "gt", duration=300, severity="error"),
            AlertConfig("response_time_high", 5.0, "gt", duration=180, severity="warning"),
            AlertConfig("error_rate_high", 10.0, "gt", duration=300, severity="error"),
        ]
        
        for alert in default_alerts:
            self.alert_manager.register_alert(alert)

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

def monitor_request(endpoint_name: str):
    """Decorator to monitor request performance"""
    
    def decorator(func: Callable) -> Callable:
        import functools
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            error = None
            status_code = 200
            
            try:
                result = await func(*args, **kwargs)
                return result
                
            except Exception as e:
                error = str(e)
                status_code = 500
                raise
                
            finally:
                duration_ms = (time.time() - start_time) * 1000
                
                # Try to extract user_id from kwargs if available
                user_id = None
                if 'current_user' in kwargs:
                    user = kwargs['current_user']
                    user_id = getattr(user, 'id', None)
                
                # Record metrics
                logger.info(f"Request {endpoint_name} completed", extra={
                    "endpoint": endpoint_name,
                    "duration_ms": duration_ms,
                    "status_code": status_code,
                    "user_id": user_id,
                    "error": error
                })
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            error = None
            status_code = 200
            
            try:
                result = func(*args, **kwargs)
                return result
                
            except Exception as e:
                error = str(e)
                status_code = 500
                raise
                
            finally:
                duration_ms = (time.time() - start_time) * 1000
                
                # Try to extract user_id from kwargs if available
                user_id = None
                if 'current_user' in kwargs:
                    user = kwargs['current_user']
                    user_id = getattr(user, 'id', None)
                
                # Record metrics  
                logger.info(f"Request {endpoint_name} completed", extra={
                    "endpoint": endpoint_name,
                    "duration_ms": duration_ms,
                    "status_code": status_code,
                    "user_id": user_id,
                    "error": error
                })
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
