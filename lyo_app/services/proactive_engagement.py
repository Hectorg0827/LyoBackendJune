"""
Proactive Engagement Service - Anticipatory User Engagement

This service transforms Lyo from a reactive tool into an anticipatory companion
that reaches out at the right moments. It analyzes user patterns to determine:
- WHEN to engage (optimal timing based on login patterns)
- WHAT to send (personalized nudges based on context)
- HOW to engage (tone/style based on user state)

The goal is to feel helpful, not spammy. Every nudge should feel like it's
coming from someone who genuinely cares about the user's progress.
"""

import logging
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from lyo_app.auth.models import User
from lyo_app.ai_agents.models import MentorInteraction, UserEngagementState
from lyo_app.personalization.models import (
    LearnerState, LearnerMastery, SpacedRepetitionSchedule, AffectState
)
from lyo_app.gamification.models import Streak, UserXP

logger = logging.getLogger(__name__)


class NudgeType(str, Enum):
    """Types of proactive nudges we can send."""
    STREAK_REMINDER = "streak_reminder"
    STREAK_CELEBRATION = "streak_celebration"
    STREAK_RECOVERY = "streak_recovery"
    SPACED_REP_DUE = "spaced_rep_due"
    LEARNING_RECAP = "learning_recap"
    WEEKLY_DIGEST = "weekly_digest"
    ENCOURAGEMENT = "encouragement"
    COMEBACK = "comeback"
    MILESTONE = "milestone"
    PERSONALIZED_TIP = "personalized_tip"


