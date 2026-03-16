import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.core.database import AsyncSessionLocal
from lyo_app.auth.models import User  # Ensure User is registered
from lyo_app.classroom.models import ClassroomSession, ClassroomInteraction

logger = logging.getLogger(__name__)

class AnalyticsService:
    """
    Unified Analytics Service for Lyo Backend.
    Handles telemetry ingestion from clients and server-side event tracking.
    """

    @staticmethod
    async def track_interaction(
        event_type: str,
        card_id: str,
        topic: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        is_correct: Optional[bool] = None,
        word_count: Optional[int] = None,
        session_id: Optional[int] = None,
        user_id: Optional[int] = None
    ):
        """
        Track a specific student interaction (usually from iOS telemetry).
        Persists to the local PostgreSQL database for immediate visibility and internal tools.
        """
        try:
            # 1. Terminal/Log visibility
            log_msg = f"[ANALYTICS] {event_type.upper()} | Card: {card_id}"
            if topic: log_msg += f" | Topic: {topic}"
            if duration_seconds is not None: log_msg += f" | Duration: {duration_seconds}s"
            if is_correct is not None: log_msg += f" | Correct: {is_correct}"
            
            logger.info(log_msg)

            # 2. Database Persistence
            async with AsyncSessionLocal() as db:
                interaction = ClassroomInteraction(
                    event_type=event_type,
                    card_id=card_id,
                    topic=topic,
                    duration_seconds=duration_seconds,
                    is_correct=is_correct,
                    word_count=word_count,
                    session_id=session_id
                )
                db.add(interaction)
                await db.commit()
                
            # 3. External Platform Hook (Future: Firebase Measurement Protocol / Mixpanel)
            # asyncio.create_task(dispatch_to_external_platforms(event_type, ...))
            
        except Exception as e:
            logger.error(f"Failed to track interaction: {e}")

    @staticmethod
    async def track_system_event(
        event_name: str,
        properties: Dict[str, Any],
        user_id: Optional[int] = None
    ):
        """
        Track a high-level system event (e.g., 'course_generated', 'subscription_updated').
        These are server-side events that don't necessarily map to a 'card' interaction.
        """
        try:
            logger.info(f"[SYSTEM_EVENT] {event_name} | User: {user_id} | {properties}")
            
            # For now, we mainly log these to the unified log stream.
            # In Phase 2 expansion, these will be dispatched to Mixpanel/Firebase.
            
        except Exception as e:
            logger.error(f"Failed to track system event {event_name}: {e}")

analytics_service = AnalyticsService()
