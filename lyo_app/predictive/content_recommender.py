"""
Content Recommender — Suggests optimal learning content based on mastery + predictive signals.
Part of the Predictive Intelligence layer (Pillar 3).

Unlike the Recommendation Engine (which focuses on *upgrades/goals*), this module
recommends specific *content pieces* (lessons, quizzes, articles) using:
  - DKT mastery gaps
  - Spaced repetition schedules
  - Struggle predictions
  - Optimal timing
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.personalization.models import LearnerMastery, SpacedRepetitionSchedule
from lyo_app.events.models import LearningEvent

logger = logging.getLogger(__name__)


class ContentRecommendation:
    """A single recommended content piece."""

    def __init__(
        self,
        content_type: str,
        skill_id: str,
        skill_name: str,
        reason: str,
        urgency: float,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.content_type = content_type  # "review", "new_lesson", "practice", "quiz"
        self.skill_id = skill_id
        self.skill_name = skill_name
        self.reason = reason
        self.urgency = urgency  # 0-1
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_type": self.content_type,
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "reason": self.reason,
            "urgency": self.urgency,
            "metadata": self.metadata,
        }


async def recommend_content(
    db: AsyncSession, user_id: int, limit: int = 5
) -> List[ContentRecommendation]:
    """
    Generate a prioritized list of content recommendations for a user.
    """
    recommendations: List[ContentRecommendation] = []

    # ── 1. Spaced Repetition: overdue reviews ──────────────
    try:
        now = datetime.utcnow()
        overdue_q = await db.execute(
            select(SpacedRepetitionSchedule).where(
                and_(
                    SpacedRepetitionSchedule.user_id == user_id,
                    SpacedRepetitionSchedule.next_review <= now,
                )
            ).order_by(SpacedRepetitionSchedule.next_review.asc()).limit(limit)
        )
        for sched in overdue_q.scalars().all():
            days_overdue = (now - sched.next_review).days
            urgency = min(1.0, 0.5 + days_overdue * 0.1)
            recommendations.append(ContentRecommendation(
                content_type="review",
                skill_id=str(sched.skill_id),
                skill_name=sched.skill_id,  # Will be enriched downstream
                reason=f"Overdue for review by {days_overdue} day(s). Retention is at risk.",
                urgency=urgency,
                metadata={"days_overdue": days_overdue, "interval": sched.interval_days},
            ))
    except Exception as e:
        logger.warning(f"Spaced rep lookup failed: {e}")

    # ── 2. Mastery gaps: skills with low mastery + many attempts ──
    weak_q = await db.execute(
        select(LearnerMastery).where(
            and_(
                LearnerMastery.user_id == user_id,
                LearnerMastery.mastery_level < 0.4,
                LearnerMastery.attempts >= 2,
            )
        ).order_by(LearnerMastery.mastery_level.asc()).limit(limit)
    )
    for m in weak_q.scalars().all():
        recommendations.append(ContentRecommendation(
            content_type="practice",
            skill_id=m.skill_id,
            skill_name=m.skill_id,
            reason=f"Low mastery ({m.mastery_level:.0%}) despite {m.attempts} attempts. Focused practice recommended.",
            urgency=0.8,
            metadata={"mastery": m.mastery_level, "attempts": m.attempts},
        ))

    # ── 3. Neglected skills: haven't been seen in 7+ days ──
    seven_days_ago = now - timedelta(days=7)
    neglected_q = await db.execute(
        select(LearnerMastery).where(
            and_(
                LearnerMastery.user_id == user_id,
                LearnerMastery.last_seen < seven_days_ago,
                LearnerMastery.mastery_level < 0.8,
            )
        ).order_by(LearnerMastery.last_seen.asc()).limit(limit)
    )
    for m in neglected_q.scalars().all():
        days_unseen = (now - m.last_seen).days
        recommendations.append(ContentRecommendation(
            content_type="review",
            skill_id=m.skill_id,
            skill_name=m.skill_id,
            reason=f"Not practiced in {days_unseen} days. Quick review to prevent decay.",
            urgency=0.6,
            metadata={"days_unseen": days_unseen, "mastery": m.mastery_level},
        ))

    # Sort by urgency and dedup by skill
    seen_skills = set()
    unique: List[ContentRecommendation] = []
    for r in sorted(recommendations, key=lambda x: x.urgency, reverse=True):
        if r.skill_id not in seen_skills:
            unique.append(r)
            seen_skills.add(r.skill_id)

    return unique[:limit]
