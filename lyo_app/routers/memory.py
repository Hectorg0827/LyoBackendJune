"""
Memory API Routes - User Memory Management

These endpoints allow users to view and manage what the AI "remembers" about them.
This transparency is crucial for:
- Building trust (users can see what data influences AI responses)
- Enabling corrections (users can fix incorrect memories)
- GDPR compliance (right to access and modify personal data)
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from lyo_app.core.database import get_db as get_async_db
from lyo_app.auth.models import User
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.services.memory_synthesis import memory_synthesis_service
from lyo_app.tasks.memory_synthesis import (
    synthesize_full_memory_task,
    synthesize_session_memory_task
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["Memory"])


# ==================== Schemas ====================

class MemoryResponse(BaseModel):
    """Response containing user's AI memory profile."""
    user_id: int
    memory: str
    last_updated: Optional[datetime] = None
    word_count: int

    class Config:
        from_attributes = True


class MemoryUpdateRequest(BaseModel):
    """Request to update user's memory profile."""
    memory: str = Field(..., min_length=10, max_length=2000,
                        description="The updated memory content (10-2000 characters)")


class MemoryRefreshRequest(BaseModel):
    """Request to trigger memory refresh."""
    lookback_days: int = Field(default=30, ge=7, le=90,
                               description="Number of days to look back for synthesis")


class MemoryInsightRequest(BaseModel):
    """Request to add a specific insight to memory."""
    category: str = Field(..., description="Category: learning_style, emotional_pattern, topic_interest, struggle_point, success_pattern")
    content: str = Field(..., min_length=5, max_length=500)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class MemoryStatsResponse(BaseModel):
    """Statistics about user's memory and AI interactions."""
    total_interactions: int
    sessions_count: int
    memory_size_chars: int
    last_interaction: Optional[datetime]
    last_memory_update: Optional[datetime]
    memory_health_score: float  # 0-1, how up-to-date is the memory


# ==================== Endpoints ====================

