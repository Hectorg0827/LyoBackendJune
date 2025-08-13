"""
Enterprise Observability Stack Implementation
Comprehensive monitoring, logging, and tracing solution
"""

import asyncio
import time
import uuid
import json
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field, asdict
from contextlib import asynccontextmanager
import traceback
import sys
import os
from collections import defaultdict
import threading

# Structured logging
import structlog
from structlog.stdlib import LoggerFactory
from structlog.processors import JSONRenderer, TimeStamper, add_log_level, StackInfoRenderer

# OpenTelemetry for distributed tracing
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Metrics collection
import psutil
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
from prometheus_client.multiprocess import MultiProcessCollector

# FastAPI dependencies
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from lyo_app.core.config import settings
from lyo_app.core.cache_manager import get_cache_manager

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class LogLevel(Enum):
    """Log levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricType(Enum):
    """Metric types"""
    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"
    SUMMARY = "summary"


class AlertSeverity(Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TraceContext:
    """Distributed tracing context"""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    operation_name: str = ""
    service_name: str = "lyo-backend"
    tags: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    status: str = "ok"
    
    def finish(self, error: Optional[Exception] = None):
        """Finish the trace span"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        
        if error:
            self.error = str(error)
            self.status = "error"
            self.tags["error"] = True
            self.tags["error.message"] = str(error)
            self.tags["error.type"] = type(error).__name__


@dataclass
class LogEntry:
    """Structured log entry"""
    timestamp: str
    level: LogLevel
    message: str
    service: str = "lyo-backend"
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    exception: Optional[Dict[str, Any]] = None


@dataclass
class MetricEntry:
    """Metric data point"""
    name: str
    value: Union[int, float]
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    help_text: str = ""


@dataclass
class AlertRule:
    """Alert rule definition"""
    name: str
    condition: str  # PromQL-like expression
    threshold: float
    severity: AlertSeverity
    duration: int = 300  # 5 minutes default
    notification_channels: List[str] = field(default_factory=list)
    enabled: bool = True
    
    def evaluate(self, current_value: float) -> bool:
        """Evaluate if alert should fire"""
        if not self.enabled:
            return False
        
        # Simple threshold-based evaluation
        if ">" in self.condition:
            return current_value > self.threshold
        elif "<" in self.condition:
            return current_value < self.threshold
        elif "==" in self.condition:
            return abs(current_value - self.threshold) < 0.001
        
        return False


