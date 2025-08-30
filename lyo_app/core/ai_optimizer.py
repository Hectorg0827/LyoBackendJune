"""AI-Powered Optimization System for LyoBackend
Machine learning-driven performance optimization and predictive scaling
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict, deque

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error

from lyo_app.core.distributed_tracing import DistributedTracingManager
from lyo_app.core.performance_monitor import PerformanceMonitor
from lyo_app.core.cache import CacheManager

logger = logging.getLogger(__name__)

@dataclass
class OptimizationMetrics:
    """Metrics for AI optimization decisions"""
    timestamp: datetime
    cpu_utilization: float
    memory_utilization: float
    request_rate: float
    response_time_p95: float
    error_rate: float
    active_connections: int
    cache_hit_rate: float
    db_connection_pool_usage: float
    trace_count: int
    predicted_load: float = 0.0
    optimization_score: float = 0.0

@dataclass
class OptimizationDecision:
    """AI-driven optimization decision"""
    timestamp: datetime
    decision_type: str  # 'scale_up', 'scale_down', 'cache_optimize', 'db_optimize'
    confidence: float
    expected_impact: float
    reasoning: str
    actions: List[Dict[str, Any]]
    rollback_plan: Optional[Dict[str, Any]] = None

class PredictiveScaler:
    """Predictive scaling using machine learning"""

    def __init__(self, lookback_hours: int = 24):
        self.lookback_hours = lookback_hours
        self.metrics_history = deque(maxlen=lookback_hours * 60)  # 1 minute intervals
        self.scaler = StandardScaler()
        self.model = RandomForestRegressor(
            n_estimators=100,
            random_state=42,
            n_jobs=-1
        )
        self.is_trained = False
        self.feature_columns = [
            'cpu_utilization', 'memory_utilization', 'request_rate',
            'response_time_p95', 'error_rate', 'active_connections',
            'cache_hit_rate', 'db_connection_pool_usage', 'hour_of_day',
            'day_of_week', 'is_peak_hour'
        ]

    def add_metrics(self, metrics: OptimizationMetrics):
        """Add metrics to training data"""
        self.metrics_history.append(metrics)

    def _prepare_features(self, metrics_list: List[OptimizationMetrics]) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare features and targets for training"""
        if len(metrics_list) < 60:  # Need at least 1 hour of data
            return np.array([]), np.array([])

        data = []
        targets = []

        for i, metrics in enumerate(metrics_list):
            if i >= 30:  # Use 30 minutes of history to predict next value
                # Create feature vector
                features = [
                    metrics.cpu_utilization,
                    metrics.memory_utilization,
                    metrics.request_rate,
                    metrics.response_time_p95,
                    metrics.error_rate,
                    metrics.active_connections,
                    metrics.cache_hit_rate,
                    metrics.db_connection_pool_usage,
                    metrics.timestamp.hour,
                    metrics.timestamp.weekday(),
                    1 if 9 <= metrics.timestamp.hour <= 17 else 0  # Peak hours
                ]
                data.append(features)

                # Target: predicted load in next 5 minutes
                future_metrics = metrics_list[min(i + 5, len(metrics_list) - 1)]
                target_load = (
                    future_metrics.cpu_utilization * 0.4 +
                    future_metrics.memory_utilization * 0.3 +
                    future_metrics.request_rate * 0.3
                )
                targets.append(target_load)

        return np.array(data), np.array(targets)

    def train_model(self):
        """Train the predictive model"""
        if len(self.metrics_history) < 120:  # Need at least 2 hours of data
            logger.warning("Insufficient data for training predictive model")
            return False

        X, y = self._prepare_features(list(self.metrics_history))

        if len(X) == 0 or len(y) == 0:
            return False

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Train model
        self.model.fit(X_train_scaled, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        mae = mean_absolute_error(y_test, y_pred)
        mse = mean_squared_error(y_test, y_pred)

        logger.info(".3f"
        self.is_trained = True
        return True

    def predict_load(self, current_metrics: OptimizationMetrics) -> float:
        """Predict future load based on current metrics"""
        if not self.is_trained:
            return current_metrics.cpu_utilization * 0.4 + \
                   current_metrics.memory_utilization * 0.3 + \
                   current_metrics.request_rate * 0.3

        features = [
            current_metrics.cpu_utilization,
            current_metrics.memory_utilization,
            current_metrics.request_rate,
            current_metrics.response_time_p95,
            current_metrics.error_rate,
            current_metrics.active_connections,
            current_metrics.cache_hit_rate,
            current_metrics.db_connection_pool_usage,
            current_metrics.timestamp.hour,
            current_metrics.timestamp.weekday(),
            1 if 9 <= current_metrics.timestamp.hour <= 17 else 0
        ]

        features_scaled = self.scaler.transform([features])
        prediction = self.model.predict(features_scaled)[0]

        return max(0.0, min(1.0, prediction))  # Clamp to [0, 1]

class AnomalyDetector:
    """Anomaly detection for system metrics"""

    def __init__(self, contamination: float = 0.1):
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.is_trained = False
        self.metrics_history = deque(maxlen=1000)

    def add_metrics(self, metrics: OptimizationMetrics):
        """Add metrics for anomaly detection training"""
        self.metrics_history.append(metrics)

    def train_model(self):
        """Train anomaly detection model"""
        if len(self.metrics_history) < 100:
            return False

        # Prepare features
        features = []
        for metrics in self.metrics_history:
            features.append([
                metrics.cpu_utilization,
                metrics.memory_utilization,
                metrics.request_rate,
                metrics.response_time_p95,
                metrics.error_rate,
                metrics.active_connections,
                metrics.cache_hit_rate,
                metrics.db_connection_pool_usage
            ])

        self.model.fit(features)
        self.is_trained = True
        return True

    def detect_anomaly(self, metrics: OptimizationMetrics) -> Tuple[bool, float]:
        """Detect if current metrics are anomalous"""
        if not self.is_trained:
            return False, 0.0

        features = [[
            metrics.cpu_utilization,
            metrics.memory_utilization,
            metrics.request_rate,
            metrics.response_time_p95,
            metrics.error_rate,
            metrics.active_connections,
            metrics.cache_hit_rate,
            metrics.db_connection_pool_usage
        ]]

        # Isolation Forest returns -1 for anomalies, 1 for normal
        prediction = self.model.predict(features)[0]
        anomaly_score = self.model.decision_function(features)[0]

        is_anomaly = prediction == -1
        confidence = abs(anomaly_score)  # Higher absolute value = more anomalous

        return is_anomaly, confidence

class OptimizationEngine:
    """Main AI optimization engine"""

    def __init__(self,
                 tracing_manager: DistributedTracingManager,
                 performance_monitor: PerformanceMonitor,
                 cache_manager: CacheManager):
        self.tracing_manager = tracing_manager
        self.performance_monitor = performance_monitor
        self.cache_manager = cache_manager

        self.predictive_scaler = PredictiveScaler()
        self.anomaly_detector = AnomalyDetector()

        self.metrics_history: List[OptimizationMetrics] = []
        self.decisions_history: List[OptimizationDecision] = []

        self.optimization_interval = 60  # seconds
        self.is_running = False

        # Optimization thresholds
        self.thresholds = {
            'cpu_high': 0.8,
            'cpu_low': 0.3,
            'memory_high': 0.85,
            'memory_low': 0.4,
            'response_time_high': 2.0,  # seconds
            'error_rate_high': 0.05,    # 5%
            'cache_hit_rate_low': 0.7,
            'db_pool_usage_high': 0.9
        }

    async def start_optimization_loop(self):
        """Start the optimization loop"""
        self.is_running = True
        logger.info("🚀 Starting AI Optimization Engine")

        while self.is_running:
            try:
                await self._collect_metrics()
                await self._analyze_and_optimize()
                await asyncio.sleep(self.optimization_interval)
            except Exception as e:
                logger.error(f"Error in optimization loop: {e}")
                await asyncio.sleep(self.optimization_interval)

    async def stop_optimization_loop(self):
        """Stop the optimization loop"""
        self.is_running = False
        logger.info("🛑 Stopped AI Optimization Engine")

    async def _collect_metrics(self):
        """Collect current system metrics"""
        try:
            # Get performance metrics
            perf_metrics = await self.performance_monitor.get_comprehensive_metrics()

            # Get tracing metrics
            trace_metrics = await self.tracing_manager.get_trace_metrics()

            # Get cache metrics
            cache_metrics = await self.cache_manager.get_cache_metrics()

            # Get database metrics (simplified)
            db_metrics = await self._get_database_metrics()

            # Create optimization metrics
            metrics = OptimizationMetrics(
                timestamp=datetime.now(),
                cpu_utilization=perf_metrics.get('cpu_percent', 0) / 100.0,
                memory_utilization=perf_metrics.get('memory_percent', 0) / 100.0,
                request_rate=perf_metrics.get('requests_per_second', 0),
                response_time_p95=perf_metrics.get('response_time_p95', 0),
                error_rate=perf_metrics.get('error_rate', 0),
                active_connections=perf_metrics.get('active_connections', 0),
                cache_hit_rate=cache_metrics.get('hit_rate', 0),
                db_connection_pool_usage=db_metrics.get('pool_usage', 0),
                trace_count=trace_metrics.get('total_traces', 0)
            )

            # Add to history
            self.metrics_history.append(metrics)
            self.predictive_scaler.add_metrics(metrics)
            self.anomaly_detector.add_metrics(metrics)

            # Keep only last 24 hours
            cutoff_time = datetime.now() - timedelta(hours=24)
            self.metrics_history = [
                m for m in self.metrics_history
                if m.timestamp > cutoff_time
            ]

        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")

    async def _analyze_and_optimize(self):
        """Analyze metrics and make optimization decisions"""
        if len(self.metrics_history) < 10:
            return  # Need more data

        current_metrics = self.metrics_history[-1]

        # Train models if needed
        if not self.predictive_scaler.is_trained and len(self.metrics_history) >= 120:
            self.predictive_scaler.train_model()

        if not self.anomaly_detector.is_trained and len(self.metrics_history) >= 100:
            self.anomaly_detector.train_model()

        # Predict future load
        predicted_load = self.predictive_scaler.predict_load(current_metrics)
        current_metrics.predicted_load = predicted_load

        # Detect anomalies
        is_anomaly, anomaly_confidence = self.anomaly_detector.detect_anomaly(current_metrics)

        # Make optimization decisions
        decisions = []

        # Scaling decisions
        scale_decision = await self._analyze_scaling_needs(current_metrics, predicted_load)
        if scale_decision:
            decisions.append(scale_decision)

        # Cache optimization
        cache_decision = await self._analyze_cache_optimization(current_metrics)
        if cache_decision:
            decisions.append(cache_decision)

        # Database optimization
        db_decision = await self._analyze_database_optimization(current_metrics)
        if db_decision:
            decisions.append(db_decision)

        # Anomaly response
        if is_anomaly and anomaly_confidence > 0.7:
            anomaly_decision = await self._handle_anomaly(current_metrics, anomaly_confidence)
            if anomaly_decision:
                decisions.append(anomaly_decision)

        # Execute decisions
        for decision in decisions:
            await self._execute_decision(decision)
            self.decisions_history.append(decision)

        # Keep only recent decisions
        cutoff_time = datetime.now() - timedelta(hours=24)
        self.decisions_history = [
            d for d in self.decisions_history
            if d.timestamp > cutoff_time
        ]

    async def _analyze_scaling_needs(self,
                                   metrics: OptimizationMetrics,
                                   predicted_load: float) -> Optional[OptimizationDecision]:
        """Analyze if scaling is needed"""
        confidence = 0.0
        actions = []
        reasoning_parts = []

        # CPU-based scaling
        if metrics.cpu_utilization > self.thresholds['cpu_high']:
            confidence = max(confidence, 0.8)
            actions.append({
                'type': 'scale_up',
                'target': 'cpu',
                'replicas': min(5, max(1, int(metrics.cpu_utilization * 10)))
            })
            reasoning_parts.append(f"High CPU utilization: {metrics.cpu_utilization:.1%}")

        elif metrics.cpu_utilization < self.thresholds['cpu_low'] and predicted_load < 0.4:
            confidence = max(confidence, 0.6)
            actions.append({
                'type': 'scale_down',
                'target': 'cpu',
                'replicas': 1
            })
            reasoning_parts.append(f"Low CPU utilization: {metrics.cpu_utilization:.1%}")

        # Memory-based scaling
        if metrics.memory_utilization > self.thresholds['memory_high']:
            confidence = max(confidence, 0.9)
            actions.append({
                'type': 'scale_up',
                'target': 'memory',
                'replicas': min(3, max(1, int(metrics.memory_utilization * 5)))
            })
            reasoning_parts.append(f"High memory utilization: {metrics.memory_utilization:.1%}")

        # Request rate based scaling
        if metrics.request_rate > 100:  # High request rate
            confidence = max(confidence, 0.7)
            actions.append({
                'type': 'scale_up',
                'target': 'requests',
                'replicas': min(10, max(2, int(metrics.request_rate / 50)))
            })
            reasoning_parts.append(f"High request rate: {metrics.request_rate:.0f} req/s")

        # Predictive scaling
        if predicted_load > 0.8:
            confidence = max(confidence, 0.75)
            actions.append({
                'type': 'predictive_scale_up',
                'target': 'predicted_load',
                'replicas': min(8, max(2, int(predicted_load * 10)))
            })
            reasoning_parts.append(f"Predicted high load: {predicted_load:.1%}")

        if not actions:
            return None

        # Calculate expected impact
        expected_impact = confidence * 0.8  # Conservative estimate

        return OptimizationDecision(
            timestamp=datetime.now(),
            decision_type='scale_up' if any(a['type'].endswith('up') for a in actions) else 'scale_down',
            confidence=confidence,
            expected_impact=expected_impact,
            reasoning="; ".join(reasoning_parts),
            actions=actions,
            rollback_plan={
                'type': 'scale_down',
                'replicas': 1,
                'conditions': ['cpu < 50%', 'memory < 60%', 'error_rate < 1%']
            }
        )

    async def _analyze_cache_optimization(self, metrics: OptimizationMetrics) -> Optional[OptimizationDecision]:
        """Analyze cache optimization opportunities"""
        if metrics.cache_hit_rate < self.thresholds['cache_hit_rate_low']:
            return OptimizationDecision(
                timestamp=datetime.now(),
                decision_type='cache_optimize',
                confidence=0.8,
                expected_impact=0.6,
                reasoning=f"Low cache hit rate: {metrics.cache_hit_rate:.1%}",
                actions=[
                    {
                        'type': 'increase_cache_ttl',
                        'target': 'frequently_accessed',
                        'ttl_multiplier': 2.0
                    },
                    {
                        'type': 'prewarm_cache',
                        'target': 'predicted_requests'
                    }
                ],
                rollback_plan={
                    'type': 'reset_cache_ttl',
                    'original_ttl': 'current'
                }
            )
        return None

    async def _analyze_database_optimization(self, metrics: OptimizationMetrics) -> Optional[OptimizationDecision]:
        """Analyze database optimization opportunities"""
        if metrics.db_connection_pool_usage > self.thresholds['db_pool_usage_high']:
            return OptimizationDecision(
                timestamp=datetime.now(),
                decision_type='db_optimize',
                confidence=0.85,
                expected_impact=0.7,
                reasoning=f"High DB connection pool usage: {metrics.db_connection_pool_usage:.1%}",
                actions=[
                    {
                        'type': 'increase_connection_pool',
                        'target': 'database',
                        'increment': 10
                    },
                    {
                        'type': 'enable_connection_pooling',
                        'target': 'read_queries'
                    }
                ],
                rollback_plan={
                    'type': 'reset_connection_pool',
                    'original_size': 'current'
                }
            )
        return None

    async def _handle_anomaly(self,
                            metrics: OptimizationMetrics,
                            confidence: float) -> Optional[OptimizationDecision]:
        """Handle detected anomalies"""
        return OptimizationDecision(
            timestamp=datetime.now(),
            decision_type='anomaly_response',
            confidence=min(confidence, 0.9),
            expected_impact=0.5,
            reasoning=f"Anomaly detected with confidence: {confidence:.2f}",
            actions=[
                {
                    'type': 'increase_monitoring',
                    'target': 'anomalous_metrics',
                    'duration': 300  # 5 minutes
                },
                {
                    'type': 'log_detailed_metrics',
                    'target': 'system_state'
                }
            ]
        )

    async def _execute_decision(self, decision: OptimizationDecision):
        """Execute optimization decision"""
        logger.info(f"🎯 Executing decision: {decision.decision_type} "
                   f"(confidence: {decision.confidence:.2f})")

        try:
            for action in decision.actions:
                await self._execute_action(action)

            logger.info(f"✅ Decision executed successfully: {decision.reasoning}")

        except Exception as e:
            logger.error(f"❌ Failed to execute decision: {e}")
            # Could implement rollback here

    async def _execute_action(self, action: Dict[str, Any]):
        """Execute individual optimization action"""
        action_type = action['type']

        if action_type == 'scale_up':
            await self._scale_up(action)
        elif action_type == 'scale_down':
            await self._scale_down(action)
        elif action_type == 'increase_cache_ttl':
            await self._increase_cache_ttl(action)
        elif action_type == 'prewarm_cache':
            await self._prewarm_cache(action)
        elif action_type == 'increase_connection_pool':
            await self._increase_connection_pool(action)
        elif action_type == 'increase_monitoring':
            await self._increase_monitoring(action)

    async def _scale_up(self, action: Dict[str, Any]):
        """Scale up resources"""
        # This would integrate with Kubernetes HPA or cloud auto-scaling
        logger.info(f"Scaling up: {action}")

    async def _scale_down(self, action: Dict[str, Any]):
        """Scale down resources"""
        logger.info(f"Scaling down: {action}")

    async def _increase_cache_ttl(self, action: Dict[str, Any]):
        """Increase cache TTL"""
        await self.cache_manager.adjust_cache_ttl(
            multiplier=action.get('ttl_multiplier', 1.5)
        )

    async def _prewarm_cache(self, action: Dict[str, Any]):
        """Pre-warm cache with predicted requests"""
        # This would analyze recent patterns and pre-load cache
        logger.info("Pre-warming cache with predicted requests")

    async def _increase_connection_pool(self, action: Dict[str, Any]):
        """Increase database connection pool"""
        # This would adjust database connection pool settings
        logger.info(f"Increasing connection pool: {action}")

    async def _increase_monitoring(self, action: Dict[str, Any]):
        """Increase monitoring for specific metrics"""
        duration = action.get('duration', 300)
        logger.info(f"Increasing monitoring for {duration} seconds")

    async def _get_database_metrics(self) -> Dict[str, float]:
        """Get database performance metrics"""
        # This would integrate with database monitoring
        return {
            'pool_usage': 0.6,  # Placeholder
            'active_connections': 15,
            'query_latency': 0.05
        }

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get optimization statistics"""
        if not self.decisions_history:
            return {}

        recent_decisions = [
            d for d in self.decisions_history
            if d.timestamp > datetime.now() - timedelta(hours=1)
        ]

        return {
            'total_decisions': len(self.decisions_history),
            'recent_decisions': len(recent_decisions),
            'avg_confidence': np.mean([d.confidence for d in recent_decisions]) if recent_decisions else 0,
            'decision_types': list(set(d.decision_type for d in self.decisions_history)),
            'scaler_trained': self.predictive_scaler.is_trained,
            'anomaly_detector_trained': self.anomaly_detector.is_trained,
            'metrics_collected': len(self.metrics_history)
        }
