"""
Personalization API routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import verify_access_token
from lyo_app.auth.models import User

from .schemas import (
    PersonalizationStateUpdate, KnowledgeTraceRequest,
    NextActionRequest, NextActionResponse, MasteryProfile
)
from .service import personalization_engine

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/personalization", tags=["Personalization"])

@router.patch("/state")
async def update_personalization_state(
    update: PersonalizationStateUpdate,
    current_user: User = Depends(verify_access_token),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update learner state with affect and session signals.
    Privacy-preserving: only aggregated signals, never raw data.
    """
    try:
        # Verify user can update this learner
        if update.learner_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="Cannot update another user's state")
        
        result = await personalization_engine.update_state(db, update)
        
        logger.info(f"Updated personalization state for user {current_user.id}")
        return result
        
    except Exception as e:
        logger.error(f"Error updating personalization state: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trace")
async def trace_knowledge(
    request: KnowledgeTraceRequest,
    current_user: User = Depends(verify_access_token),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update knowledge tracking from assessment result.
    Uses Deep Knowledge Tracing to update mastery estimates.
    """
    try:
        if request.learner_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="Cannot trace another user's knowledge")
        
        result = await personalization_engine.trace_knowledge(db, request)
        
        logger.info(f"Traced knowledge for user {current_user.id}, skill {request.skill_id}")
        return result
        
    except Exception as e:
        logger.error(f"Error tracing knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/next", response_model=NextActionResponse)
async def get_next_action(
    lesson_id: str = None,
    current_skill: str = None,
    current_user: User = Depends(verify_access_token),
    db: AsyncSession = Depends(get_db)
) -> NextActionResponse:
    """
    Get next best learning action based on current state.
    Considers mastery, affect, fatigue, and spaced repetition.
    """
    try:
        request = NextActionRequest(
            learner_id=str(current_user.id),
            lesson_id=lesson_id,
            current_skill=current_skill
        )
        
        response = await personalization_engine.get_next_action(db, request)
        
        logger.info(f"Next action for user {current_user.id}: {response.action}")
        return response
        
    except Exception as e:
        logger.error(f"Error getting next action: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mastery", response_model=MasteryProfile)
async def get_mastery_profile(
    current_user: User = Depends(verify_access_token),
    db: AsyncSession = Depends(get_db)
) -> MasteryProfile:
    """
    Get complete mastery profile with strengths and weaknesses.
    """
    try:
        profile = await personalization_engine.get_mastery_profile(
            db, str(current_user.id)
        )
        
        return profile
        
    except Exception as e:
        logger.error(f"Error getting mastery profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))
