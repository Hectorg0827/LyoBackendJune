"""
Relationship Tracker — Orchestrates relationship-level queries:
journey summary, weekly review, and relationship health.
Part of the Persistent Relationship System (Pillar 4).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Milestone, RelationshipMemory, PersonalityProfile
from .milestone_engine import get_milestones, count_milestones
from .memory_system import count_memories
from .personality_adapter import get_personality
from .schemas import (
    JourneySummaryResponse,
    MilestoneRead,
    PersonalityProfileRead,
    WeeklyReviewResponse,
)

from lyo_app.auth.models import User
from lyo_app.evolution.goals_models import UserGoal, GoalStatus
from lyo_app.events.models import LearningEvent, EventType

logger = logging.getLogger(__name__)


async def get_journey_summary(db: AsyncSession, user_id: int) -> JourneySummaryResponse:
    """Build a holistic summary of the learner's journey with Lyo."""
    # User join date
    user_q = await db.execute(select(User).where(User.id == user_id))
    user = user_q.scalar_one_or_none()
    days_since_joined = (datetime.utcnow() - user.created_at).days if user else 0

    # Milestones
    milestones = await get_milestones(db, user_id, limit=5)
    total_milestones = await count_milestones(db, user_id)
    total_memories = await count_memories(db, user_id)

    # Personality
    personality = await get_personality(db, user_id)

    # Goals achieved
    goals_q = await db.execute(
        select(func.count(UserGoal.id)).where(
            and_(UserGoal.user_id == user_id, UserGoal.status == GoalStatus.ACHIEVED)
        )
    )
    goals_achieved = goals_q.scalar() or 0

    # Streak (simplified: count consecutive days with events ending today)
    streak = await _compute_streak(db, user_id)

    return JourneySummaryResponse(
        days_since_joined=days_since_joined,
        total_milestones=total_milestones,
        recent_milestones=[MilestoneRead.model_validate(m) for m in milestones],
        total_memories=total_memories,
        personality_snapshot=PersonalityProfileRead.model_validate(personality),
        streak_days=streak,
        goals_achieved=goals_achieved,
    )


async def get_weekly_review(db: AsyncSession, user_id: int) -> WeeklyReviewResponse:
    """Generate a summary of the past 7 days for the weekly review screen."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # Events in past week
    events_q = await db.execute(
        select(func.count(LearningEvent.id)).where(
            and_(
                LearningEvent.user_id == user_id,
                LearningEvent.timestamp >= week_ago,
            )
        )
    )
    events_count = events_q.scalar() or 0

    # Reflections
    reflections_q = await db.execute(
        select(func.count(LearningEvent.id)).where(
            and_(
                LearningEvent.user_id == user_id,
                LearningEvent.timestamp >= week_ago,
                LearningEvent.event_type == EventType.REFLECTION,
            )
        )
    )
    reflections_count = reflections_q.scalar() or 0

    # Milestones this week
    milestones_q = await db.execute(
        select(Milestone).where(
            and_(
                Milestone.user_id == user_id,
                Milestone.achieved_at >= week_ago,
            )
        )
    )
    new_milestones = [MilestoneRead.model_validate(m) for m in milestones_q.scalars().all()]

    # Goals progressed (goals with a snapshot this week)
    from lyo_app.evolution.goals_models import GoalProgressSnapshot
    goals_q = await db.execute(
        select(func.count(func.distinct(GoalProgressSnapshot.goal_id))).where(
            GoalProgressSnapshot.recorded_at >= week_ago
        )
    )
    goals_progressed = goals_q.scalar() or 0

    # Momentum trend
    trend = "stable"
    if events_count > 10:
        trend = "rising"
    elif events_count < 3:
        trend = "declining"

    return WeeklyReviewResponse(
        period_start=week_ago.isoformat(),
        period_end=now.isoformat(),
        lessons_completed=events_count,  # approximation
        events_logged=events_count,
        reflections_submitted=reflections_count,
        goals_progressed=goals_progressed,
        new_milestones=new_milestones,
        momentum_trend=trend,
        highlight=f"{events_count} learning events this week!" if events_count > 0 else None,
    )


async def _compute_streak(db: AsyncSession, user_id: int) -> int:
    """Count consecutive days with at least one learning event ending today."""
    streak = 0
    today = datetime.utcnow().date()
    for i in range(365):  # max lookback
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day, datetime.max.time())
        q = await db.execute(
            select(func.count(LearningEvent.id)).where(
                and_(
                    LearningEvent.user_id == user_id,
                    LearningEvent.timestamp >= day_start,
                    LearningEvent.timestamp <= day_end,
                )
            )
        )
        if (q.scalar() or 0) > 0:
            streak += 1
        else:
            break
    return streak
