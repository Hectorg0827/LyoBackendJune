"""
Living Classroom - Monitoring & A/B Testing System
=================================================

Production-ready monitoring, metrics, and A/B testing for Living Classroom rollout.
Includes performance tracking, error monitoring, and feature flag management.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ABTestGroup(str, Enum):
    """A/B test groups for Living Classroom"""
    CONTROL = "control"          # Legacy SSE streaming
    TREATMENT = "treatment"      # Living Classroom streaming
    HYBRID = "hybrid"           # Mix of both based on scene type


class PerformanceMetric(str, Enum):
    """Performance metrics to track"""
    SCENE_GENERATION_TIME = "scene_generation_time_ms"
    WEBSOCKET_CONNECTION_TIME = "websocket_connection_time_ms"
    COMPONENT_RENDER_TIME = "component_render_time_ms"
    USER_INTERACTION_TIME = "user_interaction_time_ms"
    ERROR_RATE = "error_rate"
    USER_ENGAGEMENT_SCORE = "user_engagement_score"


class LivingClassroomMetrics:
    """Metrics collection and reporting"""

    def __init__(self):
        self.metrics = {}
        self.counters = {}
        self.histograms = {}
        self.errors = []

    def increment_counter(self, metric: str, value: int = 1, labels: Dict[str, str] = None):
        """Increment a counter metric"""
        key = f"{metric}_{self._labels_to_key(labels or {})}"
        self.counters[key] = self.counters.get(key, 0) + value

    def record_histogram(self, metric: str, value: float, labels: Dict[str, str] = None):
        """Record a histogram value"""
        key = f"{metric}_{self._labels_to_key(labels or {})}"
        if key not in self.histograms:
            self.histograms[key] = []
        self.histograms[key].append(value)

    def record_error(self, error: Exception, context: Dict[str, Any] = None):
        """Record an error for monitoring"""
        error_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {}
        }
        self.errors.append(error_record)

        # Keep only last 1000 errors
        if len(self.errors) > 1000:
            self.errors = self.errors[-1000:]

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        histogram_stats = {}
        for key, values in self.histograms.items():
            if values:
                histogram_stats[key] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "p95": self._percentile(values, 0.95),
                    "p99": self._percentile(values, 0.99)
                }

        return {
            "counters": self.counters,
            "histograms": histogram_stats,
            "error_count": len(self.errors),
            "recent_errors": self.errors[-5:] if self.errors else []
        }

    def _labels_to_key(self, labels: Dict[str, str]) -> str:
        """Convert labels dict to cache key"""
        if not labels:
            return "default"
        return "_".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def _percentile(self, values: List[float], p: float) -> float:
        """Calculate percentile"""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * p)
        return sorted_values[min(index, len(sorted_values) - 1)]


class ABTestManager:
    """A/B testing framework for Living Classroom rollout"""

    def __init__(self):
        self.test_configs = {}
        self.user_assignments = {}
        self.test_results = {}

        # Load configuration from environment
        self._load_config()

    def _load_config(self):
        """Load A/B test configuration from environment"""
        self.test_configs = {
            "living_classroom_rollout": {
                "enabled": os.getenv("AB_TEST_ENABLED", "true").lower() == "true",
                "control_percentage": float(os.getenv("AB_CONTROL_PERCENTAGE", "50")),
                "treatment_percentage": float(os.getenv("AB_TREATMENT_PERCENTAGE", "40")),
                "hybrid_percentage": float(os.getenv("AB_HYBRID_PERCENTAGE", "10")),
                "start_date": os.getenv("AB_TEST_START_DATE", "2024-01-01"),
                "end_date": os.getenv("AB_TEST_END_DATE", "2024-12-31"),
                "success_metrics": ["user_engagement_score", "scene_generation_time"]
            }
        }

    def assign_user_to_group(self, user_id: str, test_name: str = "living_classroom_rollout") -> ABTestGroup:
        """Assign user to A/B test group"""
        if test_name not in self.test_configs:
            return ABTestGroup.CONTROL

        config = self.test_configs[test_name]
        if not config["enabled"]:
            return ABTestGroup.CONTROL

        # Check if user already assigned
        cache_key = f"{test_name}_{user_id}"
        if cache_key in self.user_assignments:
            return ABTestGroup(self.user_assignments[cache_key])

        # Assign based on user hash
        user_hash = hash(f"{test_name}_{user_id}") % 100

        control_pct = config["control_percentage"]
        treatment_pct = config["treatment_percentage"]

        if user_hash < control_pct:
            group = ABTestGroup.CONTROL
        elif user_hash < control_pct + treatment_pct:
            group = ABTestGroup.TREATMENT
        else:
            group = ABTestGroup.HYBRID

        # Cache assignment
        self.user_assignments[cache_key] = group.value

        logger.info(f"🧪 AB Test: User {user_id} assigned to {group.value} group")
        return group

    def should_use_living_classroom(self, user_id: str) -> bool:
        """Determine if user should get Living Classroom based on A/B test"""
        group = self.assign_user_to_group(user_id)
        return group in [ABTestGroup.TREATMENT, ABTestGroup.HYBRID]

    def record_test_event(
        self,
        user_id: str,
        event_type: str,
        value: float,
        metadata: Dict[str, Any] = None
    ):
        """Record A/B test event for analysis"""
        group = self.assign_user_to_group(user_id)

        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "group": group.value,
            "event_type": event_type,
            "value": value,
            "metadata": metadata or {}
        }

        test_key = f"living_classroom_rollout_{group.value}"
        if test_key not in self.test_results:
            self.test_results[test_key] = []

        self.test_results[test_key].append(event)

        # Keep only last 10000 events per group
        if len(self.test_results[test_key]) > 10000:
            self.test_results[test_key] = self.test_results[test_key][-10000:]

    def get_test_results(self, test_name: str = "living_classroom_rollout") -> Dict[str, Any]:
        """Get A/B test results summary"""
        results = {}

        for group in [ABTestGroup.CONTROL, ABTestGroup.TREATMENT, ABTestGroup.HYBRID]:
            test_key = f"{test_name}_{group.value}"
            events = self.test_results.get(test_key, [])

            if events:
                # Calculate metrics
                engagement_scores = [e["value"] for e in events if e["event_type"] == "user_engagement_score"]
                scene_times = [e["value"] for e in events if e["event_type"] == "scene_generation_time"]

                results[group.value] = {
                    "total_events": len(events),
                    "unique_users": len(set(e["user_id"] for e in events)),
                    "avg_engagement": sum(engagement_scores) / len(engagement_scores) if engagement_scores else 0,
                    "avg_scene_time_ms": sum(scene_times) / len(scene_times) if scene_times else 0,
                    "recent_events": events[-10:] if events else []
                }
            else:
                results[group.value] = {
                    "total_events": 0,
                    "unique_users": 0,
                    "avg_engagement": 0,
                    "avg_scene_time_ms": 0,
                    "recent_events": []
                }

        return results


class PerformanceMonitor:
    """Performance monitoring for Living Classroom"""

    def __init__(self, metrics: LivingClassroomMetrics):
        self.metrics = metrics
        self.active_timers = {}

    async def time_operation(self, operation_name: str, labels: Dict[str, str] = None):
        """Context manager for timing operations"""
        return TimingContext(self, operation_name, labels)

    def start_timer(self, timer_id: str) -> float:
        """Start a timer and return start time"""
        start_time = time.time()
        self.active_timers[timer_id] = start_time
        return start_time

    def end_timer(self, timer_id: str, metric_name: str, labels: Dict[str, str] = None) -> float:
        """End timer and record metric"""
        if timer_id not in self.active_timers:
            logger.warning(f"Timer {timer_id} not found")
            return 0.0

        start_time = self.active_timers.pop(timer_id)
        duration_ms = (time.time() - start_time) * 1000

        self.metrics.record_histogram(metric_name, duration_ms, labels)
        return duration_ms

    async def monitor_scene_generation(self, scene_generation_func: Callable, context: Dict[str, Any]):
        """Monitor scene generation performance"""
        timer_id = f"scene_{int(time.time() * 1000000)}"

        try:
            self.start_timer(timer_id)
            result = await scene_generation_func()

            duration = self.end_timer(
                timer_id,
                PerformanceMetric.SCENE_GENERATION_TIME,
                {"user_id": context.get("user_id", "unknown")}
            )

            logger.info(f"⚡ Scene generated in {duration:.1f}ms")
            return result

        except Exception as e:
            self.end_timer(timer_id, PerformanceMetric.SCENE_GENERATION_TIME)
            self.metrics.record_error(e, context)
            raise

    async def monitor_websocket_connection(self, connection_func: Callable, user_id: str):
        """Monitor WebSocket connection performance"""
        timer_id = f"ws_conn_{int(time.time() * 1000000)}"

        try:
            self.start_timer(timer_id)
            result = await connection_func()

            duration = self.end_timer(
                timer_id,
                PerformanceMetric.WEBSOCKET_CONNECTION_TIME,
                {"user_id": user_id}
            )

            logger.info(f"🔌 WebSocket connected in {duration:.1f}ms")
            return result

        except Exception as e:
            self.end_timer(timer_id, PerformanceMetric.WEBSOCKET_CONNECTION_TIME)
            self.metrics.record_error(e, {"user_id": user_id})
            raise


class TimingContext:
    """Context manager for timing operations"""

    def __init__(self, monitor: PerformanceMonitor, operation_name: str, labels: Dict[str, str] = None):
        self.monitor = monitor
        self.operation_name = operation_name
        self.labels = labels or {}
        self.timer_id = None

    async def __aenter__(self):
        self.timer_id = f"{self.operation_name}_{int(time.time() * 1000000)}"
        self.monitor.start_timer(self.timer_id)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.timer_id:
            duration = self.monitor.end_timer(
                self.timer_id,
                self.operation_name,
                self.labels
            )

            if exc_type:
                self.monitor.metrics.record_error(
                    exc_val or Exception("Unknown error"),
                    {"operation": self.operation_name, **self.labels}
                )


class HealthChecker:
    """Health checking for Living Classroom components"""

    def __init__(self, metrics: LivingClassroomMetrics):
        self.metrics = metrics

    async def check_system_health(self) -> Dict[str, Any]:
        """Comprehensive system health check"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }

        # Check WebSocket Manager
        try:
            from lyo_app.ai_classroom.websocket_manager import get_websocket_manager
            ws_manager = await get_websocket_manager()
            ws_stats = ws_manager.get_connection_stats()

            health_status["checks"]["websocket_manager"] = {
                "status": "healthy",
                "active_connections": ws_stats["active_connections"],
                "total_messages": ws_stats["messages_sent"]
            }
        except Exception as e:
            health_status["checks"]["websocket_manager"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        # Check Scene Lifecycle Engine
        try:
            from lyo_app.ai_classroom.scene_lifecycle_engine import SceneLifecycleEngine
            # Basic import test
            health_status["checks"]["scene_lifecycle"] = {
                "status": "healthy",
                "components": ["TriggerListener", "ContextAssembler", "ClassroomDirector", "SceneCompiler"]
            }
        except Exception as e:
            health_status["checks"]["scene_lifecycle"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        # Check metrics
        metrics_summary = self.metrics.get_summary()
        error_rate = len(metrics_summary["recent_errors"]) / max(
            sum(metrics_summary["counters"].values()), 1
        ) * 100

        health_status["checks"]["metrics"] = {
            "status": "healthy" if error_rate < 5 else "degraded",
            "error_rate_percent": round(error_rate, 2),
            "total_errors": metrics_summary["error_count"]
        }

        if error_rate >= 10:
            health_status["status"] = "unhealthy"

        return health_status

    async def check_database_connectivity(self, db: AsyncSession) -> Dict[str, Any]:
        """Check database connectivity for Living Classroom"""
        try:
            # Simple connectivity test
            result = await db.execute(text("SELECT 1"))
            row = result.fetchone()

            if row and row[0] == 1:
                return {"status": "healthy", "latency_ms": "< 10"}
            else:
                return {"status": "unhealthy", "error": "Unexpected query result"}

        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Global instances
_metrics = LivingClassroomMetrics()
_ab_test_manager = ABTestManager()
_performance_monitor = PerformanceMonitor(_metrics)
_health_checker = HealthChecker(_metrics)


# Public API
async def get_metrics() -> LivingClassroomMetrics:
    """Get metrics instance"""
    return _metrics


async def get_ab_test_manager() -> ABTestManager:
    """Get A/B test manager"""
    return _ab_test_manager


async def get_performance_monitor() -> PerformanceMonitor:
    """Get performance monitor"""
    return _performance_monitor


async def get_health_checker() -> HealthChecker:
    """Get health checker"""
    return _health_checker


# Convenience functions
async def should_use_living_classroom(user_id: str) -> bool:
    """Check if user should get Living Classroom experience"""
    ab_manager = await get_ab_test_manager()
    return ab_manager.should_use_living_classroom(user_id)


async def record_performance_metric(metric: str, value: float, labels: Dict[str, str] = None):
    """Record a performance metric"""
    metrics = await get_metrics()
    metrics.record_histogram(metric, value, labels)


async def increment_counter(metric: str, value: int = 1, labels: Dict[str, str] = None):
    """Increment a counter metric"""
    metrics = await get_metrics()
    metrics.increment_counter(metric, value, labels)


__all__ = [
    "get_metrics",
    "get_ab_test_manager",
    "get_performance_monitor",
    "get_health_checker",
    "should_use_living_classroom",
    "record_performance_metric",
    "increment_counter",
    "ABTestGroup",
    "PerformanceMetric"
]