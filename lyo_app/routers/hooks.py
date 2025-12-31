"""
Behavioral Hooks API Routes

Endpoints for the Hook Model engagement system.
These track trigger→action→reward→investment loops.
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
from lyo_app.services.behavioral_hooks import (
    behavioral_hooks_service,
    TriggerType,
    ActionType,
    RewardType,
    InvestmentType
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hooks", tags=["Behavioral Hooks"])


# ==================== Schemas ====================

class RewardResponse(BaseModel):
    """A reward earned by the user."""
    type: str
    title: str
    message: str
    value: str
    rarity: str
    celebration_level: int


class HookLoopResponse(BaseModel):
    """A complete hook loop."""
    trigger: str
    action: str
    rewards: List[RewardResponse]
    total_xp: int
    investments: List[str]
    completed_at: datetime


class TrackActionRequest(BaseModel):
    """Request to track a user action."""
    action_type: str = Field(..., description="Type of action: start_session, complete_lesson, etc.")
    context: dict = Field(default_factory=dict, description="Additional context about the action")
    trigger_type: Optional[str] = Field(None, description="What triggered this action")


class InvestmentRequest(BaseModel):
    """Request to track a user investment."""
    investment_type: str = Field(..., description="Type of investment: time, data, content, etc.")
    value: str = Field(..., description="Value of the investment")


class HookAnalyticsResponse(BaseModel):
    """Analytics on hook effectiveness."""
    period_days: int
    total_sessions: int
    total_xp: int
    avg_sessions_per_day: float
    engagement_score: float
    hook_health: str


# ==================== Endpoints ====================

@router.post("/action", response_model=HookLoopResponse)
async def track_action_and_reward(
    request: TrackActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Track a user action and generate rewards.

    This is the core of the hook loop:
    1. Records the action the user took
    2. Generates a variable reward (with rarity roll)
    3. Returns the reward for celebration UI

    Variable rewards are key to habit formation - the unpredictability
    triggers dopamine release and reinforces the behavior.
    """
    try:
        action_type = ActionType(request.action_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action type. Valid types: {[a.value for a in ActionType]}"
        )

    try:
        # Track the action
        trigger = None
        if request.trigger_type:
            trigger_type = TriggerType(request.trigger_type)
            trigger = await behavioral_hooks_service.generate_trigger(
                user_id=current_user.id,
                trigger_type=trigger_type,
                context=request.context,
                db=db
            )

        loop = await behavioral_hooks_service.track_action(
            user_id=current_user.id,
            action_type=action_type,
            trigger=trigger,
            db=db
        )

        # Generate variable reward
        reward = await behavioral_hooks_service.generate_variable_reward(
            user_id=current_user.id,
            action_type=action_type,
            context=request.context,
            db=db
        )

        # Complete the loop
        completed_loop = await behavioral_hooks_service.complete_hook_loop(
            loop=loop,
            rewards=[reward],
            investments=[],
            db=db
        )

        return HookLoopResponse(
            trigger=completed_loop.trigger.value,
            action=completed_loop.action.value,
            rewards=[RewardResponse(
                type=reward.type.value,
                title=reward.title,
                message=reward.message,
                value=str(reward.value),
                rarity=reward.rarity,
                celebration_level=reward.celebration_level
            )],
            total_xp=completed_loop.total_xp_earned,
            investments=[],
            completed_at=completed_loop.completed_at or datetime.utcnow()
        )

    except Exception as e:
        logger.exception(f"Failed to track action: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process action"
        )