class DistributedTracer:
    """Distributed tracing implementation"""
    
    def __init__(self):
        self.active_spans: Dict[str, TraceContext] = {}
        self.completed_spans: List[TraceContext] = []
        self._lock = threading.RLock()
        
        # Initialize OpenTelemetry
        self._setup_otel()
    
    def _setup_otel(self):
        """Setup OpenTelemetry tracing"""
        try:
            # Jaeger exporter for distributed tracing
            jaeger_exporter = JaegerExporter(
                agent_host_name=getattr(settings, 'JAEGER_HOST', 'localhost'),
                agent_port=getattr(settings, 'JAEGER_PORT', 14268)
            )
            
            # Configure tracer provider
            trace.set_tracer_provider(TracerProvider())
            tracer = trace.get_tracer(__name__)
            
            # Add span processor
            span_processor = BatchSpanProcessor(jaeger_exporter)
            trace.get_tracer_provider().add_span_processor(span_processor)
            
            # Instrument frameworks
            FastAPIInstrumentor().instrument()
            SQLAlchemyInstrumentor().instrument()
            RedisInstrumentor().instrument()
            RequestsInstrumentor().instrument()
            
            self.tracer = tracer
            logger.info("Distributed tracing configured successfully")
            
        except Exception as e:
            logger.error(f"Failed to configure distributed tracing: {e}")
            self.tracer = None
    
    def start_span(
        self,
        operation_name: str,
        parent_span_id: Optional[str] = None,
        tags: Dict[str, Any] = None
    ) -> TraceContext:
        """Start a new trace span"""
        
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        
        span_context = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            tags=tags or {}
        )
        
        with self._lock:
            self.active_spans[span_id] = span_context
        
        # Create OpenTelemetry span if available
        if self.tracer:
            otel_span = self.tracer.start_span(operation_name)
            if tags:
                for key, value in tags.items():
                    otel_span.set_attribute(key, str(value))
            span_context.tags["otel_span"] = otel_span
        
        logger.debug(
            "Started trace span",
            trace_id=trace_id,
            span_id=span_id,
            operation=operation_name,
            parent=parent_span_id
        )
        
        return span_context
    
    def finish_span(self, span_context: TraceContext, error: Optional[Exception] = None):
        """Finish a trace span"""
        
        span_context.finish(error)
        
        with self._lock:
            if span_context.span_id in self.active_spans:
                del self.active_spans[span_context.span_id]
            self.completed_spans.append(span_context)
        
        # Finish OpenTelemetry span
        otel_span = span_context.tags.get("otel_span")
        if otel_span:
            if error:
                otel_span.set_status(trace.Status(trace.StatusCode.ERROR, str(error)))
            otel_span.end()
        
        logger.debug(
            "Finished trace span",
            trace_id=span_context.trace_id,
            span_id=span_context.span_id,
            operation=span_context.operation_name,
            duration=span_context.duration,
            status=span_context.status
        )
    
    @asynccontextmanager
    async def trace_operation(
        self,
        operation_name: str,
        tags: Dict[str, Any] = None
    ):
        """Context manager for tracing operations"""
        
        span = self.start_span(operation_name, tags=tags)
        
        try:
            yield span
        except Exception as e:
            self.finish_span(span, error=e)
            raise
        else:
            self.finish_span(span)
    
    def get_active_spans(self) -> List[TraceContext]:
        """Get currently active spans"""
        with self._lock:
            return list(self.active_spans.values())
    
    def get_recent_spans(self, limit: int = 100) -> List[TraceContext]:
        """Get recently completed spans"""
        with self._lock:
            return self.completed_spans[-limit:]


class MetricsCollector:
    """Application metrics collector"""
    
    def __init__(self):
        # Create custom registry for multiprocess support
        self.registry = CollectorRegistry()
        
        # Core application metrics
        self.request_count = Counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status_code'],
            registry=self.registry
        )
        
        self.request_duration = Histogram(
            'http_request_duration_seconds',
            'HTTP request duration',
            ['method', 'endpoint'],
            registry=self.registry
        )
        
        self.active_connections = Gauge(
            'http_active_connections',
            'Active HTTP connections',
            registry=self.registry
        )
        
        # Business metrics
        self.ai_requests = Counter(
            'ai_requests_total',
            'Total AI requests',
            ['model', 'operation'],
            registry=self.registry
        )
        
        self.ai_tokens_used = Counter(
            'ai_tokens_used_total',
            'Total AI tokens consumed',
            ['model', 'type'],
            registry=self.registry
        )
        
        self.cache_hits = Counter(
            'cache_operations_total',
            'Cache operations',
            ['operation', 'result'],
            registry=self.registry
        )
        
        self.database_operations = Counter(
            'database_operations_total',
            'Database operations',
            ['engine', 'operation', 'table'],
            registry=self.registry
        )
        
        self.database_duration = Histogram(
            'database_operation_duration_seconds',
            'Database operation duration',
            ['engine', 'operation'],
            registry=self.registry
        )
        
        # System metrics
        self.cpu_usage = Gauge(
            'system_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )
        
        self.memory_usage = Gauge(
            'system_memory_usage_bytes',
            'Memory usage in bytes',
            registry=self.registry
        )
        
        self.disk_usage = Gauge(
            'system_disk_usage_percent',
            'Disk usage percentage',
            registry=self.registry
        )
        
        # Start system metrics collection
        self._start_system_metrics_collection()
    
    def _start_system_metrics_collection(self):
        """Start collecting system metrics"""
        async def collect_system_metrics():
            while True:
                try:
                    # CPU usage
                    cpu_percent = psutil.cpu_percent(interval=1)
                    self.cpu_usage.set(cpu_percent)
                    
                    # Memory usage
                    memory = psutil.virtual_memory()
                    self.memory_usage.set(memory.used)
                    
                    # Disk usage
                    disk = psutil.disk_usage('/')
                    disk_percent = (disk.used / disk.total) * 100
                    self.disk_usage.set(disk_percent)
                    
                except Exception as e:
                    logger.error(f"Failed to collect system metrics: {e}")
                
                await asyncio.sleep(30)  # Collect every 30 seconds
        
        # Run in background
        asyncio.create_task(collect_system_metrics())
    
    def record_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float
    ):
        """Record HTTP request metrics"""
        self.request_count.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()
        
        self.request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
    
    def record_ai_request(
        self,
        model: str,
        operation: str,
        tokens_used: int = 0,
        token_type: str = "completion"
    ):
        """Record AI usage metrics"""
        self.ai_requests.labels(
            model=model,
            operation=operation
        ).inc()
        
        if tokens_used > 0:
            self.ai_tokens_used.labels(
                model=model,
                type=token_type
            ).inc(tokens_used)
    
    def record_cache_operation(self, operation: str, hit: bool):
        """Record cache operation metrics"""
        result = "hit" if hit else "miss"
        self.cache_hits.labels(
            operation=operation,
            result=result
        ).inc()
    
    def record_database_operation(
        self,
        engine: str,
        operation: str,
        table: str,
        duration: float
    ):
        """Record database operation metrics"""
        self.database_operations.labels(
            engine=engine,
            operation=operation,
            table=table
        ).inc()
        
        self.database_duration.labels(
            engine=engine,
            operation=operation
        ).observe(duration)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary for health checks"""
        try:
            # This is a simplified version - in production you'd query Prometheus
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "system": {
                    "cpu_usage": psutil.cpu_percent(),
                    "memory_usage": psutil.virtual_memory().percent,
                    "disk_usage": psutil.disk_usage('/').percent
                },
                "application": {
                    "active_connections": 0,  # Would be tracked in middleware
                    "total_requests": 0,      # Would sum from counter
                    "average_response_time": 0  # Would calculate from histogram
                }
            }
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {"error": str(e)}
    
    def export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format"""
        try:
            return generate_latest(self.registry).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to export Prometheus metrics: {e}")
            return ""


