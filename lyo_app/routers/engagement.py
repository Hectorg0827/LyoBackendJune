"""
Proactive Engagement API Routes

These endpoints allow users to:
- View pending nudges and notifications
- See their engagement patterns and stats
- Manage notification preferences
- Trigger on-demand engagement analysis
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db as get_async_db
from lyo_app.auth.models import User
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.services.proactive_engagement import (
    proactive_engagement_service,
    NudgeType,
    NudgePriority
)
from lyo_app.tasks.proactive_engagement import (
    analyze_user_engagement_task,
    get_pending_nudges_task
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engagement", tags=["Engagement"])


# ==================== Schemas ====================

class NudgeResponse(BaseModel):
    """A proactive nudge for the user."""
    type: str
    title: str
    message: str
    priority: str
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    context: Optional[dict] = None
    expires_at: Optional[datetime] = None


class EngagementPatternResponse(BaseModel):
    """User's engagement patterns and stats."""
    user_id: int
    preferred_hours: List[int]
    preferred_days: List[int]
    avg_session_duration_minutes: float
    avg_interactions_per_session: float
    last_active: Optional[datetime]
    current_streak: int
    longest_streak: int
    engagement_score: float
    engagement_level: str  # low, medium, high, excellent
    is_at_risk: bool


class NotificationPreferences(BaseModel):
    """User's notification preferences."""
    streak_reminders: bool = True
    spaced_rep_reminders: bool = True
    weekly_digest: bool = True
    comeback_nudges: bool = True
    quiet_hours_start: int = Field(default=22, ge=0, le=23)
    quiet_hours_end: int = Field(default=8, ge=0, le=23)
    max_nudges_per_day: int = Field(default=3, ge=0, le=10)


class EngagementStatsResponse(BaseModel):
    """Engagement statistics for dashboard."""
    total_nudges_sent: int
    nudges_acted_on: int
    action_rate: float
    streak_saves: int  # Times user saved streak after reminder
    items_reviewed_from_nudges: int
    engagement_trend: str  # improving, stable, declining


# ==================== Endpoints ====================

