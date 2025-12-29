"""
Usage tracking and analytics for course generation.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class CourseGenerationMetrics:
    """Metrics for a single course generation"""
    generation_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: Optional[str] = None
    course_id: Optional[str] = None
    
    # Request details
    topic: str = ""
    quality_tier: str = "balanced"
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Generation performance
    total_duration_seconds: float = 0.0
    generation_status: str = "pending"  # pending, completed, failed
    
    # Token usage by agent
    orchestrator_tokens: int = 0
    curriculum_tokens: int = 0
    content_creator_tokens: int = 0
    assessment_tokens: int = 0
    qa_tokens: int = 0
    total_tokens: int = 0
    
    # Cost breakdown (USD)
    orchestrator_cost: float = 0.0
    curriculum_cost: float = 0.0
    content_creator_cost: float = 0.0
    assessment_cost: float = 0.0
    qa_cost: float = 0.0
    total_cost: float = 0.0
    
    # Quality metrics
    qa_score: Optional[int] = None
    lesson_count: int = 0
    module_count: int = 0
    
    # Model usage
    models_used: Dict[str, str] = field(default_factory=dict)
    
    # Errors (if any)
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class UsageTracker:
    """
    Track usage metrics for all course generations.
    
    Provides:
    - Per-user cost tracking
    - System-wide analytics
    - Quality trend analysis
    """
    
    def __init__(self):
        # In production, this would use a database
        self._metrics_store: Dict[str, CourseGenerationMetrics] = {}
        self._user_metrics: Dict[str, List[str]] = {}  # user_id -> [generation_ids]
    
    async def start_tracking(
        self,
        user_id: Optional[str],
        topic: str,
        quality_tier: str
    ) -> str:
        """
        Start tracking a new generation.
        
        Returns:
            generation_id to use for updates
        """
        metrics = CourseGenerationMetrics(
            user_id=user_id,
            topic=topic,
            quality_tier=quality_tier,
            created_at=datetime.utcnow()
        )
        
        generation_id = metrics.generation_id
        self._metrics_store[generation_id] = metrics
        
        if user_id:
            if user_id not in self._user_metrics:
                self._user_metrics[user_id] = []
            self._user_metrics[user_id].append(generation_id)
        
        logger.info(f"Started tracking generation: {generation_id}")
        return generation_id
    
    async def update_metrics(
        self,
        generation_id: str,
        updates: Dict[str, Any]
    ):
        """Update metrics for a generation"""
        if generation_id not in self._metrics_store:
            logger.warning(f"Unknown generation_id: {generation_id}")
            return
        
        metrics = self._metrics_store[generation_id]
        
        for key, value in updates.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)
        
        # Calculate totals
        metrics.total_tokens = sum([
            metrics.orchestrator_tokens,
            metrics.curriculum_tokens,
            metrics.content_creator_tokens,
            metrics.assessment_tokens,
            metrics.qa_tokens
        ])
        
        metrics.total_cost = sum([
            metrics.orchestrator_cost,
            metrics.curriculum_cost,
            metrics.content_creator_cost,
            metrics.assessment_cost,
            metrics.qa_cost
        ])
    
    async def complete_tracking(
        self,
        generation_id: str,
        course_id: str,
        duration_seconds: float,
        qa_score: int
    ):
        """Mark generation as complete and finalize metrics"""
        await self.update_metrics(generation_id, {
            "generation_status": "completed",
            "course_id": course_id,
            "total_duration_seconds": duration_seconds,
            "qa_score": qa_score
        })
        
        logger.info(f"Completed tracking for {generation_id}: ${self._metrics_store[generation_id].total_cost:.4f}")
    
    async def record_failure(
        self,
        generation_id: str,
        error_message: str
    ):
        """Record a failed generation"""
        await self.update_metrics(generation_id, {
            "generation_status": "failed",
            "error_message": error_message
        })
    
    async def get_user_analytics(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get analytics for a specific user.
        
        Returns:
            Dictionary with user's usage stats
        """
        if user_id not in self._user_metrics:
            return {
                "total_courses": 0,
                "total_cost": 0.0,
                "total_tokens": 0
            }
        
        generation_ids = self._user_metrics[user_id]
        metrics_list = [
            self._metrics_store[gid] for gid in generation_ids
            if gid in self._metrics_store
        ]
        
        # Filter by date range
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_metrics = [
            m for m in metrics_list
            if m.created_at >= cutoff_date
        ]
        
        if not recent_metrics:
            return {
                "total_courses": 0,
                "total_cost": 0.0,
                "total_tokens": 0
            }
        
        # Aggregate stats
        total_cost = sum(m.total_cost for m in recent_metrics)
        total_tokens = sum(m.total_tokens for m in recent_metrics)
        completed_count = sum(1 for m in recent_metrics if m.generation_status == "completed")
        
        avg_cost = total_cost / len(recent_metrics) if recent_metrics else 0
        avg_qa_score = sum(m.qa_score for m in recent_metrics if m.qa_score) / completed_count if completed_count else 0
        
        # Cost by tier
        cost_by_tier = {}
        for tier in ["ultra", "balanced", "fast", "custom"]:
            tier_metrics = [m for m in recent_metrics if m.quality_tier == tier]
            if tier_metrics:
                cost_by_tier[tier] = {
                    "count": len(tier_metrics),
                    "total_cost": sum(m.total_cost for m in tier_metrics),
                    "avg_cost": sum(m.total_cost for m in tier_metrics) / len(tier_metrics)
                }
        
        # Daily cost trend (last 7 days)
        daily_costs = []
        for i in range(7):
            date = datetime.utcnow() - timedelta(days=i)
            day_metrics = [
                m for m in recent_metrics
                if m.created_at.date() == date.date()
            ]
            daily_costs.append({
                "date": date.strftime("%Y-%m-%d"),
                "cost": sum(m.total_cost for m in day_metrics),
                "courses": len(day_metrics)
            })
        
        return {
            "period_days": days,
            "total_courses": len(recent_metrics),
            "completed_courses": completed_count,
            "failed_courses": sum(1 for m in recent_metrics if m.generation_status == "failed"),
            "total_cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "avg_cost_per_course": round(avg_cost, 4),
            "avg_qa_score": round(avg_qa_score, 1) if avg_qa_score else None,
            "cost_by_tier": cost_by_tier,
            "daily_trend": list(reversed(daily_costs))
        }
    
    async def get_system_analytics(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get system-wide analytics.
        
        Returns:
            Dictionary with aggregate system stats
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_metrics = [
            m for m in self._metrics_store.values()
            if m.created_at >= cutoff_date
        ]
        
        if not recent_metrics:
            return {"total_generations": 0}
        
        total_users = len(set(m.user_id for m in recent_metrics if m.user_id))
        total_cost = sum(m.total_cost for m in recent_metrics)
        total_tokens = sum(m.total_tokens for m in recent_metrics)
        completed = sum(1 for m in recent_metrics if m.generation_status == "completed")
        
        # Average generation time
        completed_metrics = [m for m in recent_metrics if m.generation_status == "completed"]
        avg_generation_time = (
            sum(m.total_duration_seconds for m in completed_metrics) / len(completed_metrics)
            if completed_metrics else 0
        )
        
        return {
            "period_days": days,
            "total_generations": len(recent_metrics),
            "completed_generations": completed,
            "unique_users": total_users,
            "total_cost_usd": round(total_cost, 2),
            "total_tokens": total_tokens,
            "avg_cost_per_generation": round(total_cost / len(recent_metrics), 4),
            "avg_generation_time_seconds": round(avg_generation_time, 1),
            "success_rate": round((completed / len(recent_metrics)) * 100, 1) if recent_metrics else 0
        }
    
    async def get_course_metrics(
        self,
        course_id: str
    ) -> Optional[CourseGenerationMetrics]:
        """Get metrics for a specific course"""
        for metrics in self._metrics_store.values():
            if metrics.course_id == course_id:
                return metrics
        return None


# Global instance
_usage_tracker: Optional[UsageTracker] = None


def get_usage_tracker() -> UsageTracker:
    """Get or create global usage tracker"""
    global _usage_tracker
    
    if _usage_tracker is None:
        _usage_tracker = UsageTracker()
    
    return _usage_tracker


# Helper function to track generation
async def track_course_generation(
    user_id: Optional[str],
    course_id: str,
    config: "PipelineConfig"
) -> None:
    """Helper to track a course generation"""
    tracker = get_usage_tracker()
    
    # This would be called in background task
    # For now, just log
    logger.info(f"Would track generation for user {user_id}, course {course_id}")