class AlertManager:
    """Alert management system"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.alert_rules: List[AlertRule] = []
        self.active_alerts: Dict[str, Dict[str, Any]] = {}
        self.alert_history: List[Dict[str, Any]] = []
        
        # Setup default alert rules
        self._setup_default_alerts()
        
        # Start alert evaluation
        self._start_alert_evaluation()
    
    def _setup_default_alerts(self):
        """Setup default alert rules"""
        default_rules = [
            AlertRule(
                name="high_cpu_usage",
                condition="cpu_usage > 80",
                threshold=80.0,
                severity=AlertSeverity.HIGH,
                duration=300  # 5 minutes
            ),
            AlertRule(
                name="high_memory_usage",
                condition="memory_usage > 85",
                threshold=85.0,
                severity=AlertSeverity.HIGH,
                duration=300
            ),
            AlertRule(
                name="high_error_rate",
                condition="error_rate > 5",
                threshold=5.0,
                severity=AlertSeverity.MEDIUM,
                duration=180  # 3 minutes
            ),
            AlertRule(
                name="slow_response_time",
                condition="avg_response_time > 2000",
                threshold=2000.0,  # 2 seconds in ms
                severity=AlertSeverity.MEDIUM,
                duration=300
            ),
            AlertRule(
                name="database_connection_errors",
                condition="db_errors > 0",
                threshold=0.0,
                severity=AlertSeverity.CRITICAL,
                duration=60  # 1 minute
            )
        ]
        
        self.alert_rules.extend(default_rules)
    
    def _start_alert_evaluation(self):
        """Start alert evaluation loop"""
        async def evaluate_alerts():
            while True:
                try:
                    await self._evaluate_all_rules()
                except Exception as e:
                    logger.error(f"Alert evaluation failed: {e}")
                
                await asyncio.sleep(60)  # Evaluate every minute
        
        asyncio.create_task(evaluate_alerts())
    
    async def _evaluate_all_rules(self):
        """Evaluate all alert rules"""
        current_metrics = self.metrics_collector.get_metrics_summary()
        
        for rule in self.alert_rules:
            if not rule.enabled:
                continue
            
            try:
                # Extract metric value based on rule condition
                metric_value = self._extract_metric_value(rule.condition, current_metrics)
                
                if metric_value is not None:
                    should_fire = rule.evaluate(metric_value)
                    
                    alert_key = f"{rule.name}:{rule.condition}"
                    
                    if should_fire:
                        if alert_key not in self.active_alerts:
                            # New alert
                            alert = {
                                "rule_name": rule.name,
                                "severity": rule.severity.value,
                                "condition": rule.condition,
                                "current_value": metric_value,
                                "threshold": rule.threshold,
                                "started_at": datetime.utcnow().isoformat(),
                                "status": "firing"
                            }
                            
                            self.active_alerts[alert_key] = alert
                            await self._send_alert_notification(alert)
                            
                            logger.warning(
                                f"Alert fired: {rule.name}",
                                severity=rule.severity.value,
                                current_value=metric_value,
                                threshold=rule.threshold
                            )
                    else:
                        if alert_key in self.active_alerts:
                            # Alert resolved
                            alert = self.active_alerts[alert_key]
                            alert["status"] = "resolved"
                            alert["resolved_at"] = datetime.utcnow().isoformat()
                            
                            self.alert_history.append(alert.copy())
                            del self.active_alerts[alert_key]
                            
                            await self._send_alert_resolution(alert)
                            
                            logger.info(
                                f"Alert resolved: {rule.name}",
                                current_value=metric_value
                            )
                            
            except Exception as e:
                logger.error(f"Failed to evaluate rule {rule.name}: {e}")
    
    def _extract_metric_value(
        self,
        condition: str,
        metrics: Dict[str, Any]
    ) -> Optional[float]:
        """Extract metric value from condition string"""
        
        # Simple metric extraction - in production use proper parser
        if "cpu_usage" in condition:
            return metrics.get("system", {}).get("cpu_usage", 0.0)
        elif "memory_usage" in condition:
            return metrics.get("system", {}).get("memory_usage", 0.0)
        elif "error_rate" in condition:
            return metrics.get("application", {}).get("error_rate", 0.0)
        elif "response_time" in condition:
            return metrics.get("application", {}).get("average_response_time", 0.0)
        
        return None
    
    async def _send_alert_notification(self, alert: Dict[str, Any]):
        """Send alert notification"""
        # In production, integrate with PagerDuty, Slack, email, etc.
        
        notification = {
            "type": "alert",
            "severity": alert["severity"],
            "message": f"Alert: {alert['rule_name']} - {alert['condition']}",
            "details": alert,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Store in cache for monitoring dashboard
        try:
            cache_manager = get_cache_manager()
            await cache_manager.redis_client.lpush(
                "alerts:notifications",
                json.dumps(notification)
            )
            
            # Keep only last 1000 notifications
            await cache_manager.redis_client.ltrim("alerts:notifications", 0, 999)
            
        except Exception as e:
            logger.error(f"Failed to store alert notification: {e}")
    
    async def _send_alert_resolution(self, alert: Dict[str, Any]):
        """Send alert resolution notification"""
        notification = {
            "type": "resolution",
            "message": f"Resolved: {alert['rule_name']}",
            "details": alert,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            cache_manager = get_cache_manager()
            await cache_manager.redis_client.lpush(
                "alerts:notifications",
                json.dumps(notification)
            )
            
        except Exception as e:
            logger.error(f"Failed to store alert resolution: {e}")
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get currently active alerts"""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alert history"""
        return self.alert_history[-limit:]


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware for request tracing and metrics"""
    
    def __init__(
        self,
        app,
        tracer: DistributedTracer,
        metrics: MetricsCollector
    ):
        super().__init__(app)
        self.tracer = tracer
        self.metrics = metrics
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with observability"""
        
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        # Extract route info
        method = request.method
        path = request.url.path
        endpoint = self._normalize_endpoint(path)
        
        # Start distributed trace
        span = self.tracer.start_span(
            f"{method} {endpoint}",
            tags={
                "http.method": method,
                "http.url": str(request.url),
                "http.scheme": request.url.scheme,
                "http.user_agent": request.headers.get("user-agent", ""),
                "request.id": request_id
            }
        )
        
        # Add trace context to request
        request.state.trace_context = span
        request.state.request_id = request_id
        
        # Add structured logging context
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            trace_id=span.trace_id,
            span_id=span.span_id
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Record successful request
            duration = time.time() - start_time
            status_code = response.status_code
            
            self.metrics.record_request(method, endpoint, status_code, duration)
            
            # Add response info to span
            span.tags.update({
                "http.status_code": status_code,
                "http.response_size": response.headers.get("content-length", 0)
            })
            
            # Finish span
            self.tracer.finish_span(span)
            
            # Add trace headers to response
            response.headers["X-Trace-ID"] = span.trace_id
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Record error
            duration = time.time() - start_time
            
            self.metrics.record_request(method, endpoint, 500, duration)
            
            # Finish span with error
            self.tracer.finish_span(span, error=e)
            
            # Log error
            logger.error(
                "Request failed",
                method=method,
                endpoint=endpoint,
                duration=duration,
                error=str(e),
                traceback=traceback.format_exc()
            )
            
            raise
        
        finally:
            # Clear context
            structlog.contextvars.clear_contextvars()
    
    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for metrics"""
        # Replace IDs and UUIDs with placeholders
        import re
        
        # Replace UUIDs
        path = re.sub(
            r'/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
            '/{uuid}',
            path
        )
        
        # Replace numeric IDs
        path = re.sub(r'/\d+', '/{id}', path)
        
        return path


