from datetime import datetime
import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from lyo_app.services.analytics_service import analytics_service

logger = logging.getLogger(__name__)

router = APIRouter()


class LyoAnalyticsEvent(BaseModel):
    """Telemetry envelope shared by legacy card events and newer classroom UX events."""

    # New classroom surfaces emit event names such as classroom_advance_tapped,
    # while older clients emit card_viewed / quiz_answered. Do not reject valid
    # product telemetry merely because it was added after this schema.
    model_config = ConfigDict(extra="allow")

    event_type: str = Field(..., min_length=1)
    card_id: Optional[str] = None
    topic: Optional[str] = None
    duration_seconds: Optional[float] = None
    is_correct: Optional[bool] = None
    word_count: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


@router.post("/event")
async def track_analytics_event(event: LyoAnalyticsEvent):
    """
    Ingest client telemetry without forcing every UX event into a card model.

    Card-scoped learning events remain durable ClassroomInteraction rows.
    General classroom/UI events are recorded as system events so current iOS
    telemetry (advance taps, drawer opens, onboarding events, etc.) is accepted
    without inventing a fake card_id.
    """
    if event.card_id:
        await analytics_service.track_interaction(
            event_type=event.event_type,
            card_id=event.card_id,
            topic=event.topic,
            duration_seconds=event.duration_seconds,
            is_correct=event.is_correct,
            word_count=event.word_count,
        )
    else:
        properties = event.model_dump(exclude_none=True)
        properties.pop("event_type", None)
        await analytics_service.track_system_event(event.event_type, properties)

    return {
        "status": "success",
        "message": "Event received and buffered for processing.",
    }
