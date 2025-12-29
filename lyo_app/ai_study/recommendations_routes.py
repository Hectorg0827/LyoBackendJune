"""
AI Recommendations API Routes - Layer 1 & 2 Personalized Learning
Provides endpoints for personalized content, next-best-action, and learner insights.
"""

import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user
from lyo_app.models.enhanced import User
from lyo_app.personalization.service import personalization_engine
from lyo_app.personalization.schemas import (
    PersonalizationStateUpdate, NextActionRequest, NextActionResponse,
    MasteryProfile, KnowledgeTraceRequest
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai/recommendations", tags=["AI Recommendations"])

@router.get("/", response_model=Dict[str, Any])
async def get_current_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get immediate personalized recommendations for the current user.
    """
    try:
        # Create a basic update to trigger the engine to fetch current state
        update = PersonalizationStateUpdate(
            learner_id=str(current_user.id)
        )
        result = await personalization_engine.update_state(db, update)
        return result
    except Exception as e:
        logger.error(f"Error fetching recommendations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch personalized recommendations"
        )

@router.post("/state", response_model=Dict[str, Any])
async def update_learner_state(
    update: PersonalizationStateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update the learner's affective and session state and get updated recommendations.
    """
    if str(current_user.id) != update.learner_id:
        raise HTTPException(status_code=403, detail="Cannot update state for another user")
        
    try:
        return await personalization_engine.update_state(db, update)
    except Exception as e:
        logger.error(f"Error updating state: {e}")
        raise HTTPException(status_code=500, detail="Failed to update learner state")

@router.post("/next-action", response_model=NextActionResponse)
async def get_next_best_action(
    request: NextActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Calculate the next best action (Practice, Review, Break, etc.) for the user.
    """
    if str(current_user.id) != request.learner_id:
        raise HTTPException(status_code=403, detail="Cannot request action for another user")
        
    try:
        return await personalization_engine.get_next_action(db, request)
    except Exception as e:
        logger.error(f"Error calculating next action: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate next action")

@router.get("/profile", response_model=MasteryProfile)
async def get_mastery_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the comprehensive skill mastery profile for the current user.
    """
    try:
        return await personalization_engine.get_mastery_profile(db, str(current_user.id))
    except Exception as e:
        logger.error(f"Error fetching mastery profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch mastery profile")

@router.post("/trace", response_model=Dict[str, Any])
async def trace_knowledge_event(
    request: KnowledgeTraceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a learning event (e.g. quiz answer) to update knowledge tracing registry.
    """
    if str(current_user.id) != request.learner_id:
        raise HTTPException(status_code=403, detail="Cannot trace event for another user")
        
    try:
        return await personalization_engine.trace_knowledge(db, request)
    except Exception as e:
        logger.error(f"Error tracing knowledge: {e}")
        raise HTTPException(status_code=500, detail="Failed to trace knowledge event")