@router.get("/me", response_model=MemoryResponse)
async def get_my_memory(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get your AI memory profile.

    This shows you what the AI "remembers" about you - your learning style,
    preferences, strengths, struggles, and recent progress. This memory is
    used to personalize every AI interaction.
    """
    memory = current_user.user_context_summary or ""

    return MemoryResponse(
        user_id=current_user.id,
        memory=memory if memory else "No memory profile yet. Start chatting with Lyo to build your profile!",
        last_updated=current_user.updated_at,
        word_count=len(memory.split()) if memory else 0
    )


@router.put("/me", response_model=MemoryResponse)
async def update_my_memory(
    request: MemoryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update your AI memory profile.

    Use this to correct any inaccuracies in what the AI remembers about you.
    For example:
    - "I actually prefer detailed explanations, not quick summaries"
    - "I'm not struggling with fractions anymore"
    - "My name is spelled differently"

    The AI will use this updated memory in all future interactions.
    """
    try:
        current_user.user_context_summary = request.memory
        current_user.updated_at = datetime.utcnow()
        await db.commit()

        logger.info(f"User {current_user.id} manually updated their memory profile")

        return MemoryResponse(
            user_id=current_user.id,
            memory=request.memory,
            last_updated=current_user.updated_at,
            word_count=len(request.memory.split())
        )

    except Exception as e:
        logger.exception(f"Failed to update memory for user {current_user.id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update memory profile"
        )


@router.delete("/me")
async def clear_my_memory(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Clear your AI memory profile.

    This resets what the AI knows about you. The AI will treat you as a new
    user until a new memory profile is built from future interactions.

    Note: This doesn't delete your interaction history, only the synthesized memory.
    """
    try:
        current_user.user_context_summary = None
        current_user.updated_at = datetime.utcnow()
        await db.commit()

        logger.info(f"User {current_user.id} cleared their memory profile")

        return {"message": "Memory profile cleared successfully", "user_id": current_user.id}

    except Exception as e:
        logger.exception(f"Failed to clear memory for user {current_user.id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear memory profile"
        )


@router.post("/me/refresh")
async def refresh_my_memory(
    request: MemoryRefreshRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Trigger a full refresh of your AI memory.

    This re-synthesizes your memory profile from your recent interaction
    history. Useful if:
    - Your memory feels outdated
    - You've had many new interactions
    - You want a fresh analysis of your learning patterns

    The refresh happens in the background and may take a few minutes.
    """
    try:
        # Queue the refresh task
        synthesize_full_memory_task.delay(
            user_id=current_user.id,
            lookback_days=request.lookback_days
        )

        logger.info(f"User {current_user.id} triggered memory refresh")

        return {
            "message": "Memory refresh queued",
            "user_id": current_user.id,
            "lookback_days": request.lookback_days,
            "status": "processing",
            "note": "Your memory will be updated in a few minutes. Check back soon!"
        }

    except Exception as e:
        logger.exception(f"Failed to queue memory refresh for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue memory refresh"
        )


@router.post("/me/insight")
async def add_memory_insight(
    request: MemoryInsightRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Add a specific insight to your memory.

    This lets you directly tell the AI something about yourself that might
    not be captured from interactions alone. Examples:
    - Category: "learning_style", Content: "I learn best through hands-on practice"
    - Category: "struggle_point", Content: "I often confuse affect vs effect"
    - Category: "topic_interest", Content: "I'm passionate about climate science"
    """
    from lyo_app.services.memory_synthesis import MemoryInsight

    valid_categories = [
        "learning_style", "emotional_pattern", "topic_interest",
        "struggle_point", "success_pattern"
    ]

    if request.category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
        )

    try:
        insight = MemoryInsight(
            category=request.category,
            content=request.content,
            confidence=request.confidence,
            source="user_input",
            timestamp=datetime.utcnow()
        )

        success = await memory_synthesis_service.update_memory_insight(
            user_id=current_user.id,
            insight=insight,
            db=db
        )

        if success:
            return {
                "message": "Insight added to memory",
                "category": request.category,
                "content": request.content
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add insight to memory"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to add memory insight for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add insight to memory"
        )


@router.get("/me/stats", response_model=MemoryStatsResponse)
async def get_my_memory_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get statistics about your memory and AI interactions.

    Shows you how much the AI knows about you and how up-to-date that
    knowledge is.
    """
    from lyo_app.ai_agents.models import MentorInteraction
    from sqlalchemy import func

    try:
        # Get interaction stats
        interaction_result = await db.execute(
            select(
                func.count(MentorInteraction.id).label("total"),
                func.count(func.distinct(MentorInteraction.session_id)).label("sessions"),
                func.max(MentorInteraction.timestamp).label("last_interaction")
            ).where(MentorInteraction.user_id == current_user.id)
        )
        stats = interaction_result.first()

        memory = current_user.user_context_summary or ""
        memory_chars = len(memory)

        # Calculate memory health score
        # Based on: recency, interaction count, and memory existence
        health_score = 0.0

        if memory:
            health_score += 0.4  # Base score for having a memory

        if stats.total and stats.total > 10:
            health_score += 0.2  # Bonus for substantial interaction history

        if stats.last_interaction:
            days_since = (datetime.utcnow() - stats.last_interaction).days
            if days_since < 7:
                health_score += 0.3
            elif days_since < 30:
                health_score += 0.2
            elif days_since < 90:
                health_score += 0.1

        # Check if memory is up to date
        if current_user.updated_at and stats.last_interaction:
            if current_user.updated_at >= stats.last_interaction:
                health_score += 0.1

        return MemoryStatsResponse(
            total_interactions=stats.total or 0,
            sessions_count=stats.sessions or 0,
            memory_size_chars=memory_chars,
            last_interaction=stats.last_interaction,
            last_memory_update=current_user.updated_at,
            memory_health_score=min(health_score, 1.0)
        )

    except Exception as e:
        logger.exception(f"Failed to get memory stats for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get memory statistics"
        )


@router.get("/me/prompt-preview")
async def preview_memory_prompt(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Preview how your memory appears to the AI.

    This shows you the exact memory context that gets injected into every
    AI conversation. Useful for understanding how the AI sees you.
    """
    try:
        prompt = await memory_synthesis_service.get_memory_for_prompt(
            user_id=current_user.id,
            db=db
        )

        return {
            "user_id": current_user.id,
            "memory_prompt": prompt,
            "character_count": len(prompt),
            "note": "This is what the AI sees about you at the start of each conversation"
        }

    except Exception as e:
        logger.exception(f"Failed to preview memory prompt for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate memory preview"
        )
