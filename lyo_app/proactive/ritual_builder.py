"""
Ritual Builder — Constructs personalized learning rituals for members.
Part of the Proactive Companion layer (Pillar 2).

A "ritual" is a recurring micro-routine that Lyo proposes based on the
learner's schedule, goals, and personality. Examples:
  - Morning 5-min review of yesterday's weak skills
  - Pre-study confidence check-in
  - End-of-day reflection prompt
  - Weekly goal review
"""

import logging
from datetime import time as dt_time
from typing import List, Dict, Any, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.evolution.goals_models import UserGoal, GoalStatus
from lyo_app.personalization.models import LearnerMastery

logger = logging.getLogger(__name__)


class Ritual:
    """A proposed micro-routine for the learner."""

    def __init__(
        self,
        ritual_type: str,
        title: str,
        description: str,
        suggested_time: Optional[str] = None,
        duration_minutes: int = 5,
        frequency: str = "daily",
        priority: float = 0.5,
        actions: Optional[List[Dict[str, Any]]] = None,
    ):
        self.ritual_type = ritual_type
        self.title = title
        self.description = description
        self.suggested_time = suggested_time
        self.duration_minutes = duration_minutes
        self.frequency = frequency
        self.priority = priority
        self.actions = actions or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ritual_type": self.ritual_type,
            "title": self.title,
            "description": self.description,
            "suggested_time": self.suggested_time,
            "duration_minutes": self.duration_minutes,
            "frequency": self.frequency,
            "priority": self.priority,
            "actions": self.actions,
        }


async def build_rituals(
    db: AsyncSession,
    user_id: int,
    peak_hours: Optional[List[int]] = None,
) -> List[Ritual]:
    """
    Generate a personalized set of micro-rituals for the learner.
    """
    rituals: List[Ritual] = []

    # Fetch user context
    goals_q = await db.execute(
        select(UserGoal).where(
            and_(UserGoal.user_id == user_id, UserGoal.status == GoalStatus.ACTIVE)
        )
    )
    active_goals = list(goals_q.scalars().all())

    mastery_q = await db.execute(
        select(LearnerMastery).where(LearnerMastery.user_id == user_id)
    )
    mastery_records = list(mastery_q.scalars().all())
    weak_skills = [m for m in mastery_records if m.mastery_level < 0.4]

    # ── 1. Morning Quick Review ─────────────────────────────
    if weak_skills:
        skill_names = ", ".join(m.skill_id for m in weak_skills[:3])
        morning = peak_hours[0] if peak_hours else 8
        rituals.append(Ritual(
            ritual_type="morning_review",
            title="Morning Quick Review",
            description=f"Start your day with a 5-min review of: {skill_names}",
            suggested_time=f"{morning:02d}:00",
            duration_minutes=5,
            frequency="daily",
            priority=0.8,
            actions=[
                {"type": "flashcard_review", "skill_ids": [m.skill_id for m in weak_skills[:3]]},
            ],
        ))

    # ── 2. Pre-Study Check-in ───────────────────────────────
    rituals.append(Ritual(
        ritual_type="pre_study_checkin",
        title="How are you feeling?",
        description="Quick confidence & energy check before studying. Helps Lyo adapt the session.",
        suggested_time=None,  # Triggered contextually
        duration_minutes=1,
        frequency="per_session",
        priority=0.6,
        actions=[{"type": "confidence_survey"}],
    ))

    # ── 3. End-of-Day Reflection ────────────────────────────
    evening = peak_hours[-1] + 2 if peak_hours else 21
    rituals.append(Ritual(
        ritual_type="evening_reflection",
        title="Evening Reflection",
        description="Take 3 minutes to reflect on what clicked today and what was hard.",
        suggested_time=f"{min(evening, 23):02d}:00",
        duration_minutes=3,
        frequency="daily",
        priority=0.7,
        actions=[{"type": "reflection_prompt"}],
    ))

    # ── 4. Weekly Goal Review ───────────────────────────────
    if active_goals:
        goal_titles = ", ".join(g.target for g in active_goals[:3])
        rituals.append(Ritual(
            ritual_type="weekly_goal_review",
            title="Weekly Goal Check",
            description=f"Review progress on: {goal_titles}",
            suggested_time="10:00",
            duration_minutes=10,
            frequency="weekly",
            priority=0.9,
            actions=[
                {"type": "goal_review", "goal_ids": [g.id for g in active_goals[:3]]},
            ],
        ))

    # ── 5. Spaced Repetition Ritual ─────────────────────────
    from lyo_app.personalization.models import SpacedRepetitionSchedule
    from datetime import datetime
    now = datetime.utcnow()
    overdue_q = await db.execute(
        select(SpacedRepetitionSchedule).where(
            and_(
                SpacedRepetitionSchedule.user_id == user_id,
                SpacedRepetitionSchedule.next_review <= now,
            )
        ).limit(5)
    )
    overdue = list(overdue_q.scalars().all())
    if overdue:
        rituals.append(Ritual(
            ritual_type="spaced_rep",
            title="Spaced Repetition Session",
            description=f"{len(overdue)} skill(s) are due for review. A quick session prevents forgetting.",
            duration_minutes=5,
            frequency="daily",
            priority=0.85,
            actions=[{"type": "spaced_rep_review", "count": len(overdue)}],
        ))

    # Sort by priority
    rituals.sort(key=lambda r: r.priority, reverse=True)
    return rituals
