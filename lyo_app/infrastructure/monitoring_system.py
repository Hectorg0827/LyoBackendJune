#!/usr/bin/env python3
"""
Comprehensive Monitoring System for Lyo Platform
Real-time system monitoring, alerting, performance analytics,
and automated health checks across all platform components
"""

from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import time
import json
import psutil
import threading
from datetime import datetime, timedelta
from collections import deque, defaultdict
import statistics
import logging


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricType(Enum):
    """Types of metrics being monitored"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class ComponentStatus(Enum):
    """Component health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class MetricPoint:
    """Single metric data point"""
    timestamp: datetime
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    component: str = "system"


@dataclass
class Alert:
    """System alert"""
    id: str
    level: AlertLevel
    component: str
    message: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentHealth:
    """Health status of a system component"""
    component_name: str
    status: ComponentStatus
    health_score: float
    last_check: datetime
    response_time: Optional[float] = None
    error_rate: float = 0.0
    uptime_percentage: float = 100.0
    metrics: Dict[str, float] = field(default_factory=dict)
    alerts: List[Alert] = field(default_factory=list)


@dataclass
class SystemSnapshot:
    """Complete system health snapshot"""
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_io: Dict[str, float]
    active_connections: int
    request_rate: float
    error_rate: float
    response_time_p95: float
    component_health: Dict[str, ComponentHealth]
    active_alerts: int
    overall_health_score: float