class NudgePriority(str, Enum):
    """Priority levels for nudges (affects timing and delivery)."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Nudge:
    """A proactive nudge to send to a user."""
    user_id: int
    nudge_type: NudgeType
    title: str
    message: str
    priority: NudgePriority
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    context_data: Optional[Dict[str, Any]] = None
    scheduled_for: Optional[datetime] = None
    expires_at: Optional[datetime] = None


@dataclass
class UserEngagementPattern:
    """Analyzed engagement patterns for a user."""
    user_id: int
    preferred_hours: List[int]  # Hours of day user is typically active (0-23)
    preferred_days: List[int]  # Days of week (0=Monday, 6=Sunday)
    avg_session_duration: float  # Minutes
    avg_interactions_per_session: float
    last_active: Optional[datetime]
    current_streak: int
    longest_streak: int
    engagement_score: float  # 0-1, overall engagement health
    is_at_risk: bool  # True if user might churn


class ProactiveEngagementService:
    """
    Orchestrates proactive user engagement.

    Key principles:
    1. Respect user attention - don't spam
    2. Be helpful, not annoying
    3. Personalize timing and content
    4. Learn from engagement/dismissal patterns
    """

    # Nudge frequency limits
    MAX_NUDGES_PER_DAY = 3
    MIN_HOURS_BETWEEN_NUDGES = 4
    QUIET_HOURS_START = 22  # 10 PM
    QUIET_HOURS_END = 8     # 8 AM

    # Engagement thresholds
    STREAK_WARNING_HOURS = 20  # Remind if streak will break in 4 hours
    INACTIVE_DAYS_COMEBACK = 7  # Send comeback message after 7 days
    AT_RISK_INACTIVE_DAYS = 3   # Consider user at risk after 3 days

    def __init__(self):
        self.nudge_templates = self._load_nudge_templates()

    async def analyze_user_patterns(
        self,
        user_id: int,
        db: AsyncSession,
        lookback_days: int = 30
    ) -> UserEngagementPattern:
        """
        Analyze a user's engagement patterns to determine optimal engagement timing.
        """
        since = datetime.utcnow() - timedelta(days=lookback_days)

        # Get interaction timestamps
        result = await db.execute(
            select(MentorInteraction.timestamp)
            .where(
                and_(
                    MentorInteraction.user_id == user_id,
                    MentorInteraction.timestamp >= since
                )
            )
            .order_by(desc(MentorInteraction.timestamp))
        )
        timestamps = [row[0] for row in result.fetchall()]

        # Analyze preferred hours
        hour_counts = defaultdict(int)
        day_counts = defaultdict(int)
        for ts in timestamps:
            hour_counts[ts.hour] += 1
            day_counts[ts.weekday()] += 1

        # Get top 3 preferred hours
        preferred_hours = sorted(hour_counts.keys(), key=lambda h: hour_counts[h], reverse=True)[:3]
        if not preferred_hours:
            preferred_hours = [9, 12, 19]  # Default: morning, noon, evening

        # Get preferred days
        preferred_days = sorted(day_counts.keys(), key=lambda d: day_counts[d], reverse=True)[:3]
        if not preferred_days:
            preferred_days = [0, 1, 2, 3, 4]  # Default: weekdays

        # Calculate session metrics
        sessions = self._group_into_sessions(timestamps, gap_minutes=30)
        avg_duration = sum(s['duration'] for s in sessions) / len(sessions) if sessions else 0
        avg_interactions = sum(s['count'] for s in sessions) / len(sessions) if sessions else 0

        # Get streak info
        streak_result = await db.execute(
            select(Streak)
            .where(Streak.user_id == user_id)
            .order_by(desc(Streak.current_count))
            .limit(1)
        )
        streak = streak_result.scalar_one_or_none()
        current_streak = streak.current_count if streak else 0
        longest_streak = streak.longest_count if streak else 0

        # Determine last active
        last_active = timestamps[0] if timestamps else None

        # Calculate engagement score
        engagement_score = self._calculate_engagement_score(
            interaction_count=len(timestamps),
            lookback_days=lookback_days,
            current_streak=current_streak,
            avg_session_duration=avg_duration
        )

        # Determine if at risk
        days_inactive = (datetime.utcnow() - last_active).days if last_active else 999
        is_at_risk = days_inactive >= self.AT_RISK_INACTIVE_DAYS

        return UserEngagementPattern(
            user_id=user_id,
            preferred_hours=preferred_hours,
            preferred_days=preferred_days,
            avg_session_duration=avg_duration,
            avg_interactions_per_session=avg_interactions,
            last_active=last_active,
            current_streak=current_streak,
            longest_streak=longest_streak,
            engagement_score=engagement_score,
            is_at_risk=is_at_risk
        )

    async def get_optimal_nudge_time(
        self,
        user_id: int,
        db: AsyncSession,
        nudge_priority: NudgePriority = NudgePriority.MEDIUM
    ) -> datetime:
        """
        Determine the optimal time to send a nudge to a user.
        """
        patterns = await self.analyze_user_patterns(user_id, db)
        now = datetime.utcnow()

        # For critical nudges, send immediately (but respect quiet hours)
        if nudge_priority == NudgePriority.CRITICAL:
            if self._is_quiet_hours(now):
                return self._next_non_quiet_hour(now)
            return now

        # Find next preferred hour
        current_hour = now.hour
        for hour in patterns.preferred_hours:
            if hour > current_hour:
                # Same day, later hour
                optimal = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if not self._is_quiet_hours(optimal):
                    return optimal

        # Tomorrow, first preferred hour
        tomorrow = now + timedelta(days=1)
        for hour in patterns.preferred_hours:
            optimal = tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
            if not self._is_quiet_hours(optimal):
                return optimal

        # Fallback: tomorrow at 9 AM
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

    async def generate_streak_nudge(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Optional[Nudge]:
        """
        Generate a streak-related nudge if appropriate.
        """
        # Get user's streak status
        result = await db.execute(
            select(Streak)
            .where(
                and_(
                    Streak.user_id == user_id,
                    Streak.streak_type == "DAILY_LOGIN"
                )
            )
        )
        streak = result.scalar_one_or_none()

        if not streak:
            return None

        # Check if streak is about to break
        if streak.last_activity_at:
            hours_since = (datetime.utcnow() - streak.last_activity_at).total_seconds() / 3600
            hours_until_break = 24 - hours_since

            if 0 < hours_until_break <= 4 and streak.current_count >= 3:
                # Streak warning
                return Nudge(
                    user_id=user_id,
                    nudge_type=NudgeType.STREAK_REMINDER,
                    title=f"Don't lose your {streak.current_count}-day streak!",
                    message=f"You've been learning for {streak.current_count} days straight. "
                            f"Just a quick session keeps the streak alive!",
                    priority=NudgePriority.HIGH,
                    action_label="Continue Learning",
                    action_url="/learn",
                    context_data={
                        "streak_count": streak.current_count,
                        "hours_until_break": round(hours_until_break, 1)
                    },
                    expires_at=datetime.utcnow() + timedelta(hours=hours_until_break)
                )

            if hours_since >= 24 and streak.current_count > 0:
                # Streak broken - recovery message
                return Nudge(
                    user_id=user_id,
                    nudge_type=NudgeType.STREAK_RECOVERY,
                    title="Let's start a new streak!",
                    message=f"Your {streak.current_count}-day streak ended, but that's okay! "
                            "Every expert was once a beginner. Start fresh today.",
                    priority=NudgePriority.MEDIUM,
                    action_label="Start Fresh",
                    action_url="/learn",
                    context_data={"previous_streak": streak.current_count}
                )

        # Streak milestone celebration
        if streak.current_count in [7, 14, 30, 50, 100, 365]:
            return Nudge(
                user_id=user_id,
                nudge_type=NudgeType.STREAK_CELEBRATION,
                title=f"Amazing! {streak.current_count}-day streak!",
                message=self._get_streak_celebration_message(streak.current_count),
                priority=NudgePriority.MEDIUM,
                action_label="Keep Going",
                action_url="/learn",
                context_data={"streak_count": streak.current_count}
            )

        return None

    async def generate_spaced_rep_nudge(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Optional[Nudge]:
        """
        Generate a nudge for spaced repetition items due for review.
        """
        now = datetime.utcnow()

        # Get items due for review
        result = await db.execute(
            select(SpacedRepetitionSchedule)
            .where(
                and_(
                    SpacedRepetitionSchedule.user_id == user_id,
                    SpacedRepetitionSchedule.next_review <= now
                )
            )
        )
        due_items = result.scalars().all()

        if not due_items:
            return None

        count = len(due_items)

        # Get the skill names for context
        skill_ids = list(set(item.skill_id for item in due_items[:5]))

        if count == 1:
            message = f"One concept is ready for review: {skill_ids[0]}. A quick review keeps it fresh!"
        elif count <= 5:
            message = f"{count} concepts are ready for review. This will only take a few minutes!"
        else:
            message = f"You have {count} concepts ready for review. Tackle a few to keep your knowledge sharp!"

        return Nudge(
            user_id=user_id,
            nudge_type=NudgeType.SPACED_REP_DUE,
            title="Time to review!",
            message=message,
            priority=NudgePriority.MEDIUM if count < 10 else NudgePriority.HIGH,
            action_label=f"Review {min(count, 10)} items",
            action_url="/review",
            context_data={
                "due_count": count,
                "skills": skill_ids
            }
        )

    async def generate_comeback_nudge(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Optional[Nudge]:
        """
        Generate a nudge for users who haven't been active recently.
        """
        user = await db.get(User, user_id)
        if not user:
            return None

        # Check last activity
        result = await db.execute(
            select(func.max(MentorInteraction.timestamp))
            .where(MentorInteraction.user_id == user_id)
        )
        last_interaction = result.scalar()

        if not last_interaction:
            return None

        days_inactive = (datetime.utcnow() - last_interaction).days

        if days_inactive < self.INACTIVE_DAYS_COMEBACK:
            return None

        # Get user's memory for personalization
        memory = user.user_context_summary or ""

        # Personalize message based on what we know
        if "struggling" in memory.lower() or "difficult" in memory.lower():
            message = ("We noticed you've been away. Learning can be tough, but you've got this! "
                      "Come back when you're ready - we'll pick up right where you left off.")
        elif days_inactive > 30:
            message = ("It's been a while! Your learning journey is waiting. "
                      "Even 5 minutes today can reignite your progress.")
        else:
            message = (f"We miss you! It's been {days_inactive} days since your last session. "
                      "Ready to jump back in?")

        return Nudge(
            user_id=user_id,
            nudge_type=NudgeType.COMEBACK,
            title=f"Welcome back, {user.first_name or 'learner'}!",
            message=message,
            priority=NudgePriority.LOW,
            action_label="Resume Learning",
            action_url="/learn",
            context_data={
                "days_inactive": days_inactive,
                "has_memory": bool(memory)
            }
        )

    async def generate_weekly_digest(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Optional[Nudge]:
        """
        Generate a weekly learning digest for the user.
        """
        since = datetime.utcnow() - timedelta(days=7)

        # Get weekly stats
        interaction_result = await db.execute(
            select(func.count(MentorInteraction.id))
            .where(
                and_(
                    MentorInteraction.user_id == user_id,
                    MentorInteraction.timestamp >= since
                )
            )
        )
        interaction_count = interaction_result.scalar() or 0

        if interaction_count == 0:
            return None  # No activity, no digest

        # Get XP earned this week
        xp_result = await db.execute(
            select(func.sum(UserXP.xp_amount))
            .where(
                and_(
                    UserXP.user_id == user_id,
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
                    LearnerMastery.user_id == user_id,
                    LearnerMastery.last_seen >= since
                )
            )
        )
        improved_skills = mastery_result.scalars().all()
        skills_improved = len([s for s in improved_skills if s.mastery_level >= 0.7])

        message = f"This week: {interaction_count} learning sessions"
        if xp_earned > 0:
            message += f", {xp_earned} XP earned"
        if skills_improved > 0:
            message += f", {skills_improved} skills mastered"
        message += ". Keep up the great work!"

        return Nudge(
            user_id=user_id,
            nudge_type=NudgeType.WEEKLY_DIGEST,
            title="Your Weekly Learning Recap",
            message=message,
            priority=NudgePriority.LOW,
            action_label="See Details",
            action_url="/progress",
            context_data={
                "interaction_count": interaction_count,
                "xp_earned": xp_earned,
                "skills_improved": skills_improved
            }
        )

    async def get_pending_nudges_for_user(
        self,
        user_id: int,
        db: AsyncSession
    ) -> List[Nudge]:
        """
        Get all pending nudges for a user, prioritized.
        """
        nudges = []

        # Check each nudge type
        streak_nudge = await self.generate_streak_nudge(user_id, db)
        if streak_nudge:
            nudges.append(streak_nudge)

        spaced_rep_nudge = await self.generate_spaced_rep_nudge(user_id, db)
        if spaced_rep_nudge:
            nudges.append(spaced_rep_nudge)

        comeback_nudge = await self.generate_comeback_nudge(user_id, db)
        if comeback_nudge:
            nudges.append(comeback_nudge)

        # Sort by priority
        priority_order = {
            NudgePriority.CRITICAL: 0,
            NudgePriority.HIGH: 1,
            NudgePriority.MEDIUM: 2,
            NudgePriority.LOW: 3
        }
        nudges.sort(key=lambda n: priority_order[n.priority])

        # Limit to max nudges per day
        return nudges[:self.MAX_NUDGES_PER_DAY]

    # ==================== Private Methods ====================

    def _group_into_sessions(
        self,
        timestamps: List[datetime],
        gap_minutes: int = 30
    ) -> List[Dict[str, Any]]:
        """Group timestamps into sessions based on gap threshold."""
        if not timestamps:
            return []

        sessions = []
        current_session = {"start": timestamps[0], "end": timestamps[0], "count": 1}

        for i in range(1, len(timestamps)):
            gap = (timestamps[i - 1] - timestamps[i]).total_seconds() / 60

            if gap <= gap_minutes:
                current_session["end"] = timestamps[i]
                current_session["count"] += 1
            else:
                current_session["duration"] = (
                    current_session["start"] - current_session["end"]
                ).total_seconds() / 60
                sessions.append(current_session)
                current_session = {"start": timestamps[i], "end": timestamps[i], "count": 1}

        # Add last session
        current_session["duration"] = (
            current_session["start"] - current_session["end"]
        ).total_seconds() / 60
        sessions.append(current_session)

        return sessions

    def _calculate_engagement_score(
        self,
        interaction_count: int,
        lookback_days: int,
        current_streak: int,
        avg_session_duration: float
    ) -> float:
        """Calculate overall engagement health score (0-1)."""
        # Frequency score (0-0.4)
        expected_interactions = lookback_days * 3  # 3 per day target
        frequency_score = min(interaction_count / expected_interactions, 1.0) * 0.4

        # Streak score (0-0.3)
        streak_score = min(current_streak / 30, 1.0) * 0.3  # 30-day streak = max

        # Session depth score (0-0.3)
        depth_score = min(avg_session_duration / 15, 1.0) * 0.3  # 15 min = max

        return frequency_score + streak_score + depth_score

    def _is_quiet_hours(self, dt: datetime) -> bool:
        """Check if the given time is during quiet hours."""
        hour = dt.hour
        if self.QUIET_HOURS_START > self.QUIET_HOURS_END:
            # Quiet hours span midnight
            return hour >= self.QUIET_HOURS_START or hour < self.QUIET_HOURS_END
        return self.QUIET_HOURS_START <= hour < self.QUIET_HOURS_END

    def _next_non_quiet_hour(self, dt: datetime) -> datetime:
        """Get the next datetime that's not in quiet hours."""
        result = dt.replace(minute=0, second=0, microsecond=0)
        while self._is_quiet_hours(result):
            result += timedelta(hours=1)
        return result

    def _get_streak_celebration_message(self, streak_count: int) -> str:
        """Get a celebration message for streak milestones."""
        messages = {
            7: "A full week of learning! You're building a powerful habit.",
            14: "Two weeks strong! Your consistency is inspiring.",
            30: "A whole month of daily learning! You're unstoppable.",
            50: "50 days! You're in the top 1% of learners.",
            100: "100 DAYS! This is legendary dedication.",
            365: "ONE YEAR! You've achieved what most only dream of."
        }
        return messages.get(streak_count, f"Amazing! {streak_count} days of learning!")

    def _load_nudge_templates(self) -> Dict[NudgeType, List[str]]:
        """Load nudge message templates."""
        return {
            NudgeType.ENCOURAGEMENT: [
                "You're making great progress! Keep it up.",
                "Every session brings you closer to mastery.",
                "Your dedication is paying off!"
            ],
            NudgeType.PERSONALIZED_TIP: [
                "Based on your learning style, try visual examples today.",
                "You learn best with hands-on practice. Try the exercises!",
                "Take breaks every 25 minutes - your brain will thank you."
            ]
        }


# Global service instance
proactive_engagement_service = ProactiveEngagementService()
