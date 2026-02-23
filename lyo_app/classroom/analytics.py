from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Literal
import logging
from datetime import datetime

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.core.database import get_db
from lyo_app.classroom.models import ClassroomSession, ClassroomInteraction

logger = logging.getLogger(__name__)

router = APIRouter()

# Schema for the incoming iOS telemetry
class LyoAnalyticsEvent(BaseModel):
    event_type: Literal["card_viewed", "quiz_answered", "reflection_submitted", "lesson_completed"]
    card_id: str
    topic: Optional[str] = None
    
    # Specific to 'card_viewed'
    duration_seconds: Optional[float] = None
    
    # Specific to 'quiz_answered'
    is_correct: Optional[bool] = None
    
    # Specific to 'reflection_submitted'
    word_count: Optional[int] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)

@router.post("/event")
async def track_analytics_event(event: LyoAnalyticsEvent, db: AsyncSession = Depends(get_db)):
    """
    Ingest a telemetry event from the iOS app.
    Inserts directly into the `classroom_interactions` table.
    """
    try:
        # 1. Log for immediate terminal visibility
        log_msg = f"[ANALYTICS] {event.event_type.upper()} | Card: {event.card_id}"
        
        if event.event_type == "card_viewed":
            log_msg += f" | Duration: {event.duration_seconds}s"
        elif event.event_type == "quiz_answered":
            log_msg += f" | Correct: {event.is_correct}"
        elif event.event_type == "reflection_submitted":
            log_msg += f" | Words: {event.word_count}"
            
        logger.info(log_msg)
        
        # 2. Persist to Database
        # Note: In a fully authenticated session, we'd lookup `ClassroomSession` using a known session_id or user.
        # For Sprint 5 tracking, we simply insert the core metrics.
        interaction = ClassroomInteraction(
            event_type=event.event_type,
            card_id=event.card_id,
            topic=event.topic,
            duration_seconds=event.duration_seconds,
            is_correct=event.is_correct,
            word_count=event.word_count
        )
        
        db.add(interaction)
        await db.commit()
        
        return {"status": "success", "message": "Event logged seamlessly."}
        
    except Exception as e:
        logger.error(f"Error logging analytics event: {e}")
        raise HTTPException(status_code=500, detail="Failed to log analytics event")
