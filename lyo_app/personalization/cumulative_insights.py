"""
Cumulative Insights Engine — Aggregates cross-domain patterns over time.
Part of the Value Compounding layer (Pillar 5).

Synthesizes data across Goals, DKT mastery, Events, Reflections, and Soft Skills
to produce high-level insights that are hard to see from any single system.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.personalization.models import LearnerMastery
from lyo_app.events.models import LearningEvent, EventType
from lyo_app.evolution.goals_models import UserGoal, GoalStatus, GoalProgressSnapshot

logger = logging.getLogger(__name__)


class CumulativeInsight:
    """A single high-level insight derived from cross-domain analysis."""

    def __init__(
        self,
        category: str,
        title: str,
        description: str,
        confidence: float,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.category = category
        self.title = title
        self.description = description
        self.confidence = confidence
        self.data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "confidence": self.confidence,
            "data": self.data,
        }


async def generate_cumulative_insights(
    db: AsyncSession, user_id: int
) -> List[CumulativeInsight]:
    """
    Analyze all available data for a user and produce a list of cross-domain insights.
    Meant to be called periodically (e.g. weekly) or on-demand.
    """
    insights: List[CumulativeInsight] = []

    # ── 1. Mastery velocity ─────────────────────────────────
    mastery_rows = await db.execute(
        select(LearnerMastery).where(LearnerMastery.user_id == user_id)
    )
    mastery_records = list(mastery_rows.scalars().all())

    if mastery_records:
        avg_mastery = sum(m.mastery_level for m in mastery_records) / len(mastery_records)
        high_mastery = [m for m in mastery_records if m.mastery_level >= 0.8]
        low_mastery = [m for m in mastery_records if m.mastery_level < 0.3]

        insights.append(CumulativeInsight(
            category="mastery",
            title="Mastery Overview",
            description=(
                f"You are tracking {len(mastery_records)} skills with an average mastery of "
                f"{avg_mastery:.0%}. {len(high_mastery)} skills are near-expert level, "
                f"and {len(low_mastery)} need more attention."
            ),
            confidence=0.9,
            data={
                "total_skills": len(mastery_records),
                "avg_mastery": round(avg_mastery, 3),
                "high_count": len(high_mastery),
                "low_count": len(low_mastery),
            },
        ))

    # ── 2. Learning consistency ─────────────────────────────
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    events_q = await db.execute(
        select(func.count(LearningEvent.id)).where(
            and_(
                LearningEvent.user_id == user_id,
                LearningEvent.timestamp >= thirty_days_ago,
            )
        )
    )
    event_count_30d = events_q.scalar() or 0

    if event_count_30d > 0:
        daily_avg = event_count_30d / 30.0
        consistency = "strong" if daily_avg >= 1.0 else ("moderate" if daily_avg >= 0.3 else "low")
        insights.append(CumulativeInsight(
            category="consistency",
            title="Learning Consistency",
            description=(
                f"Over the past 30 days you logged {event_count_30d} events "
                f"(~{daily_avg:.1f}/day). Your consistency is {consistency}."
            ),
            confidence=0.85,
            data={"events_30d": event_count_30d, "daily_avg": round(daily_avg, 2), "rating": consistency},
        ))

    # ── 3. Goal alignment ──────────────────────────────────
    goals_q = await db.execute(
        select(UserGoal).where(
            and_(UserGoal.user_id == user_id, UserGoal.status == GoalStatus.ACTIVE)
        )
    )
    active_goals = list(goals_q.scalars().all())

    if active_goals:
        goals_with_skills = [g for g in active_goals if g.skill_mappings]
        unmapped = len(active_goals) - len(goals_with_skills)
        if unmapped > 0:
            insights.append(CumulativeInsight(
                category="goal_alignment",
                title="Unmapped Goals",
                description=(
                    f"{unmapped} of your {len(active_goals)} active goals have no skill mappings. "
                    f"Map skills to them so Lyo can track your trajectory automatically."
                ),
                confidence=0.95,
                data={"unmapped": unmapped, "total_active": len(active_goals)},
            ))

    # ── 4. Reflection depth ────────────────────────────────
    reflection_q = await db.execute(
        select(func.count(LearningEvent.id)).where(
            and_(
                LearningEvent.user_id == user_id,
                LearningEvent.event_type == EventType.REFLECTION,
            )
        )
    )
    reflection_count = reflection_q.scalar() or 0

    if reflection_count == 0:
        insights.append(CumulativeInsight(
            category="reflection",
            title="Start Reflecting",
            description=(
                "You haven't submitted any reflections yet. "
                "Reflections help Lyo understand your confidence and adjust your path."
            ),
            confidence=0.9,
        ))
    elif reflection_count >= 10:
        insights.append(CumulativeInsight(
            category="reflection",
            title="Reflection Habit Formed",
            description=(
                f"You've submitted {reflection_count} reflections — great self-awareness! "
                f"This data is actively improving your AI tutor's accuracy."
            ),
            confidence=0.85,
            data={"count": reflection_count},
        ))

    return insights
