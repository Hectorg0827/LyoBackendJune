"""
Proactive Intervention Engine

Decides when and how to reach out to users proactively.
Uses time-based, event-based, and behavioral triggers.
"""

import logging
from datetime import datetime, time, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from .models import (
    Intervention,
    InterventionLog,
    InterventionType,
    UserNotificationPreferences,
    UserState
)
from lyo_app.gamification.models import Streak, UserLevel
from lyo_app.learning.models import CourseEnrollment, LessonCompletion
from lyo_app.personalization.models import LearnerMastery, LearnerState

logger = logging.getLogger(__name__)


class InterventionEngine:
    """
    Proactive intervention system that decides when and how to reach out to users.
    """

    def __init__(self):
        self.max_interventions_per_evaluation = 3

    async def evaluate_interventions(
        self,
        user_id: int,
        db: AsyncSession
    ) -> List[Intervention]:
        """
        Evaluate all possible interventions for a user.
        Returns prioritized list of interventions to execute.
        """
        interventions = []

        # Get user state
        user_state = await self._get_user_state(user_id, db)

        # 1. Check time-based triggers
        time_interventions = await self._check_time_triggers(user_state, db)
        interventions.extend(time_interventions)

        # 2. Check event-based triggers
        event_interventions = await self._check_event_triggers(user_state, db)
        interventions.extend(event_interventions)

        # 3. Prioritize and filter
        interventions = self._prioritize_interventions(interventions)

        # 4. Respect user preferences and fatigue
        interventions = await self._apply_fatigue_filter(interventions, user_id, db)

        return interventions

    async def _get_user_state(
        self,
        user_id: int,
        db: AsyncSession
    ) -> UserState:
        """
        Build user state from multiple data sources.
        """
        state = UserState(user_id)

        # Get last activity
        stmt = select(LearnerState).where(LearnerState.user_id == user_id)
        result = await db.execute(stmt)
        learner_state = result.scalar_one_or_none()

        if learner_state:
            state.last_activity_hours = (
                datetime.utcnow() - learner_state.updated_at
            ).total_seconds() / 3600

        # Get current streak
        stmt = select(Streak).where(
            and_(
                Streak.user_id == user_id,
                Streak.streak_type == "daily_login"
            )
        )
        result = await db.execute(stmt)
        streak = result.scalar_one_or_none()

        if streak:
            state.current_streak = streak.current_count
            state.longest_streak = streak.max_count

        # Check if studied today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count()).select_from(LessonCompletion).where(
            and_(
                LessonCompletion.user_id == user_id,
                LessonCompletion.completed_at >= today_start
            )
        )
        result = await db.execute(stmt)
        completions_today = result.scalar()
        state.studied_today = completions_today > 0

        # Get session count this week
        week_start = datetime.utcnow() - timedelta(days=7)
        stmt = select(func.count()).select_from(LessonCompletion).where(
            and_(
                LessonCompletion.user_id == user_id,
                LessonCompletion.completed_at >= week_start
            )
        )
        result = await db.execute(stmt)
        state.session_count_week = result.scalar() or 0

        # Get course progress
        stmt = select(CourseEnrollment).where(
            CourseEnrollment.user_id == user_id
        ).order_by(desc(CourseEnrollment.progress)).limit(1)
        result = await db.execute(stmt)
        enrollment = result.scalar_one_or_none()

        if enrollment:
            state.current_course_progress = enrollment.progress or 0.0

        # Get primary subject (most practiced)
        stmt = select(
            LearnerMastery.skill_id,
            func.count(LearnerMastery.attempts).label('attempt_count')
        ).where(
            LearnerMastery.user_id == user_id
        ).group_by(LearnerMastery.skill_id).order_by(
            desc('attempt_count')
        ).limit(1)
        result = await db.execute(stmt)
        row = result.first()

        if row:
            state.primary_subject = row[0]

        return state

    async def _check_time_triggers(
        self,
        user_state: UserState,
        db: AsyncSession
    ) -> List[Intervention]:
        """Check for time-based intervention opportunities."""
        interventions = []
        current_time = datetime.now()
        current_hour = current_time.hour

        # Morning ritual (7-9 AM if user usually studies in morning)
        if 7 <= current_hour <= 9 and user_state.usual_study_start_time:
            if abs((current_time.hour - user_state.usual_study_start_time.hour)) <= 1:
                interventions.append(Intervention(
                    intervention_type=InterventionType.MORNING_RITUAL,
                    priority=8,
                    title="Ready to start your day?",
                    message=f"Good morning! Your usual {user_state.primary_subject or 'study'} session starts now.",
                    action="start_session",
                    timing="immediate"
                ))

        # Evening reflection (8-10 PM if user studied today)
        if 20 <= current_hour <= 22 and user_state.studied_today:
            interventions.append(Intervention(
                intervention_type=InterventionType.EVENING_REFLECTION,
                priority=5,
                title="Great work today!",
                message="Quick reflection: What clicked for you today?",
                action="reflection_prompt",
                timing="immediate"
            ))

        # Pre-study check-in (before usual study time)
        if user_state.usual_study_start_time:
            minutes_until_study = (
                user_state.usual_study_start_time.hour * 60 +
                user_state.usual_study_start_time.minute -
                current_hour * 60 -
                current_time.minute
            )
            if 0 <= minutes_until_study <= 15:  # 15 min before
                interventions.append(Intervention(
                    intervention_type=InterventionType.PRE_STUDY_CHECKIN,
                    priority=6,
                    title="Study time approaching",
                    message="Your study session starts soon. Ready?",
                    action="start_session",
                    timing="immediate"
                ))

        return interventions

    async def _check_event_triggers(
        self,
        user_state: UserState,
        db: AsyncSession
    ) -> List[Intervention]:
        """Check for event-based triggers."""
        interventions = []

        # Streak at risk (if current streak > 7 days and last activity > 20 hours)
        if user_state.current_streak > 7 and user_state.last_activity_hours > 20:
            interventions.append(Intervention(
                intervention_type=InterventionType.STREAK_PRESERVATION,
                priority=9,
                title=f"Don't break your {user_state.current_streak}-day streak!",
                message="Just 5 minutes of practice keeps it alive.",
                action="quick_practice",
                timing="immediate"
            ))

        # Course completion nearby (>85% progress)
        if user_state.current_course_progress > 0.85:
            remaining = int((1.0 - user_state.current_course_progress) * 100)
            interventions.append(Intervention(
                intervention_type=InterventionType.COMPLETION_PUSH,
                priority=6,
                title="You're so close!",
                message=f"Just {remaining}% left to complete the course.",
                action="view_remaining",
                timing="immediate"
            ))

        # Check for level up milestone
        stmt = select(UserLevel).where(UserLevel.user_id == user_state.user_id)
        result = await db.execute(stmt)
        user_level = result.scalar_one_or_none()

        if user_level:
            # Check if recently leveled up (within last hour)
            if user_level.updated_at and (datetime.utcnow() - user_level.updated_at).total_seconds() < 3600:
                interventions.append(Intervention(
                    intervention_type=InterventionType.MILESTONE_CELEBRATION,
                    priority=10,
                    title="🎉 Level Up!",
                    message=f"You just reached Level {user_level.current_level}!",
                    action="celebrate",
                    timing="immediate"
                ))

        return interventions

    def _prioritize_interventions(
        self,
        interventions: List[Intervention]
    ) -> List[Intervention]:
        """
        Prioritize interventions by urgency and importance.
        """
        # Sort by priority score (descending)
        interventions.sort(key=lambda x: x.priority, reverse=True)

        # Take top N
        return interventions[:self.max_interventions_per_evaluation]

    async def _apply_fatigue_filter(
        self,
        interventions: List[Intervention],
        user_id: int,
        db: AsyncSession
    ) -> List[Intervention]:
        """
        Respect user preferences and notification fatigue.
        """
        # Get user preferences
        stmt = select(UserNotificationPreferences).where(
            UserNotificationPreferences.user_id == user_id
        )
        result = await db.execute(stmt)
        prefs = result.scalar_one_or_none()

        if not prefs:
            # Use defaults if no preferences set
            prefs = UserNotificationPreferences(
                user_id=user_id,
                max_notifications_per_day=5
            )

        # Check DND
        if prefs.dnd_enabled:
            return []

        # Check quiet hours
        current_time = datetime.now().time()
        if prefs.quiet_hours_start and prefs.quiet_hours_end:
            if self._in_quiet_hours(current_time, prefs.quiet_hours_start, prefs.quiet_hours_end):
                # Only send priority 10 interventions during quiet hours
                interventions = [i for i in interventions if i.priority == 10]

        # Check daily limit
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count()).select_from(InterventionLog).where(
            and_(
                InterventionLog.user_id == user_id,
                InterventionLog.triggered_at >= today_start
            )
        )
        result = await db.execute(stmt)
        todays_count = result.scalar() or 0

        if todays_count >= prefs.max_notifications_per_day:
            # Only critical interventions
            interventions = [i for i in interventions if i.priority >= 9]

        # Check recent notification frequency (last 4 hours)
        four_hours_ago = datetime.utcnow() - timedelta(hours=4)
        stmt = select(func.count()).select_from(InterventionLog).where(
            and_(
                InterventionLog.user_id == user_id,
                InterventionLog.triggered_at >= four_hours_ago
            )
        )
        result = await db.execute(stmt)
        recent_count = result.scalar() or 0

        if recent_count >= 3:
            # Too many recent notifications, only send critical
            interventions = [i for i in interventions if i.priority >= 9]

        # Filter by user's disabled intervention types
        if prefs.disabled_intervention_types:
            interventions = [
                i for i in interventions
                if i.intervention_type not in prefs.disabled_intervention_types
            ]

        return interventions

    def _in_quiet_hours(
        self,
        current_time: time,
        quiet_start: time,
        quiet_end: time
    ) -> bool:
        """Check if current time is in quiet hours."""
        if quiet_start < quiet_end:
            # Normal case: 22:00 - 08:00
            return quiet_start <= current_time <= quiet_end
        else:
            # Wraps midnight: 22:00 - 08:00 next day
            return current_time >= quiet_start or current_time <= quiet_end

    async def log_intervention(
        self,
        user_id: int,
        intervention: Intervention,
        db: AsyncSession,
        organization_id: Optional[int] = None
    ) -> InterventionLog:
        """
        Log an intervention that was triggered.
        """
        log = InterventionLog(
            user_id=user_id,
            organization_id=organization_id,
            intervention_type=intervention.intervention_type,
            priority=intervention.priority,
            title=intervention.title,
            message=intervention.message,
            action=intervention.action,
            context=intervention.context
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)

        return log

    async def record_intervention_response(
        self,
        intervention_log_id: int,
        user_response: str,
        db: AsyncSession
    ):
        """
        Record user's response to an intervention.
        """
        stmt = select(InterventionLog).where(InterventionLog.id == intervention_log_id)
        result = await db.execute(stmt)
        log = result.scalar_one_or_none()

        if log:
            log.user_response = user_response
            log.response_at = datetime.utcnow()
            if not log.delivered_at:
                log.delivered_at = datetime.utcnow()
            await db.commit()


# Global singleton instance
intervention_engine = InterventionEngine()