class ObservabilityStack:
    """Complete observability stack"""
    
    def __init__(self):
        self.tracer = DistributedTracer()
        self.metrics = MetricsCollector()
        self.alert_manager = AlertManager(self.metrics)
        self.middleware = None
    
    def setup_middleware(self, app):
        """Setup observability middleware"""
        self.middleware = ObservabilityMiddleware(app, self.tracer, self.metrics)
        return self.middleware
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        health_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "healthy",
            "components": {}
        }
        
        try:
            # Tracing health
            active_spans = len(self.tracer.get_active_spans())
            health_data["components"]["tracing"] = {
                "status": "healthy",
                "active_spans": active_spans
            }
            
            # Metrics health
            metrics_summary = self.metrics.get_metrics_summary()
            health_data["components"]["metrics"] = {
                "status": "healthy",
                "summary": metrics_summary
            }
            
            # Alerts health
            active_alerts = self.alert_manager.get_active_alerts()
            health_data["components"]["alerts"] = {
                "status": "healthy" if not active_alerts else "warning",
                "active_alerts": len(active_alerts),
                "alerts": active_alerts
            }
            
            # Overall status
            if active_alerts:
                critical_alerts = [a for a in active_alerts if a["severity"] == "critical"]
                if critical_alerts:
                    health_data["status"] = "critical"
                else:
                    health_data["status"] = "warning"
            
        except Exception as e:
            health_data["status"] = "error"
            health_data["error"] = str(e)
        
        return health_data
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for observability dashboard"""
        try:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "tracing": {
                    "active_spans": len(self.tracer.get_active_spans()),
                    "recent_spans": [
                        {
                            "trace_id": span.trace_id,
                            "operation": span.operation_name,
                            "duration": span.duration,
                            "status": span.status
                        }
                        for span in self.tracer.get_recent_spans(10)
                    ]
                },
                "metrics": self.metrics.get_metrics_summary(),
                "alerts": {
                    "active": self.alert_manager.get_active_alerts(),
                    "recent_history": self.alert_manager.get_alert_history(10)
                }
            }
        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            return {"error": str(e)}


# Global observability stack instance
_observability_stack: Optional[ObservabilityStack] = None


def get_observability_stack() -> ObservabilityStack:
    """Get global observability stack instance"""
    global _observability_stack
    if _observability_stack is None:
        _observability_stack = ObservabilityStack()
    return _observability_stack