@router.get("/nudges", response_model=List[NudgeResponse])
async def get_pending_nudges(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get all pending nudges for the current user.

    These are personalized, timely reminders about:
    - Streaks about to break
    - Spaced repetition items due
    - Learning milestones
    - Comeback encouragement
    """
    try:
        nudges = await proactive_engagement_service.get_pending_nudges_for_user(
            user_id=current_user.id,
            db=db
        )

        return [
            NudgeResponse(
                type=n.nudge_type.value,
                title=n.title,
                message=n.message,
                priority=n.priority.value,
                action_url=n.action_url,
                action_label=n.action_label,
                context=n.context_data,
                expires_at=n.expires_at
            )
            for n in nudges
        ]

    except Exception as e:
        logger.exception(f"Failed to get nudges for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve nudges"
        )


@router.get("/patterns", response_model=EngagementPatternResponse)
async def get_engagement_patterns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get the user's engagement patterns.

    Shows when you're most active, your current streak,
    and personalized timing recommendations.
    """
    try:
        patterns = await proactive_engagement_service.analyze_user_patterns(
            user_id=current_user.id,
            db=db
        )

        # Determine engagement level
        score = patterns.engagement_score
        if score >= 0.8:
            level = "excellent"
        elif score >= 0.6:
            level = "high"
        elif score >= 0.4:
            level = "medium"
        else:
            level = "low"

        return EngagementPatternResponse(
            user_id=current_user.id,
            preferred_hours=patterns.preferred_hours,
            preferred_days=patterns.preferred_days,
            avg_session_duration_minutes=patterns.avg_session_duration,
            avg_interactions_per_session=patterns.avg_interactions_per_session,
            last_active=patterns.last_active,
            current_streak=patterns.current_streak,
            longest_streak=patterns.longest_streak,
            engagement_score=patterns.engagement_score,
            engagement_level=level,
            is_at_risk=patterns.is_at_risk
        )

    except Exception as e:
        logger.exception(f"Failed to get patterns for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve engagement patterns"
        )


@router.get("/optimal-time")
async def get_optimal_notification_time(
    priority: str = "medium",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get the optimal time to send a notification to this user.

    Based on their historical activity patterns and preferences.
    """
    try:
        priority_enum = NudgePriority(priority)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid priority. Must be one of: low, medium, high, critical"
        )

    try:
        optimal_time = await proactive_engagement_service.get_optimal_nudge_time(
            user_id=current_user.id,
            db=db,
            nudge_priority=priority_enum
        )

        return {
            "user_id": current_user.id,
            "optimal_time": optimal_time.isoformat(),
            "priority": priority,
            "note": "This is when you're typically most active"
        }

    except Exception as e:
        logger.exception(f"Failed to get optimal time for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to determine optimal time"
        )


@router.post("/analyze")
async def trigger_engagement_analysis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Trigger a fresh analysis of your engagement patterns.

    This queues a background task that analyzes your recent activity
    to update your engagement profile and notification timing.
    """
    try:
        # Queue the analysis task
        analyze_user_engagement_task.delay(user_id=current_user.id)

        return {
            "message": "Engagement analysis queued",
            "user_id": current_user.id,
            "status": "processing",
            "note": "Your engagement profile will be updated shortly"
        }

    except Exception as e:
        logger.exception(f"Failed to queue analysis for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue engagement analysis"
        )


@router.get("/streak")
async def get_streak_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get detailed streak status for the current user.

    Shows current streak, time until it breaks, and streak history.
    """
    from lyo_app.gamification.models import Streak
    from sqlalchemy import select, and_

    try:
        result = await db.execute(
            select(Streak)
            .where(
                and_(
                    Streak.user_id == current_user.id,
                    Streak.streak_type == "DAILY_LOGIN"
                )
            )
        )
        streak = result.scalar_one_or_none()

        if not streak:
            return {
                "current_streak": 0,
                "longest_streak": 0,
                "hours_until_break": None,
                "status": "no_streak",
                "message": "Start your learning streak today!"
            }

        hours_since = 0
        hours_until_break = None
        status_msg = "active"

        if streak.last_activity_at:
            hours_since = (datetime.utcnow() - streak.last_activity_at).total_seconds() / 3600
            hours_until_break = max(0, 24 - hours_since)

            if hours_until_break <= 0:
                status_msg = "broken"
            elif hours_until_break <= 4:
                status_msg = "at_risk"

        message = {
            "active": f"Great! Your {streak.current_count}-day streak is safe.",
            "at_risk": f"Warning: {hours_until_break:.1f} hours until your streak breaks!",
            "broken": "Your streak ended. Start fresh today!"
        }[status_msg]

        return {
            "current_streak": streak.current_count,
            "longest_streak": streak.longest_count,
            "last_activity": streak.last_activity_at,
            "hours_until_break": round(hours_until_break, 1) if hours_until_break else None,
            "status": status_msg,
            "message": message
        }

    except Exception as e:
        logger.exception(f"Failed to get streak for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve streak status"
        )


@router.get("/spaced-rep/due")
async def get_spaced_rep_due(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get spaced repetition items due for review.

    Shows what concepts need refreshing to maximize retention.
    """
    from lyo_app.personalization.models import SpacedRepetitionSchedule
    from sqlalchemy import select, and_

    try:
        now = datetime.utcnow()

        result = await db.execute(
            select(SpacedRepetitionSchedule)
            .where(
                and_(
                    SpacedRepetitionSchedule.user_id == current_user.id,
                    SpacedRepetitionSchedule.next_review <= now
                )
            )
            .order_by(SpacedRepetitionSchedule.next_review)
            .limit(20)
        )
        due_items = result.scalars().all()

        items = [
            {
                "skill_id": item.skill_id,
                "item_id": item.item_id,
                "last_review": item.last_review,
                "repetitions": item.repetitions,
                "easiness_factor": round(item.easiness_factor, 2),
                "overdue_hours": round(
                    (now - item.next_review).total_seconds() / 3600, 1
                ) if item.next_review else 0
            }
            for item in due_items
        ]

        return {
            "due_count": len(items),
            "items": items,
            "message": f"You have {len(items)} items ready for review" if items else "All caught up!"
        }

    except Exception as e:
        logger.exception(f"Failed to get due items for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve due items"
        )


@router.get("/weekly-summary")
async def get_weekly_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a summary of this week's learning activity.

    Shows sessions, XP earned, skills improved, and more.
    """
    from lyo_app.ai_agents.models import MentorInteraction
    from lyo_app.gamification.models import UserXP
    from lyo_app.personalization.models import LearnerMastery
    from sqlalchemy import select, func, and_
    from datetime import timedelta

    try:
        since = datetime.utcnow() - timedelta(days=7)

        # Get interaction count
        interaction_result = await db.execute(
            select(func.count(MentorInteraction.id))
            .where(
                and_(
                    MentorInteraction.user_id == current_user.id,
                    MentorInteraction.timestamp >= since
                )
            )
        )
        interaction_count = interaction_result.scalar() or 0

        # Get session count (distinct sessions)
        session_result = await db.execute(
            select(func.count(func.distinct(MentorInteraction.session_id)))
            .where(
                and_(
                    MentorInteraction.user_id == current_user.id,
                    MentorInteraction.timestamp >= since
                )
            )
        )
        session_count = session_result.scalar() or 0

        # Get XP earned
        xp_result = await db.execute(
            select(func.sum(UserXP.xp_amount))
            .where(
                and_(
                    UserXP.user_id == current_user.id,
                    UserXP.earned_at >= since
                )
            )
        )
        xp_earned = xp_result.scalar() or 0

        # Get mastery improvements
        mastery_result = await db.execute(
            select(LearnerMastery)
            .where(
                and_(
                    LearnerMastery.user_id == current_user.id,
                    LearnerMastery.last_seen >= since
                )
            )
        )
        skills_touched = mastery_result.scalars().all()
        skills_improved = len([s for s in skills_touched if s.mastery_level >= 0.7])

        return {
            "period": "last_7_days",
            "sessions": session_count,
            "interactions": interaction_count,
            "xp_earned": int(xp_earned),
            "skills_practiced": len(skills_touched),
            "skills_mastered": skills_improved,
            "avg_session_length_minutes": round(
                interaction_count / session_count * 2, 1
            ) if session_count > 0 else 0,
            "summary": _generate_weekly_summary_message(
                session_count, xp_earned, skills_improved
            )
        }

    except Exception as e:
        logger.exception(f"Failed to get weekly summary for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve weekly summary"
        )


def _generate_weekly_summary_message(sessions: int, xp: int, mastered: int) -> str:
    """Generate a personalized weekly summary message."""
    if sessions == 0:
        return "No activity this week. Jump back in - your learning journey awaits!"
    elif sessions >= 7:
        return f"Amazing week! {sessions} sessions, {xp} XP earned. You're on fire!"
    elif sessions >= 3:
        return f"Good progress! {sessions} sessions this week. Keep the momentum going!"
    else:
        return f"You learned {sessions} time(s) this week. A little more consistency will boost your results!"


# Attach helper to module for access in endpoint
import types
router._generate_weekly_summary_message = _generate_weekly_summary_message
