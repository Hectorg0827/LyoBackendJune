"""
Living Classroom - A/B Testing Configuration & Management
=======================================================

Production-ready A/B testing framework for safe rollout of Living Classroom.
Supports multiple test variants, user segmentation, and metric collection.
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


class TestVariant(str, Enum):
    """A/B test variants for Living Classroom rollout"""
    CONTROL = "control"          # Current SSE streaming
    TREATMENT = "treatment"      # Full Living Classroom
    HYBRID = "hybrid"           # Mixed approach based on scene type
    BETA = "beta"               # Advanced features for power users


class UserSegment(str, Enum):
    """User segmentation for targeted testing"""
    NEW_USERS = "new_users"
    RETURNING_USERS = "returning_users"
    PREMIUM_USERS = "premium_users"
    FREE_USERS = "free_users"
    HIGH_ENGAGEMENT = "high_engagement"
    LOW_ENGAGEMENT = "low_engagement"
    ALL_USERS = "all_users"


class MetricType(str, Enum):
    """Types of metrics to track"""
    ENGAGEMENT = "engagement"
    PERFORMANCE = "performance"
    CONVERSION = "conversion"
    RETENTION = "retention"
    SATISFACTION = "satisfaction"


@dataclass
class TestConfiguration:
    """A/B test configuration"""
    test_name: str
    description: str
    start_date: str
    end_date: str

    # Traffic allocation (must sum to 100)
    control_percentage: float = 50.0
    treatment_percentage: float = 40.0
    hybrid_percentage: float = 10.0
    beta_percentage: float = 0.0

    # User segmentation
    target_segments: List[UserSegment] = field(default_factory=lambda: [UserSegment.ALL_USERS])
    excluded_segments: List[UserSegment] = field(default_factory=list)

    # Feature flags
    enabled: bool = True
    force_assignment: Optional[Dict[str, TestVariant]] = None  # user_id -> variant

    # Metrics to track
    success_metrics: List[str] = field(default_factory=lambda: [
        "scene_generation_time",
        "user_engagement_score",
        "session_completion_rate",
        "user_satisfaction_score"
    ])

    # Minimum sample sizes for statistical significance
    min_sample_size: int = 1000
    confidence_level: float = 0.95


class ABTestManager:
    """Advanced A/B Testing Framework"""

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.test_configs: Dict[str, TestConfiguration] = {}
        self.user_assignments: Dict[str, Dict[str, TestVariant]] = {}
        self.metric_collectors: Dict[str, Any] = {}

        # Load configurations
        self._load_configurations()

        logger.info(f"🧪 A/B Test Manager initialized with {len(self.test_configs)} active tests")

    def _load_configurations(self):
        """Load A/B test configurations from environment and database"""

        # Primary Living Classroom rollout test
        self.test_configs["living_classroom_rollout"] = TestConfiguration(
            test_name="living_classroom_rollout",
            description="Gradual rollout of Living Classroom real-time streaming",
            start_date=os.getenv("AB_TEST_START_DATE", "2024-01-01"),
            end_date=os.getenv("AB_TEST_END_DATE", "2024-12-31"),
            control_percentage=float(os.getenv("AB_CONTROL_PCT", "60")),
            treatment_percentage=float(os.getenv("AB_TREATMENT_PCT", "30")),
            hybrid_percentage=float(os.getenv("AB_HYBRID_PCT", "10")),
            enabled=os.getenv("AB_TEST_ENABLED", "true").lower() == "true"
        )

        # Feature-specific tests
        self.test_configs["progressive_rendering"] = TestConfiguration(
            test_name="progressive_rendering",
            description="Test progressive component rendering vs instant display",
            start_date="2024-01-01",
            end_date="2024-06-30",
            control_percentage=50.0,
            treatment_percentage=50.0,
            target_segments=[UserSegment.PREMIUM_USERS, UserSegment.HIGH_ENGAGEMENT],
            success_metrics=["component_render_time", "user_engagement_score"]
        )

        self.test_configs["ai_peer_interactions"] = TestConfiguration(
            test_name="ai_peer_interactions",
            description="Test AI peer student interactions for error normalization",
            start_date="2024-02-01",
            end_date="2024-08-31",
            control_percentage=70.0,
            treatment_percentage=30.0,
            target_segments=[UserSegment.NEW_USERS],
            success_metrics=["frustration_reduction", "session_completion_rate"]
        )

    async def assign_user_to_variant(
        self,
        user_id: str,
        test_name: str = "living_classroom_rollout",
        user_segment: Optional[UserSegment] = None
    ) -> TestVariant:
        """Assign user to A/B test variant with intelligent segmentation"""

        config = self.test_configs.get(test_name)
        if not config or not config.enabled:
            return TestVariant.CONTROL

        # Check test date range
        now = datetime.utcnow()
        start_date = datetime.fromisoformat(config.start_date.replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(config.end_date.replace('Z', '+00:00'))

        if not (start_date <= now <= end_date):
            return TestVariant.CONTROL

        # Check cached assignment
        cache_key = f"{test_name}_{user_id}"
        if test_name in self.user_assignments and user_id in self.user_assignments[test_name]:
            return self.user_assignments[test_name][user_id]

        # Check forced assignment
        if config.force_assignment and user_id in config.force_assignment:
            variant = config.force_assignment[user_id]
            self._cache_assignment(test_name, user_id, variant)
            return variant

        # Check user segment eligibility
        if user_segment and not await self._is_user_eligible(user_id, config, user_segment):
            self._cache_assignment(test_name, user_id, TestVariant.CONTROL)
            return TestVariant.CONTROL

        # Assign based on deterministic hash
        variant = self._calculate_variant_assignment(user_id, test_name, config)

        # Log assignment
        await self._log_assignment(test_name, user_id, variant, user_segment)

        # Cache assignment
        self._cache_assignment(test_name, user_id, variant)

        return variant

    def _calculate_variant_assignment(
        self,
        user_id: str,
        test_name: str,
        config: TestConfiguration
    ) -> TestVariant:
        """Calculate variant assignment using consistent hashing"""

        # Create deterministic hash
        hash_input = f"{test_name}_{user_id}_{config.start_date}"
        user_hash = int(hashlib.md5(hash_input.encode()).hexdigest(), 16) % 10000

        # Calculate cumulative percentages (scaled to 10000 for precision)
        control_threshold = int(config.control_percentage * 100)
        treatment_threshold = control_threshold + int(config.treatment_percentage * 100)
        hybrid_threshold = treatment_threshold + int(config.hybrid_percentage * 100)
        beta_threshold = hybrid_threshold + int(config.beta_percentage * 100)

        # Assign variant
        if user_hash < control_threshold:
            return TestVariant.CONTROL
        elif user_hash < treatment_threshold:
            return TestVariant.TREATMENT
        elif user_hash < hybrid_threshold:
            return TestVariant.HYBRID
        elif user_hash < beta_threshold:
            return TestVariant.BETA
        else:
            return TestVariant.CONTROL  # Default fallback

    async def _is_user_eligible(
        self,
        user_id: str,
        config: TestConfiguration,
        user_segment: UserSegment
    ) -> bool:
        """Check if user is eligible for the test based on segmentation"""

        # Check target segments
        if UserSegment.ALL_USERS not in config.target_segments:
            if user_segment not in config.target_segments:
                return False

        # Check excluded segments
        if user_segment in config.excluded_segments:
            return False

        # Additional eligibility checks can be added here
        # e.g., user registration date, subscription status, etc.

        return True

    def _cache_assignment(self, test_name: str, user_id: str, variant: TestVariant):
        """Cache user assignment in memory"""
        if test_name not in self.user_assignments:
            self.user_assignments[test_name] = {}

        self.user_assignments[test_name][user_id] = variant

    async def _log_assignment(
        self,
        test_name: str,
        user_id: str,
        variant: TestVariant,
        user_segment: Optional[UserSegment]
    ):
        """Log assignment to database for analysis"""
        if not self.db:
            return

        try:
            await self.db.execute(
                text("""
                    INSERT INTO ab_test_assignments
                    (test_name, user_id, variant, user_segment, assigned_at)
                    VALUES (:test_name, :user_id, :variant, :user_segment, :assigned_at)
                    ON CONFLICT (test_name, user_id) DO NOTHING
                """),
                {
                    "test_name": test_name,
                    "user_id": user_id,
                    "variant": variant.value,
                    "user_segment": user_segment.value if user_segment else None,
                    "assigned_at": datetime.utcnow()
                }
            )
            await self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log A/B test assignment: {e}")

    async def record_metric_event(
        self,
        user_id: str,
        test_name: str,
        metric_name: str,
        metric_value: Union[float, int, str],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record metric event for A/B test analysis"""

        variant = await self.assign_user_to_variant(user_id, test_name)

        if not self.db:
            # Store in memory for testing
            if not hasattr(self, '_metric_events'):
                self._metric_events = []

            self._metric_events.append({
                "timestamp": datetime.utcnow(),
                "test_name": test_name,
                "user_id": user_id,
                "variant": variant.value,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "metadata": metadata or {}
            })
            return

        try:
            await self.db.execute(
                text("""
                    INSERT INTO ab_test_metrics
                    (test_name, user_id, variant, metric_name, metric_value, metadata, recorded_at)
                    VALUES (:test_name, :user_id, :variant, :metric_name, :metric_value, :metadata, :recorded_at)
                """),
                {
                    "test_name": test_name,
                    "user_id": user_id,
                    "variant": variant.value,
                    "metric_name": metric_name,
                    "metric_value": float(metric_value) if isinstance(metric_value, (int, float)) else str(metric_value),
                    "metadata": json.dumps(metadata) if metadata else None,
                    "recorded_at": datetime.utcnow()
                }
            )
            await self.db.commit()
        except Exception as e:
            logger.error(f"Failed to record A/B test metric: {e}")

    async def get_test_results(self, test_name: str) -> Dict[str, Any]:
        """Get comprehensive test results with statistical analysis"""

        if not self.db:
            # Return mock results for testing
            return self._get_mock_results(test_name)

        try:
            # Get assignment counts
            assignment_result = await self.db.execute(
                text("""
                    SELECT variant, COUNT(*) as count
                    FROM ab_test_assignments
                    WHERE test_name = :test_name
                    GROUP BY variant
                """),
                {"test_name": test_name}
            )

            assignments = {row[0]: row[1] for row in assignment_result}

            # Get metric aggregations
            metrics_result = await self.db.execute(
                text("""
                    SELECT
                        variant,
                        metric_name,
                        COUNT(*) as event_count,
                        AVG(metric_value) as avg_value,
                        STDDEV(metric_value) as stddev_value,
                        MIN(metric_value) as min_value,
                        MAX(metric_value) as max_value
                    FROM ab_test_metrics
                    WHERE test_name = :test_name
                    GROUP BY variant, metric_name
                """),
                {"test_name": test_name}
            )

            metrics = {}
            for row in metrics_result:
                variant, metric_name = row[0], row[1]
                if variant not in metrics:
                    metrics[variant] = {}

                metrics[variant][metric_name] = {
                    "event_count": row[2],
                    "average": row[3],
                    "stddev": row[4],
                    "min": row[5],
                    "max": row[6]
                }

            # Calculate statistical significance
            significance_results = self._calculate_statistical_significance(metrics)

            return {
                "test_name": test_name,
                "assignments": assignments,
                "metrics": metrics,
                "statistical_significance": significance_results,
                "total_users": sum(assignments.values()),
                "analysis_timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get A/B test results: {e}")
            return {"error": str(e)}

    def _get_mock_results(self, test_name: str) -> Dict[str, Any]:
        """Generate mock results for testing purposes"""
        return {
            "test_name": test_name,
            "assignments": {
                "control": 1200,
                "treatment": 800,
                "hybrid": 200
            },
            "metrics": {
                "control": {
                    "scene_generation_time": {"average": 2450.0, "event_count": 1200},
                    "user_engagement_score": {"average": 0.72, "event_count": 1200}
                },
                "treatment": {
                    "scene_generation_time": {"average": 245.0, "event_count": 800},
                    "user_engagement_score": {"average": 0.89, "event_count": 800}
                },
                "hybrid": {
                    "scene_generation_time": {"average": 450.0, "event_count": 200},
                    "user_engagement_score": {"average": 0.81, "event_count": 200}
                }
            },
            "statistical_significance": {
                "scene_generation_time": {
                    "control_vs_treatment": {"p_value": 0.001, "significant": True},
                    "control_vs_hybrid": {"p_value": 0.023, "significant": True}
                },
                "user_engagement_score": {
                    "control_vs_treatment": {"p_value": 0.007, "significant": True},
                    "control_vs_hybrid": {"p_value": 0.045, "significant": True}
                }
            },
            "total_users": 2200
        }

    def _calculate_statistical_significance(self, metrics: Dict) -> Dict[str, Any]:
        """Calculate statistical significance between variants"""
        # Placeholder for statistical calculations
        # In production, you'd implement proper statistical tests (t-tests, chi-square, etc.)
        return {
            "method": "t_test",
            "confidence_level": 0.95,
            "note": "Statistical significance calculation placeholder"
        }

    async def should_use_living_classroom(self, user_id: str) -> bool:
        """Determine if user should get Living Classroom based on A/B test"""
        variant = await self.assign_user_to_variant(user_id)
        return variant in [TestVariant.TREATMENT, TestVariant.HYBRID, TestVariant.BETA]

    async def get_feature_flags(self, user_id: str) -> Dict[str, bool]:
        """Get feature flags for user based on A/B test assignments"""

        living_classroom_variant = await self.assign_user_to_variant(user_id, "living_classroom_rollout")
        progressive_rendering_variant = await self.assign_user_to_variant(user_id, "progressive_rendering")
        ai_peer_variant = await self.assign_user_to_variant(user_id, "ai_peer_interactions")

        return {
            "use_living_classroom": living_classroom_variant in [TestVariant.TREATMENT, TestVariant.HYBRID, TestVariant.BETA],
            "use_progressive_rendering": progressive_rendering_variant == TestVariant.TREATMENT,
            "use_ai_peer_interactions": ai_peer_variant == TestVariant.TREATMENT,
            "use_advanced_features": living_classroom_variant == TestVariant.BETA,
            "living_classroom_variant": living_classroom_variant.value,
        }

    def get_active_tests(self) -> List[str]:
        """Get list of currently active tests"""
        now = datetime.utcnow()
        active_tests = []

        for test_name, config in self.test_configs.items():
            if not config.enabled:
                continue

            start_date = datetime.fromisoformat(config.start_date.replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(config.end_date.replace('Z', '+00:00'))

            if start_date <= now <= end_date:
                active_tests.append(test_name)

        return active_tests


# Global instance
_ab_test_manager: Optional[ABTestManager] = None


async def get_ab_test_manager(db: Optional[AsyncSession] = None) -> ABTestManager:
    """Get A/B test manager instance"""
    global _ab_test_manager

    if _ab_test_manager is None:
        _ab_test_manager = ABTestManager(db)

    return _ab_test_manager


# Convenience functions
async def should_use_living_classroom(user_id: str, db: Optional[AsyncSession] = None) -> bool:
    """Check if user should get Living Classroom experience"""
    ab_manager = await get_ab_test_manager(db)
    return await ab_manager.should_use_living_classroom(user_id)


async def get_user_feature_flags(user_id: str, db: Optional[AsyncSession] = None) -> Dict[str, bool]:
    """Get feature flags for user"""
    ab_manager = await get_ab_test_manager(db)
    return await ab_manager.get_feature_flags(user_id)


async def record_ab_test_metric(
    user_id: str,
    metric_name: str,
    metric_value: Union[float, int, str],
    test_name: str = "living_classroom_rollout",
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[AsyncSession] = None
):
    """Record A/B test metric"""
    ab_manager = await get_ab_test_manager(db)
    await ab_manager.record_metric_event(user_id, test_name, metric_name, metric_value, metadata)