@router.post("/investment")
async def track_investment(
    request: InvestmentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Track a user investment.

    Investments are things users put INTO the product:
    - Time spent learning
    - Data/preferences shared
    - Content created (notes, answers)
    - Reputation built
    - Social connections made

    These increase switching costs and future engagement.
    """
    try:
        investment_type = InvestmentType(request.investment_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid investment type. Valid types: {[i.value for i in InvestmentType]}"
        )

    try:
        result = await behavioral_hooks_service.track_investment(
            user_id=current_user.id,
            investment_type=investment_type,
            value=request.value,
            db=db
        )

        return result

    except Exception as e:
        logger.exception(f"Failed to track investment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to track investment"
        )


@router.get("/analytics", response_model=HookAnalyticsResponse)
async def get_hook_analytics(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get analytics on your engagement patterns.

    Shows how effective the hook loops are at driving
    your learning habits.
    """
    try:
        analytics = await behavioral_hooks_service.get_hook_analytics(
            user_id=current_user.id,
            db=db,
            days=days
        )

        return HookAnalyticsResponse(**analytics)

    except Exception as e:
        logger.exception(f"Failed to get analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics"
        )


@router.get("/reward-preview")
async def preview_possible_rewards(
    action: str = "complete_lesson",
    current_user: User = Depends(get_current_user)
):
    """
    Preview possible rewards for an action.

    Shows the range of rewards you might earn, building
    anticipation and curiosity (part of the hook!).
    """
    try:
        action_type = ActionType(action)
    except ValueError:
        action_type = ActionType.COMPLETE_LESSON

    rarities = ["common", "uncommon", "rare", "epic", "legendary"]
    probability_display = {
        "common": "60%",
        "uncommon": "25%",
        "rare": "10%",
        "epic": "4%",
        "legendary": "1%"
    }

    return {
        "action": action_type.value,
        "possible_rewards": [
            {
                "rarity": r,
                "probability": probability_display[r],
                "xp_multiplier": behavioral_hooks_service.RARITY_MULTIPLIERS[r],
                "example": f"{r.title()} XP Bonus"
            }
            for r in rarities
        ],
        "note": "Rarity rolls are boosted by streak length!"
    }


@router.get("/trigger-types")
async def list_trigger_types():
    """
    List all trigger types in the system.

    Useful for understanding what can initiate engagement.
    """
    return {
        "external_triggers": [
            {"type": TriggerType.PUSH_NOTIFICATION.value, "description": "Push notification"},
            {"type": TriggerType.EMAIL.value, "description": "Email reminder"},
            {"type": TriggerType.IN_APP_PROMPT.value, "description": "In-app prompt"},
            {"type": TriggerType.STREAK_WARNING.value, "description": "Streak about to break"},
            {"type": TriggerType.SOCIAL_PROOF.value, "description": "Friends are learning"},
            {"type": TriggerType.CALENDAR_EVENT.value, "description": "Upcoming calendar event"}
        ],
        "internal_triggers": [
            {"type": TriggerType.BOREDOM.value, "description": "User feels bored"},
            {"type": TriggerType.CURIOSITY.value, "description": "User is curious"},
            {"type": TriggerType.ANXIETY.value, "description": "Pre-exam anxiety"},
            {"type": TriggerType.FOMO.value, "description": "Fear of missing out"},
            {"type": TriggerType.HABIT.value, "description": "Automatic habit"}
        ],
        "note": "Internal triggers are more powerful but take time to develop"
    }


@router.get("/investment-summary")
async def get_investment_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a summary of user's investments in the platform.

    These are the things that make leaving hard and staying valuable.
    """
    from sqlalchemy import select, func
    from lyo_app.ai_agents.models import MentorInteraction
    from lyo_app.gamification.models import UserXP, Streak

    try:
        # Calculate time investment
        interaction_count = await db.execute(
            select(func.count(MentorInteraction.id))
            .where(MentorInteraction.user_id == current_user.id)
        )
        total_interactions = interaction_count.scalar() or 0
        estimated_minutes = total_interactions * 3  # ~3 min per interaction

        # Get XP (reputation investment)
        xp_result = await db.execute(
            select(func.sum(UserXP.xp_amount))
            .where(UserXP.user_id == current_user.id)
        )
        total_xp = xp_result.scalar() or 0

        # Get streak (consistency investment)
        streak_result = await db.execute(
            select(Streak)
            .where(Streak.user_id == current_user.id)
            .order_by(Streak.current_count.desc())
            .limit(1)
        )
        streak = streak_result.scalar_one_or_none()
        longest_streak = streak.longest_count if streak else 0

        # Memory (data investment)
        has_memory = bool(current_user.user_context_summary)

        return {
            "investments": {
                "time": {
                    "value": estimated_minutes,
                    "unit": "minutes",
                    "description": f"You've invested ~{estimated_minutes} minutes learning"
                },
                "reputation": {
                    "value": int(total_xp),
                    "unit": "XP",
                    "description": f"You've earned {int(total_xp)} XP"
                },
                "consistency": {
                    "value": longest_streak,
                    "unit": "days",
                    "description": f"Longest streak: {longest_streak} days"
                },
                "personalization": {
                    "value": "active" if has_memory else "none",
                    "description": "AI knows your learning style" if has_memory else "Start learning to build your profile"
                }
            },
            "total_investment_score": _calculate_investment_score(
                estimated_minutes, total_xp, longest_streak, has_memory
            ),
            "switching_cost": "high" if total_xp > 1000 else "medium" if total_xp > 100 else "low"
        }

    except Exception as e:
        logger.exception(f"Failed to get investment summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve investment summary"
        )


def _calculate_investment_score(minutes: int, xp: int, streak: int, has_memory: bool) -> int:
    """Calculate overall investment score."""
    score = 0
    score += min(minutes // 10, 100)  # Up to 100 for time
    score += min(int(xp) // 100, 100)  # Up to 100 for XP
    score += min(streak * 5, 50)  # Up to 50 for streak
    score += 50 if has_memory else 0  # 50 for personalization
    return min(score, 300)


# Attach helper to module
router._calculate_investment_score = _calculate_investment_score
