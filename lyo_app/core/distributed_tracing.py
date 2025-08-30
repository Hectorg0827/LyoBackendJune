"""OpenTelemetry Distributed Tracing for LyoBackend
Enterprise-grade observability with end-to-end request tracing
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, Callable
from functools import wraps
import json
from contextlib import asynccontextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator

from lyo_app.core.config import settings
from lyo_app.core.performance_monitor import get_performance_monitor

logger = logging.getLogger(__name__)

class DistributedTracer:
    """OpenTelemetry distributed tracing system"""

    def __init__(self):
        self.tracer_provider: Optional[TracerProvider] = None
        self.jaeger_exporter: Optional[JaegerExporter] = None
        self._is_initialized = False
        self.service_name = "lyo-backend"
        self.service_version = settings.APP_VERSION

    async def initialize(self):
        """Initialize distributed tracing system"""
        if self._is_initialized:
            return

        try:
            # Set up Jaeger exporter
            self.jaeger_exporter = JaegerExporter(
                agent_host_name=settings.JAEGER_HOST or "jaeger",
                agent_port=int(settings.JAEGER_PORT or 14268),
            )

            # Set up tracer provider
            self.tracer_provider = TracerProvider(
                resource=trace.Resource.create({
                    "service.name": self.service_name,
                    "service.version": self.service_version,
                    "service.environment": settings.ENVIRONMENT,
                })
            )

            # Add span processor
            span_processor = BatchSpanProcessor(self.jaeger_exporter)
            self.tracer_provider.add_span_processor(span_processor)

            # Set global tracer provider
            trace.set_tracer_provider(self.tracer_provider)

            # Set up propagators for distributed tracing
            trace.set_global_textmap(TraceContextPropagator())
            trace.set_global_baggage(W3CBaggagePropagator())

            # Instrument frameworks
            await self._instrument_frameworks()

            self._is_initialized = True
            logger.info("Distributed tracing system initialized")

        except Exception as e:
            logger.error(f"Failed to initialize distributed tracing: {e}")
            # Continue without tracing if initialization fails
            self._is_initialized = False

    async def _instrument_frameworks(self):
        """Instrument key frameworks for automatic tracing"""
        try:
            # Instrument FastAPI
            FastAPIInstrumentor().instrument()

            # Instrument HTTP clients
            HTTPXClientInstrumentor().instrument()

            # Instrument Redis (if available)
            try:
                RedisInstrumentor().instrument()
            except Exception:
                logger.warning("Redis instrumentation failed")

            # Instrument SQLAlchemy (if available)
            try:
                SQLAlchemyInstrumentor().instrument()
            except Exception:
                logger.warning("SQLAlchemy instrumentation failed")

            logger.info("Framework instrumentation completed")

        except Exception as e:
            logger.error(f"Framework instrumentation failed: {e}")

    def get_tracer(self, name: str = "lyo-backend"):
        """Get a tracer instance"""
        if not self._is_initialized:
            return trace.get_tracer(name)
        return trace.get_tracer(name, self.service_version, self.tracer_provider)

    @asynccontextmanager
    async def trace_context(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Context manager for tracing operations"""
        tracer = self.get_tracer()
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)

            try:
                yield span
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
            finally:
                span.end()

    def trace_function(
        self,
        name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """Decorator for tracing functions"""
        def decorator(func: Callable):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                tracer = self.get_tracer()
                span_name = name or f"{func.__module__}.{func.__qualname__}"

                with tracer.start_as_current_span(span_name) as span:
                    if attributes:
                        for key, value in attributes.items():
                            span.set_attribute(key, value)

                    # Add function metadata
                    span.set_attribute("function.name", func.__name__)
                    span.set_attribute("function.module", func.__module__)

                    try:
                        result = await func(*args, **kwargs)
                        span.set_attribute("result.success", True)
                        return result
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.set_attribute("result.success", False)
                        raise
                    finally:
                        span.end()

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                tracer = self.get_tracer()
                span_name = name or f"{func.__module__}.{func.__qualname__}"

                with tracer.start_as_current_span(span_name) as span:
                    if attributes:
                        for key, value in attributes.items():
                            span.set_attribute(key, value)

                    span.set_attribute("function.name", func.__name__)
                    span.set_attribute("function.module", func.__module__)

                    try:
                        result = func(*args, **kwargs)
                        span.set_attribute("result.success", True)
                        return result
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.set_attribute("result.success", False)
                        raise
                    finally:
                        span.end()

            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        return decorator

    async def shutdown(self):
        """Shutdown tracing system"""
        if self.tracer_provider:
            await self.tracer_provider.shutdown()
            logger.info("Distributed tracing system shutdown")

# Global tracer instance
_distributed_tracer = DistributedTracer()

def get_distributed_tracer() -> DistributedTracer:
    """Get global distributed tracer instance"""
    return _distributed_tracer

# Convenience functions
async def initialize_tracing():
    """Initialize distributed tracing system"""
    await _distributed_tracer.initialize()

async def shutdown_tracing():
    """Shutdown distributed tracing system"""
    await _distributed_tracer.shutdown()

def trace_operation(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Decorator for tracing operations"""
    return _distributed_tracer.trace_function(name, attributes)

@asynccontextmanager
async def traced_context(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Context manager for traced operations"""
    async with _distributed_tracer.trace_context(name, attributes) as span:
        yield span

# Custom span utilities
class TracingUtils:
    """Utilities for advanced tracing operations"""

    @staticmethod
    def add_database_span_info(span, operation: str, table: str, query_time: float):
        """Add database operation information to span"""
        span.set_attribute("db.operation", operation)
        span.set_attribute("db.table", table)
        span.set_attribute("db.query_time", query_time)

    @staticmethod
    def add_cache_span_info(span, operation: str, key: str, hit: bool):
        """Add cache operation information to span"""
        span.set_attribute("cache.operation", operation)
        span.set_attribute("cache.key", key)
        span.set_attribute("cache.hit", hit)

    @staticmethod
    def add_ai_span_info(span, model: str, tokens: int, processing_time: float):
        """Add AI processing information to span"""
        span.set_attribute("ai.model", model)
        span.set_attribute("ai.tokens", tokens)
        span.set_attribute("ai.processing_time", processing_time)

    @staticmethod
    def add_user_context(span, user_id: Optional[str], session_id: Optional[str]):
        """Add user context to span"""
        if user_id:
            span.set_attribute("user.id", user_id)
        if session_id:
            span.set_attribute("session.id", session_id)

    @staticmethod
    def add_business_metrics(span, metrics: Dict[str, Any]):
        """Add business metrics to span"""
        for key, value in metrics.items():
            span.set_attribute(f"business.{key}", value)

# Performance correlation utilities
class PerformanceCorrelator:
    """Correlate performance metrics with traces"""

    def __init__(self):
        self.performance_monitor = get_performance_monitor()
        self.trace_buffer = []

    async def correlate_performance_with_trace(
        self,
        trace_id: str,
        performance_data: Dict[str, Any]
    ):
        """Correlate performance metrics with trace data"""
        correlation = {
            "trace_id": trace_id,
            "timestamp": time.time(),
            "performance": performance_data,
            "correlation_id": f"corr_{int(time.time())}_{trace_id[:8]}"
        }

        self.trace_buffer.append(correlation)

        # Keep buffer size manageable
        if len(self.trace_buffer) > 1000:
            self.trace_buffer = self.trace_buffer[-500:]

        return correlation

    def get_performance_correlations(
        self,
        time_window: int = 3600
    ) -> List[Dict[str, Any]]:
        """Get performance correlations within time window"""
        cutoff_time = time.time() - time_window
        return [
            corr for corr in self.trace_buffer
            if corr["timestamp"] > cutoff_time
        ]

    def analyze_performance_patterns(self) -> Dict[str, Any]:
        """Analyze performance patterns from correlated data"""
        correlations = self.get_performance_correlations()

        if not correlations:
            return {"status": "no_data"}

        # Analyze patterns
        slow_traces = [
            corr for corr in correlations
            if corr["performance"].get("response_time", 0) > 1.0
        ]

        error_traces = [
            corr for corr in correlations
            if corr["performance"].get("status_code", 200) >= 400
        ]

        return {
            "total_traces": len(correlations),
            "slow_traces": len(slow_traces),
            "error_traces": len(error_traces),
            "slow_trace_percentage": len(slow_traces) / len(correlations) * 100,
            "error_rate": len(error_traces) / len(correlations) * 100,
            "analysis_timestamp": time.time()
        }

# Global performance correlator
performance_correlator = PerformanceCorrelator()

# Integration with existing systems
async def integrate_tracing_with_monitoring():
    """Integrate tracing with existing performance monitoring"""
    tracer = get_distributed_tracer()

    # Add tracing to performance monitoring
    original_track_api = get_performance_monitor().track_api_request

    async def traced_track_api(method, endpoint, status_code, duration):
        # Call original function
        await original_track_api(method, endpoint, status_code, duration)

        # Add trace correlation
        current_span = trace.get_current_span()
        if current_span.is_recording():
            current_span.set_attribute("api.method", method)
            current_span.set_attribute("api.endpoint", endpoint)
            current_span.set_attribute("api.status_code", status_code)
            current_span.set_attribute("api.duration", duration)

            # Correlate with performance data
            await performance_correlator.correlate_performance_with_trace(
                current_span.get_span_context().trace_id,
                {
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "response_time": duration
                }
            )

    # Replace the function
    get_performance_monitor().track_api_request = traced_track_api

    logger.info("Tracing integrated with performance monitoring")

# Health check for tracing system
async def get_tracing_health_status() -> Dict[str, Any]:
    """Get tracing system health status"""
    tracer = get_distributed_tracer()

    return {
        "status": "healthy" if tracer._is_initialized else "disabled",
        "service_name": tracer.service_name,
        "service_version": tracer.service_version,
        "jaeger_host": settings.JAEGER_HOST,
        "jaeger_port": settings.JAEGER_PORT,
        "performance_correlations": performance_correlator.analyze_performance_patterns(),
        "timestamp": time.time()
    }
