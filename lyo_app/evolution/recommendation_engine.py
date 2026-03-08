"""
Recommendation Engine 2.0 (Next Best Upgrade)
Moves beyond generic 'Next Practice Question' to surface behavioral 
and capability growth upgrades based on the user's trajectory.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.evolution.goals_models import UserGoal, GoalStatus, GoalProgressSnapshot
from lyo_app.evolution.goals_service import get_user_goals
from lyo_app.skills.models import Skill, SkillDomain
from lyo_app.skills.service import get_skill
from lyo_app.personalization.models import LearnerMastery
from lyo_app.events.models import LearningEvent

logger = logging.getLogger(__name__)

class UpgradeSuggestion:
    """A proactive suggestion for the user to improve a specific capability."""
    def __init__(self, skill_id: int, skill_name: str, domain: SkillDomain, reason: str, recommended_action: str, priority_score: float):
        self.skill_id = skill_id
        self.skill_name = skill_name
        self.domain = domain
        self.reason = reason
        self.recommended_action = recommended_action
        self.priority_score = priority_score # 0.0 to 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "domain": self.domain.value,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "priority_score": self.priority_score,
            "type": "upgrade_suggestion"
        }

async def get_next_upgrade(db: AsyncSession, user_id: int) -> Optional[UpgradeSuggestion]:
    """
    Core logic to determine the member's Next Best Upgrade.
    Aggregates signals from:
    1. Active Goals
    2. DKT Mastery (Weakest Links - mocked for now)
    3. Momentum Patterns
    """
    try:
        # Step 1: Fetch active goals
        active_goals = await get_user_goals(db, user_id, status=GoalStatus.ACTIVE)
        
        if not active_goals:
            logger.info(f"No active goals found for user {user_id}. Surfacing generic exploration upgrade.")
            # Fallback if no goals are set
            return UpgradeSuggestion(
                skill_id=0,
                skill_name="General Exploration",
                domain=SkillDomain.CAPABILITY,
                reason="You haven't set any active goals yet.",
                recommended_action="explore_goals",
                priority_score=0.5
            )

        # We'll prioritize the goal with the lowest recent momentum, or simply the first one for now.
        # In a fully fleshed out DKT system, this would query the mastery tensor.
        
        # Analyze the first active goal as a proxy
        primary_goal = active_goals[0]
        
        if not primary_goal.skill_mappings:
            return UpgradeSuggestion(
                skill_id=0,
                skill_name="Goal Alignment",
                domain=SkillDomain.LIFE,
                reason=f"Your goal '{primary_goal.target}' isn't mapped to any specific skills.",
                recommended_action="map_skills_to_goal",
                priority_score=0.8
            )

        # Find the "weakest link" skill in this goal's mapping
        # Cross-reference skill mappings with DKT mastery scores.
        weakest_mastery = 1.0
        target_mapping = primary_goal.skill_mappings[0]

        for mapping in primary_goal.skill_mappings:
            mastery_row = await db.execute(
                select(LearnerMastery).where(
                    and_(
                        LearnerMastery.user_id == user_id,
                        LearnerMastery.skill_id == str(mapping.skill_id),
                    )
                )
            )
            mastery = mastery_row.scalar_one_or_none()
            level = mastery.mastery_level if mastery else 0.0
            if level < weakest_mastery:
                weakest_mastery = level
                target_mapping = mapping

        skill = await get_skill(db, target_mapping.skill_id)
        
        if not skill:
            return None

        # Determine neglect: check if the learner hasn't interacted with this skill in 3+ days
        three_days_ago = datetime.utcnow() - timedelta(days=3)
        recent_event_q = await db.execute(
            select(LearningEvent.id).where(
                and_(
                    LearningEvent.user_id == user_id,
                    LearningEvent.timestamp >= three_days_ago,
                )
            ).limit(1)
        )
        is_neglected = recent_event_q.scalar_one_or_none() is None

        # Also check mastery last_seen
        mastery_check_q = await db.execute(
            select(LearnerMastery.last_seen).where(
                and_(
                    LearnerMastery.user_id == user_id,
                    LearnerMastery.skill_id == str(target_mapping.skill_id),
                )
            )
        )
        mastery_last_seen = mastery_check_q.scalar_one_or_none()
        if mastery_last_seen and mastery_last_seen < three_days_ago:
            is_neglected = True
        
        reason = f"You haven't practiced '{skill.name}' recently, which is blocking your goal: {primary_goal.target}." if is_neglected else f"Keep your momentum going on '{skill.name}' to reach: {primary_goal.target}."
        
        action = "quick_practice" if skill.domain == SkillDomain.ACADEMIC else "reflection_exercise"

        return UpgradeSuggestion(
            skill_id=skill.id,
            skill_name=skill.name,
            domain=skill.domain,
            reason=reason,
            recommended_action=action,
            priority_score=0.9 if is_neglected else 0.7
        )

    except Exception as e:
        logger.error(f"Error calculating next upgrade for user {user_id}: {e}")
        return None