class MonitoringSystem:
    """Comprehensive system monitoring and alerting"""

    def __init__(self, alert_handlers: Optional[List[Callable]] = None):
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.alerts: Dict[str, Alert] = {}
        self.component_health: Dict[str, ComponentHealth] = {}
        self.alert_handlers = alert_handlers or []
        self.thresholds: Dict[str, Dict[str, float]] = {}
        self.monitoring_active = False
        self.monitoring_interval = 30  # seconds
        self.monitoring_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()

        # Initialize default thresholds
        self._initialize_default_thresholds()

        # Setup logging
        self.logger = logging.getLogger(__name__)

    def _initialize_default_thresholds(self):
        """Initialize default monitoring thresholds"""
        self.thresholds = {
            "cpu_usage": {"warning": 70.0, "critical": 90.0},
            "memory_usage": {"warning": 80.0, "critical": 95.0},
            "disk_usage": {"warning": 85.0, "critical": 95.0},
            "error_rate": {"warning": 5.0, "critical": 10.0},
            "response_time_p95": {"warning": 1000.0, "critical": 3000.0},  # milliseconds
            "database_connections": {"warning": 80.0, "critical": 95.0}  # percentage of pool
        }

    def record_metric(self, metric_name: str, value: float,
                     component: str = "system", tags: Dict[str, str] = None):
        """Record a metric value"""
        with self._lock:
            metric_point = MetricPoint(
                timestamp=datetime.utcnow(),
                value=value,
                component=component,
                tags=tags or {}
            )

            self.metrics[metric_name].append(metric_point)

            # Check for threshold violations
            self._check_thresholds(metric_name, value, component)

    def _check_thresholds(self, metric_name: str, value: float, component: str):
        """Check if metric violates thresholds and generate alerts"""
        if metric_name not in self.thresholds:
            return

        thresholds = self.thresholds[metric_name]
        alert_level = None

        if value >= thresholds.get("critical", float('inf')):
            alert_level = AlertLevel.CRITICAL
        elif value >= thresholds.get("warning", float('inf')):
            alert_level = AlertLevel.WARNING

        if alert_level:
            alert_id = f"{component}_{metric_name}_{alert_level.value}"

            # Don't create duplicate alerts
            if alert_id not in self.alerts or self.alerts[alert_id].resolved:
                alert = Alert(
                    id=alert_id,
                    level=alert_level,
                    component=component,
                    message=f"{metric_name} threshold exceeded: {value}",
                    timestamp=datetime.utcnow(),
                    metadata={"metric": metric_name, "value": value, "threshold": thresholds.get(alert_level.value)}
                )

                self.alerts[alert_id] = alert
                self._trigger_alert_handlers(alert)

    def _trigger_alert_handlers(self, alert: Alert):
        """Trigger registered alert handlers"""
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                self.logger.error(f"Alert handler failed: {e}")

    def register_component(self, component_name: str,
                         health_check_func: Optional[Callable] = None):
        """Register a component for health monitoring"""
        self.component_health[component_name] = ComponentHealth(
            component_name=component_name,
            status=ComponentStatus.UNKNOWN,
            health_score=0.0,
            last_check=datetime.utcnow()
        )

    async def check_component_health(self, component_name: str,
                                   health_check_func: Optional[Callable] = None) -> ComponentHealth:
        """Check health of a specific component"""
        if component_name not in self.component_health:
            self.register_component(component_name)

        component = self.component_health[component_name]
        start_time = time.time()

        try:
            if health_check_func:
                # Execute custom health check
                health_result = await health_check_func()
                if isinstance(health_result, dict):
                    component.health_score = health_result.get("score", 100.0)
                    component.status = ComponentStatus(health_result.get("status", "healthy"))
                    component.metrics.update(health_result.get("metrics", {}))
                else:
                    # Assume boolean result
                    component.health_score = 100.0 if health_result else 0.0
                    component.status = ComponentStatus.HEALTHY if health_result else ComponentStatus.UNHEALTHY
            else:
                # Basic health check - assume healthy if reachable
                component.health_score = 100.0
                component.status = ComponentStatus.HEALTHY

            component.response_time = (time.time() - start_time) * 1000  # milliseconds

        except Exception as e:
            component.health_score = 0.0
            component.status = ComponentStatus.UNHEALTHY
            component.response_time = (time.time() - start_time) * 1000

            # Create alert for component failure
            alert = Alert(
                id=f"{component_name}_health_check_failed",
                level=AlertLevel.ERROR,
                component=component_name,
                message=f"Health check failed: {str(e)}",
                timestamp=datetime.utcnow(),
                metadata={"error": str(e)}
            )
            self.alerts[alert.id] = alert
            self._trigger_alert_handlers(alert)

        component.last_check = datetime.utcnow()
        return component

    async def collect_system_metrics(self) -> Dict[str, float]:
        """Collect system-level metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory metrics
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent

            # Network metrics
            network_io = psutil.net_io_counters()

            # Process metrics
            process_count = len(psutil.pids())

            metrics = {
                "cpu_usage": cpu_percent,
                "memory_usage": memory_percent,
                "disk_usage": disk_percent,
                "network_bytes_sent": network_io.bytes_sent,
                "network_bytes_recv": network_io.bytes_recv,
                "active_processes": process_count
            }

            # Record metrics
            for metric_name, value in metrics.items():
                self.record_metric(metric_name, value, "system")

            return metrics

        except Exception as e:
            self.logger.error(f"Failed to collect system metrics: {e}")
            return {}

    async def generate_system_snapshot(self) -> SystemSnapshot:
        """Generate comprehensive system health snapshot"""
        # Collect current system metrics
        system_metrics = await self.collect_system_metrics()

        # Calculate derived metrics
        response_times = []
        error_rates = []

        for component_name, component in self.component_health.items():
            if component.response_time:
                response_times.append(component.response_time)
            error_rates.append(component.error_rate)

        response_time_p95 = statistics.quantiles(response_times, n=20)[18] if response_times else 0.0
        avg_error_rate = statistics.mean(error_rates) if error_rates else 0.0

        # Count active alerts
        active_alerts = len([a for a in self.alerts.values() if not a.resolved])

        # Calculate overall health score
        component_scores = [c.health_score for c in self.component_health.values()]
        overall_health = statistics.mean(component_scores) if component_scores else 100.0

        # Apply penalties for system issues
        if system_metrics.get("cpu_usage", 0) > 80:
            overall_health *= 0.9
        if system_metrics.get("memory_usage", 0) > 80:
            overall_health *= 0.9
        if active_alerts > 0:
            overall_health *= max(0.5, 1.0 - (active_alerts * 0.1))

        return SystemSnapshot(
            timestamp=datetime.utcnow(),
            cpu_usage=system_metrics.get("cpu_usage", 0),
            memory_usage=system_metrics.get("memory_usage", 0),
            disk_usage=system_metrics.get("disk_usage", 0),
            network_io={
                "bytes_sent": system_metrics.get("network_bytes_sent", 0),
                "bytes_recv": system_metrics.get("network_bytes_recv", 0)
            },
            active_connections=system_metrics.get("active_processes", 0),
            request_rate=0.0,  # Would be calculated from application metrics
            error_rate=avg_error_rate,
            response_time_p95=response_time_p95,
            component_health=self.component_health.copy(),
            active_alerts=active_alerts,
            overall_health_score=overall_health
        )

    async def start_monitoring(self):
        """Start continuous monitoring"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("Monitoring system started")

    async def stop_monitoring(self):
        """Stop continuous monitoring"""
        self.monitoring_active = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Monitoring system stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Collect system metrics
                await self.collect_system_metrics()

                # Check component health
                for component_name in list(self.component_health.keys()):
                    await self.check_component_health(component_name)

                # Cleanup old metrics (keep last hour)
                cutoff_time = datetime.utcnow() - timedelta(hours=1)
                self._cleanup_old_metrics(cutoff_time)

                # Sleep until next monitoring cycle
                await asyncio.sleep(self.monitoring_interval)

            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(5)  # Short delay on error

    def _cleanup_old_metrics(self, cutoff_time: datetime):
        """Remove metrics older than cutoff time"""
        with self._lock:
            for metric_name in list(self.metrics.keys()):
                metric_deque = self.metrics[metric_name]
                # Remove old entries (deque automatically limits size to 1000)
                while metric_deque and metric_deque[0].timestamp < cutoff_time:
                    metric_deque.popleft()

    def get_metric_history(self, metric_name: str,
                          time_window: int = 3600) -> List[MetricPoint]:
        """Get metric history for specified time window (seconds)"""
        cutoff_time = datetime.utcnow() - timedelta(seconds=time_window)

        with self._lock:
            if metric_name not in self.metrics:
                return []

            return [
                point for point in self.metrics[metric_name]
                if point.timestamp >= cutoff_time
            ]

    def get_active_alerts(self, component: Optional[str] = None) -> List[Alert]:
        """Get active alerts, optionally filtered by component"""
        active_alerts = [
            alert for alert in self.alerts.values()
            if not alert.resolved
        ]

        if component:
            active_alerts = [a for a in active_alerts if a.component == component]

        return sorted(active_alerts, key=lambda x: x.timestamp, reverse=True)

    def resolve_alert(self, alert_id: str) -> bool:
        """Manually resolve an alert"""
        if alert_id in self.alerts:
            alert = self.alerts[alert_id]
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
            return True
        return False

    def set_threshold(self, metric_name: str, warning_value: float,
                     critical_value: float):
        """Set custom thresholds for a metric"""
        self.thresholds[metric_name] = {
            "warning": warning_value,
            "critical": critical_value
        }

    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """Add custom alert handler"""
        self.alert_handlers.append(handler)

    async def get_performance_analytics(self, time_window: int = 3600) -> Dict[str, Any]:
        """Generate performance analytics report"""
        cutoff_time = datetime.utcnow() - timedelta(seconds=time_window)

        analytics = {
            "time_window_hours": time_window / 3600,
            "system_performance": {},
            "component_performance": {},
            "alert_summary": {},
            "trends": {}
        }

        # System performance metrics
        for metric_name in ["cpu_usage", "memory_usage", "disk_usage"]:
            history = self.get_metric_history(metric_name, time_window)
            if history:
                values = [p.value for p in history]
                analytics["system_performance"][metric_name] = {
                    "current": values[-1] if values else 0,
                    "average": statistics.mean(values),
                    "max": max(values),
                    "min": min(values),
                    "p95": statistics.quantiles(values, n=20)[18] if len(values) > 20 else max(values)
                }

        # Component performance
        for component_name, component in self.component_health.items():
            analytics["component_performance"][component_name] = {
                "health_score": component.health_score,
                "status": component.status.value,
                "response_time": component.response_time,
                "error_rate": component.error_rate,
                "uptime_percentage": component.uptime_percentage
            }

        # Alert summary
        all_alerts = list(self.alerts.values())
        recent_alerts = [a for a in all_alerts if a.timestamp >= cutoff_time]

        analytics["alert_summary"] = {
            "total_alerts": len(recent_alerts),
            "active_alerts": len([a for a in recent_alerts if not a.resolved]),
            "critical_alerts": len([a for a in recent_alerts if a.level == AlertLevel.CRITICAL]),
            "warning_alerts": len([a for a in recent_alerts if a.level == AlertLevel.WARNING]),
            "alert_rate": len(recent_alerts) / (time_window / 3600)  # alerts per hour
        }

        return analytics

    def export_metrics(self, format: str = "json") -> str:
        """Export metrics in specified format"""
        snapshot = asyncio.create_task(self.generate_system_snapshot())

        # Get snapshot (simplified for synchronous call)
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {},
            "alerts": [
                {
                    "id": alert.id,
                    "level": alert.level.value,
                    "component": alert.component,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "resolved": alert.resolved
                }
                for alert in self.alerts.values()
            ],
            "component_health": {
                name: {
                    "status": component.status.value,
                    "health_score": component.health_score,
                    "response_time": component.response_time
                }
                for name, component in self.component_health.items()
            }
        }

        # Export recent metrics
        for metric_name, metric_deque in self.metrics.items():
            if metric_deque:
                recent_points = list(metric_deque)[-10:]  # Last 10 points
                data["metrics"][metric_name] = [
                    {
                        "timestamp": point.timestamp.isoformat(),
                        "value": point.value,
                        "component": point.component
                    }
                    for point in recent_points
                ]

        if format.lower() == "json":
            return json.dumps(data, indent=2)
        else:
            return str(data)


