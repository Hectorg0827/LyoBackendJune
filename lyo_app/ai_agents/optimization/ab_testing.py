"""
Intelligent A/B Testing Framework for AI Agents
Continuous optimization through experimentation and data-driven improvements.
"""

import asyncio
import random
import hashlib
from typing import Dict, Any, List, Optional, Tuple, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import numpy as np
# Lazy import scipy.stats only when needed
# from scipy import stats

import structlog

# Optional prometheus metrics
try:
    from prometheus_client import Counter, Histogram, Gauge
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def inc(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self

logger = structlog.get_logger(__name__)

# Metrics
experiment_counter = Counter('ai_experiments_total', 'Total experiments', ['experiment_name', 'variant'])
conversion_counter = Counter('ai_experiment_conversions_total', 'Conversions', ['experiment_name', 'variant'])
experiment_duration = Histogram('ai_experiment_duration_seconds', 'Experiment duration')

class ExperimentStatus(Enum):
    """Experiment status states."""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

class ExperimentType(Enum):
    """Types of experiments."""
    RESPONSE_OPTIMIZATION = "response_optimization"
    MODEL_SELECTION = "model_selection"
    PROMPT_ENGINEERING = "prompt_engineering"
    PERSONALIZATION = "personalization"
    CONTENT_RANKING = "content_ranking"
    UI_INTERACTION = "ui_interaction"

class StatisticalSignificance(Enum):
    """Statistical significance levels."""
    LOW = 0.10     # 90% confidence
    MEDIUM = 0.05  # 95% confidence
    HIGH = 0.01    # 99% confidence

@dataclass
class ExperimentVariant:
    """Individual experiment variant configuration."""
    name: str
    weight: float  # Traffic allocation (0.0 to 1.0)
    config: Dict[str, Any]
    description: str
    is_control: bool = False
    
    # Performance metrics
    participants: int = 0
    conversions: int = 0
    total_response_time: float = 0.0
    total_satisfaction_score: float = 0.0
    error_count: int = 0
    
    @property
    def conversion_rate(self) -> float:
        """Calculate conversion rate."""
        return self.conversions / max(self.participants, 1)
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time."""
        return self.total_response_time / max(self.participants, 1)
    
    @property
    def avg_satisfaction(self) -> float:
        """Calculate average satisfaction score."""
        return self.total_satisfaction_score / max(self.participants, 1)
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        return self.error_count / max(self.participants, 1)

@dataclass
class ExperimentMetrics:
    """Comprehensive experiment metrics."""
    primary_metric: str
    secondary_metrics: List[str] = field(default_factory=list)
    success_criteria: Dict[str, float] = field(default_factory=dict)
    
    # Statistical analysis results
    statistical_significance: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None
    effect_size: Optional[float] = None
    power: Optional[float] = None

@dataclass
class Experiment:
    """Complete experiment configuration and state."""
    id: str
    name: str
    description: str
    experiment_type: ExperimentType
    status: ExperimentStatus
    
    # Configuration
    variants: List[ExperimentVariant]
    metrics: ExperimentMetrics
    target_participants: int
    min_runtime_days: int
    max_runtime_days: int
    significance_level: StatisticalSignificance
    
    # Runtime state
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_analyzed: Optional[datetime] = None
    
    # Participant filtering
    user_filters: Dict[str, Any] = field(default_factory=dict)
    traffic_allocation: float = 1.0  # Percentage of users to include
    
    def get_variant_for_user(self, user_id: int) -> ExperimentVariant:
        """Determine which variant a user should see."""
        if self.status != ExperimentStatus.RUNNING:
            return self._get_control_variant()
        
        # Create deterministic hash based on experiment ID and user ID
        hash_input = f"{self.id}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        normalized_hash = (hash_value % 10000) / 10000.0
        
        # Check if user is in experiment traffic
        if normalized_hash > self.traffic_allocation:
            return self._get_control_variant()
        
        # Assign variant based on weights
        cumulative_weight = 0.0
        for variant in self.variants:
            cumulative_weight += variant.weight
            if normalized_hash <= cumulative_weight:
                return variant
        
        # Fallback to control
        return self._get_control_variant()
    
    def _get_control_variant(self) -> ExperimentVariant:
        """Get the control variant."""
        control_variants = [v for v in self.variants if v.is_control]
        if control_variants:
            return control_variants[0]
        return self.variants[0]  # Fallback to first variant
    
    def should_stop_early(self) -> Tuple[bool, str]:
        """Determine if experiment should stop early."""
        if not self.start_time:
            return False, ""
        
        runtime_days = (datetime.now() - self.start_time).days
        
        # Check minimum runtime
        if runtime_days < self.min_runtime_days:
            return False, "Minimum runtime not reached"
        
        # Check maximum runtime
        if runtime_days >= self.max_runtime_days:
            return True, "Maximum runtime reached"
        
        # Check if we have enough participants
        total_participants = sum(v.participants for v in self.variants)
        if total_participants < self.target_participants:
            return False, "Target participants not reached"
        
        # Check statistical significance
        significance_result = self._check_statistical_significance()
        if significance_result["is_significant"]:
            return True, f"Statistical significance achieved: p={significance_result['p_value']:.4f}"
        
        return False, "No early stopping criteria met"
    
    def _check_statistical_significance(self) -> Dict[str, Any]:
        """Check if results are statistically significant."""
        if len(self.variants) < 2:
            return {"is_significant": False, "p_value": 1.0}
        
        control = self._get_control_variant()
        treatment_variants = [v for v in self.variants if not v.is_control]
        
        if not treatment_variants:
            return {"is_significant": False, "p_value": 1.0}
        
        # Use the best performing treatment variant
        best_treatment = max(treatment_variants, key=lambda v: v.conversion_rate)
        
        # Use the best performing treatment variant
        best_treatment = max(treatment_variants, key=lambda v: v.conversion_rate)
        
        # Perform two-proportion z-test
        try:
            from scipy import stats

            control_successes = control.conversions
            control_trials = control.participants
            treatment_successes = best_treatment.conversions
            treatment_trials = best_treatment.participants
            
            if control_trials < 30 or treatment_trials < 30:
                return {"is_significant": False, "p_value": 1.0, "reason": "Insufficient sample size"}
            
            # Two-proportion z-test
            p1 = control_successes / control_trials
            p2 = treatment_successes / treatment_trials
            
            pooled_p = (control_successes + treatment_successes) / (control_trials + treatment_trials)
            se = np.sqrt(pooled_p * (1 - pooled_p) * (1/control_trials + 1/treatment_trials))
            
            if se == 0:
                return {"is_significant": False, "p_value": 1.0}
            
            z_score = (p2 - p1) / se
            p_value = 2 * (1 - stats.norm.cdf(abs(z_score)))
            
            is_significant = p_value < self.significance_level.value
            
            return {
                "is_significant": is_significant,
                "p_value": p_value,
                "z_score": z_score,
                "control_rate": p1,
                "treatment_rate": p2,
                "lift": (p2 - p1) / p1 if p1 > 0 else 0,
                "confidence_interval": self._calculate_confidence_interval(p1, p2, control_trials, treatment_trials)
            }
            
        except Exception as e:
            logger.error(f"Statistical significance calculation failed: {e}")
            return {"is_significant": False, "p_value": 1.0, "error": str(e)}
    
    def _calculate_confidence_interval(self, p1: float, p2: float, n1: int, n2: int) -> Tuple[float, float]:
        """Calculate confidence interval for the difference in proportions."""
        diff = p2 - p1
        se_diff = np.sqrt((p1 * (1 - p1) / n1) + (p2 * (1 - p2) / n2))
        
        # Z-score for desired confidence level
        z_scores = {
            StatisticalSignificance.LOW: 1.645,
            StatisticalSignificance.MEDIUM: 1.96,
            StatisticalSignificance.HIGH: 2.576
        }
        z = z_scores[self.significance_level]
        
        margin_of_error = z * se_diff
        return (diff - margin_of_error, diff + margin_of_error)

class ExperimentManager:
    """Manages all A/B testing experiments for AI agents."""
    
    def __init__(self):
        self.experiments: Dict[str, Experiment] = {}
        self.active_experiments: List[str] = []
        self.experiment_history: List[Dict[str, Any]] = []
        
    async def create_experiment(
        self,
        name: str,
        description: str,
        experiment_type: ExperimentType,
        variants: List[Dict[str, Any]],
        metrics_config: Dict[str, Any],
        target_participants: int = 1000,
        min_runtime_days: int = 7,
        max_runtime_days: int = 30,
        significance_level: StatisticalSignificance = StatisticalSignificance.MEDIUM,
        traffic_allocation: float = 0.1
    ) -> str:
        """Create a new A/B test experiment."""
        
        experiment_id = hashlib.md5(f"{name}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        # Create experiment variants
        experiment_variants = []
        total_weight = 0.0
        
        for i, variant_config in enumerate(variants):
            variant = ExperimentVariant(
                name=variant_config["name"],
                weight=variant_config.get("weight", 1.0 / len(variants)),
                config=variant_config["config"],
                description=variant_config.get("description", ""),
                is_control=variant_config.get("is_control", i == 0)
            )
            experiment_variants.append(variant)
            total_weight += variant.weight
        
        # Normalize weights to sum to 1.0
        for variant in experiment_variants:
            variant.weight = variant.weight / total_weight
        
        # Create experiment metrics
        metrics = ExperimentMetrics(
            primary_metric=metrics_config["primary_metric"],
            secondary_metrics=metrics_config.get("secondary_metrics", []),
            success_criteria=metrics_config.get("success_criteria", {})
        )
        
        # Create experiment
        experiment = Experiment(
            id=experiment_id,
            name=name,
            description=description,
            experiment_type=experiment_type,
            status=ExperimentStatus.DRAFT,
            variants=experiment_variants,
            metrics=metrics,
            target_participants=target_participants,
            min_runtime_days=min_runtime_days,
            max_runtime_days=max_runtime_days,
            significance_level=significance_level,
            traffic_allocation=traffic_allocation
        )
        
        self.experiments[experiment_id] = experiment
        
        logger.info(f"Created experiment: {name} ({experiment_id})")
        return experiment_id
    
    async def start_experiment(self, experiment_id: str) -> bool:
        """Start running an experiment."""
        if experiment_id not in self.experiments:
            logger.error(f"Experiment {experiment_id} not found")
            return False
        
        experiment = self.experiments[experiment_id]
        
        if experiment.status != ExperimentStatus.DRAFT:
            logger.error(f"Experiment {experiment_id} cannot be started (status: {experiment.status})")
            return False
        
        experiment.status = ExperimentStatus.RUNNING
        experiment.start_time = datetime.now()
        self.active_experiments.append(experiment_id)
        
        logger.info(f"Started experiment: {experiment.name} ({experiment_id})")
        return True
    
    async def stop_experiment(self, experiment_id: str, reason: str = "Manual stop") -> bool:
        """Stop a running experiment."""
        if experiment_id not in self.experiments:
            return False
        
        experiment = self.experiments[experiment_id]
        experiment.status = ExperimentStatus.COMPLETED
        experiment.end_time = datetime.now()
        
        if experiment_id in self.active_experiments:
            self.active_experiments.remove(experiment_id)
        
        # Record experiment results
        await self._record_experiment_results(experiment, reason)
        
        logger.info(f"Stopped experiment: {experiment.name} ({experiment_id}) - {reason}")
        return True
    
    async def record_participant(self, experiment_id: str, user_id: int, variant_name: str) -> bool:
        """Record a user's participation in an experiment."""
        if experiment_id not in self.experiments:
            return False
        
        experiment = self.experiments[experiment_id]
        variant = next((v for v in experiment.variants if v.name == variant_name), None)
        
        if not variant:
            return False
        
        variant.participants += 1
        experiment_counter.labels(experiment_name=experiment.name, variant=variant_name).inc()
        
        return True
    
    async def record_conversion(
        self,
        experiment_id: str,
        user_id: int,
        variant_name: str,
        conversion_value: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Record a conversion event for an experiment participant."""
        if experiment_id not in self.experiments:
            return False
        
        experiment = self.experiments[experiment_id]
        variant = next((v for v in experiment.variants if v.name == variant_name), None)
        
        if not variant:
            return False
        
        variant.conversions += conversion_value
        conversion_counter.labels(experiment_name=experiment.name, variant=variant_name).inc()
        
        # Record additional metrics if provided
        if metadata:
            if "response_time" in metadata:
                variant.total_response_time += metadata["response_time"]
            if "satisfaction_score" in metadata:
                variant.total_satisfaction_score += metadata["satisfaction_score"]
            if "error" in metadata and metadata["error"]:
                variant.error_count += 1
        
        return True
    
    async def get_experiment_variant(self, experiment_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get the variant configuration for a user in an experiment."""
        if experiment_id not in self.experiments:
            return None
        
        experiment = self.experiments[experiment_id]
        if experiment.status != ExperimentStatus.RUNNING:
            return None
        
        variant = experiment.get_variant_for_user(user_id)
        
        # Record participation
        await self.record_participant(experiment_id, user_id, variant.name)
        
        return {
            "variant_name": variant.name,
            "config": variant.config,
            "is_control": variant.is_control
        }
    
    async def analyze_experiments(self) -> Dict[str, Any]:
        """Analyze all running experiments for statistical significance and early stopping."""
        analysis_results = {}
        
        for experiment_id in self.active_experiments.copy():  # Copy to avoid modification during iteration
            experiment = self.experiments[experiment_id]
            
            # Check if experiment should stop early
            should_stop, reason = experiment.should_stop_early()
            
            if should_stop:
                await self.stop_experiment(experiment_id, reason)
            
            # Perform statistical analysis
            statistical_results = experiment._check_statistical_significance()
            
            analysis_results[experiment_id] = {
                "experiment_name": experiment.name,
                "status": experiment.status.value,
                "runtime_days": (datetime.now() - experiment.start_time).days if experiment.start_time else 0,
                "total_participants": sum(v.participants for v in experiment.variants),
                "variants": [
                    {
                        "name": v.name,
                        "participants": v.participants,
                        "conversions": v.conversions,
                        "conversion_rate": v.conversion_rate,
                        "avg_response_time": v.avg_response_time,
                        "avg_satisfaction": v.avg_satisfaction,
                        "error_rate": v.error_rate,
                        "is_control": v.is_control
                    }
                    for v in experiment.variants
                ],
                "statistical_results": statistical_results,
                "should_stop": should_stop,
                "stop_reason": reason if should_stop else None
            }
        
        return analysis_results
    
    async def _record_experiment_results(self, experiment: Experiment, stop_reason: str):
        """Record final experiment results for analysis."""
        statistical_results = experiment._check_statistical_significance()
        
        result_record = {
            "experiment_id": experiment.id,
            "experiment_name": experiment.name,
            "experiment_type": experiment.experiment_type.value,
            "start_time": experiment.start_time.isoformat() if experiment.start_time else None,
            "end_time": experiment.end_time.isoformat() if experiment.end_time else None,
            "stop_reason": stop_reason,
            "total_participants": sum(v.participants for v in experiment.variants),
            "statistical_results": statistical_results,
            "variants": [
                {
                    "name": v.name,
                    "participants": v.participants,
                    "conversions": v.conversions,
                    "conversion_rate": v.conversion_rate,
                    "is_control": v.is_control,
                    "performance_metrics": {
                        "avg_response_time": v.avg_response_time,
                        "avg_satisfaction": v.avg_satisfaction,
                        "error_rate": v.error_rate
                    }
                }
                for v in experiment.variants
            ]
        }
        
        self.experiment_history.append(result_record)
    
    def get_experiment_status(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of an experiment."""
        if experiment_id not in self.experiments:
            return None
        
        experiment = self.experiments[experiment_id]
        
        return {
            "id": experiment.id,
            "name": experiment.name,
            "status": experiment.status.value,
            "experiment_type": experiment.experiment_type.value,
            "start_time": experiment.start_time.isoformat() if experiment.start_time else None,
            "participants": sum(v.participants for v in experiment.variants),
            "target_participants": experiment.target_participants,
            "variants": [
                {
                    "name": v.name,
                    "weight": v.weight,
                    "participants": v.participants,
                    "conversions": v.conversions,
                    "conversion_rate": v.conversion_rate
                }
                for v in experiment.variants
            ]
        }
    
    def list_experiments(self, status_filter: Optional[ExperimentStatus] = None) -> List[Dict[str, Any]]:
        """List all experiments, optionally filtered by status."""
        experiments = []
        
        for experiment in self.experiments.values():
            if status_filter is None or experiment.status == status_filter:
                experiments.append({
                    "id": experiment.id,
                    "name": experiment.name,
                    "status": experiment.status.value,
                    "experiment_type": experiment.experiment_type.value,
                    "created_at": experiment.created_at.isoformat(),
                    "participants": sum(v.participants for v in experiment.variants)
                })
        
        return sorted(experiments, key=lambda x: x["created_at"], reverse=True)

# Experiment templates for common AI optimizations
EXPERIMENT_TEMPLATES = {
    "response_optimization": {
        "name": "AI Response Optimization",
        "description": "Test different response generation strategies",
        "experiment_type": ExperimentType.RESPONSE_OPTIMIZATION,
        "variants": [
            {
                "name": "control",
                "config": {"strategy": "default"},
                "is_control": True,
                "weight": 0.5
            },
            {
                "name": "optimized",
                "config": {"strategy": "optimized", "use_cache": True},
                "is_control": False,
                "weight": 0.5
            }
        ],
        "metrics": {
            "primary_metric": "user_satisfaction",
            "secondary_metrics": ["response_time", "engagement_rate"],
            "success_criteria": {"user_satisfaction": 0.05}  # 5% improvement
        }
    },
    
    "model_selection": {
        "name": "Model Selection Test",
        "description": "Compare different AI models for task performance",
        "experiment_type": ExperimentType.MODEL_SELECTION,
        "variants": [
            {
                "name": "gemma_on_device",
                "config": {"model": "gemma_4_on_device"},
                "is_control": True,
                "weight": 0.4
            },
            {
                "name": "gemma_cloud",
                "config": {"model": "gemma_4_cloud"},
                "is_control": False,
                "weight": 0.3
            },
            {
                "name": "gpt4_mini",
                "config": {"model": "gpt_4_mini"},
                "is_control": False,
                "weight": 0.3
            }
        ],
        "metrics": {
            "primary_metric": "task_completion_rate",
            "secondary_metrics": ["response_time", "cost_per_request", "user_satisfaction"],
            "success_criteria": {"task_completion_rate": 0.1}  # 10% improvement
        }
    },
    
    "personalization": {
        "name": "Personalization Engine Test",
        "description": "Test impact of personalized content recommendations",
        "experiment_type": ExperimentType.PERSONALIZATION,
        "variants": [
            {
                "name": "no_personalization",
                "config": {"personalization_enabled": False},
                "is_control": True,
                "weight": 0.5
            },
            {
                "name": "personalized",
                "config": {"personalization_enabled": True, "algorithm": "collaborative_filtering"},
                "is_control": False,
                "weight": 0.5
            }
        ],
        "metrics": {
            "primary_metric": "content_engagement",
            "secondary_metrics": ["session_duration", "return_rate", "completion_rate"],
            "success_criteria": {"content_engagement": 0.15}  # 15% improvement
        }
    }
}

# Global experiment manager instance
experiment_manager = ExperimentManager()
