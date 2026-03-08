"""
API routes for the Persistent Relationship System (Pillar 4).
Milestones, Journey Summary, Personality, Weekly Review.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User

from .schemas import (
    MilestonesResponse,
    MilestoneRead,
    JourneySummaryResponse,
    PersonalityProfileRead,
    WeeklyReviewResponse,
)
from .milestone_engine import get_milestones, count_milestones
from .personality_adapter import get_personality
from .relationship_tracker import get_journey_summary, get_weekly_review

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/relationship", tags=["Relationship System"])


@router.get("/milestones", response_model=MilestonesResponse)
async def list_milestones(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all milestones for the authenticated user."""
    milestones = await get_milestones(db, user.id)
    total = await count_milestones(db, user.id)
    return MilestonesResponse(
        milestones=[MilestoneRead.model_validate(m) for m in milestones],
        total=total,
    )


@router.get("/journey", response_model=JourneySummaryResponse)
async def journey_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a holistic summary of the learner's journey with Lyo."""
    return await get_journey_summary(db, user.id)


@router.get("/personality", response_model=PersonalityProfileRead)
async def personality(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the AI's adapted personality profile for the authenticated user."""
    profile = await get_personality(db, user.id)
    return PersonalityProfileRead.model_validate(profile)


@router.get("/weekly-review", response_model=WeeklyReviewResponse)
async def weekly_review(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the weekly learning review for the authenticated user."""
    return await get_weekly_review(db, user.id)