# Global monitoring system instance
monitoring_system = MonitoringSystem()


# Convenience functions and decorators
def record_metric(metric_name: str, value: float, component: str = "system"):
    """Record a metric value"""
    monitoring_system.record_metric(metric_name, value, component)


def monitor_performance(component_name: str):
    """Decorator to monitor function performance"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000
                record_metric(f"{component_name}_response_time", execution_time, component_name)
                record_metric(f"{component_name}_success_count", 1, component_name)
                return result
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                record_metric(f"{component_name}_response_time", execution_time, component_name)
                record_metric(f"{component_name}_error_count", 1, component_name)
                raise

        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000
                record_metric(f"{component_name}_response_time", execution_time, component_name)
                record_metric(f"{component_name}_success_count", 1, component_name)
                return result
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                record_metric(f"{component_name}_response_time", execution_time, component_name)
                record_metric(f"{component_name}_error_count", 1, component_name)
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


async def start_monitoring():
    """Start the global monitoring system"""
    await monitoring_system.start_monitoring()


async def stop_monitoring():
    """Stop the global monitoring system"""
    await monitoring_system.stop_monitoring()


if __name__ == "__main__":
    # Example usage and testing
    async def demo_monitoring_system():
        print("🎯 MONITORING SYSTEM DEMONSTRATION")
        print("=" * 70)

        # Setup monitoring
        monitor = MonitoringSystem()

        # Add custom alert handler
        def custom_alert_handler(alert: Alert):
            print(f"🚨 ALERT: {alert.level.value.upper()} - {alert.component}: {alert.message}")

        monitor.add_alert_handler(custom_alert_handler)

        # Register components
        print("📋 Registering system components...")
        components = ["api_server", "database", "cache", "ai_service", "file_storage"]

        for component in components:
            monitor.register_component(component)
            print(f"   ✅ Registered: {component}")

        # Simulate some metrics
        print("\\n📊 Simulating system metrics...")

        # Normal metrics
        monitor.record_metric("cpu_usage", 45.2, "system")
        monitor.record_metric("memory_usage", 62.8, "system")
        monitor.record_metric("response_time", 150.5, "api_server")

        # Metrics that trigger warnings
        monitor.record_metric("cpu_usage", 75.0, "system")  # Warning threshold
        monitor.record_metric("error_rate", 8.5, "api_server")  # Warning threshold

        # Critical metric
        monitor.record_metric("memory_usage", 96.0, "system")  # Critical threshold

        print("   📈 Recorded various metrics with threshold violations")

        # Check component health
        print("\\n🏥 Checking component health...")

        async def mock_health_check():
            return {"score": 95.0, "status": "healthy", "metrics": {"uptime": 99.9}}

        for component in components[:3]:  # Check first 3 components
            health = await monitor.check_component_health(component, mock_health_check)
            print(f"   💚 {component}: {health.status.value} ({health.health_score}/100)")

        # Generate system snapshot
        print("\\n📸 Generating system snapshot...")
        snapshot = await monitor.generate_system_snapshot()
        print(f"   🏆 Overall Health: {snapshot.overall_health_score:.1f}/100")
        print(f"   💻 CPU Usage: {snapshot.cpu_usage:.1f}%")
        print(f"   💾 Memory Usage: {snapshot.memory_usage:.1f}%")
        print(f"   🚨 Active Alerts: {snapshot.active_alerts}")

        # Show active alerts
        print("\\n🚨 Active Alerts:")
        active_alerts = monitor.get_active_alerts()
        for alert in active_alerts[:5]:  # Show first 5 alerts
            print(f"   {alert.level.value.upper()}: {alert.component} - {alert.message}")

        # Performance analytics
        print("\\n📈 Performance Analytics...")
        analytics = await monitor.get_performance_analytics(3600)
        print(f"   📊 System Performance Summary:")
        for metric, stats in analytics["system_performance"].items():
            print(f"      {metric}: avg={stats['average']:.1f}, max={stats['max']:.1f}")

        # Start monitoring (brief demo)
        print("\\n🔄 Starting continuous monitoring...")
        await monitor.start_monitoring()
        print("   ✅ Monitoring system active")

        # Run for a few seconds
        await asyncio.sleep(3)

        await monitor.stop_monitoring()
        print("   ⏹️  Monitoring system stopped")

        # Export metrics
        print("\\n📤 Exporting metrics...")
        exported_data = monitor.export_metrics("json")
        metrics_size = len(exported_data)
        print(f"   📄 Exported {metrics_size} bytes of monitoring data")

        print(f"\\n🎉 MONITORING SYSTEM READY")
        print("   ✅ Real-time metric collection")
        print("   ✅ Intelligent alerting system")
        print("   ✅ Component health monitoring")
        print("   ✅ Performance analytics")
        print("   ✅ System snapshots")
        print("   ✅ Threshold-based alerting")

    # Run demo if called directly
    asyncio.run(demo_monitoring_system())