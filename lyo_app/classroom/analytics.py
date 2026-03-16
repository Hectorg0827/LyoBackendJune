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

from lyo_app.services.analytics_service import analytics_service

@router.post("/event")
async def track_analytics_event(event: LyoAnalyticsEvent):
    """
    Ingest a telemetry event from the iOS app.
    Uses the unified AnalyticsService for persistence and dispatching.
    """
    # Simply delegate to the service
    await analytics_service.track_interaction(
        event_type=event.event_type,
        card_id=event.card_id,
        topic=event.topic,
        duration_seconds=event.duration_seconds,
        is_correct=event.is_correct,
        word_count=event.word_count
    )
    
    return {"status": "success", "message": "Event received and buffered for processing."}
