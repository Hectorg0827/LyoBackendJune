"""
Calendar Sync Celery Tasks

Background tasks for:
- Periodic calendar sync
- Event prep reminder generation
- Learning session scheduling based on calendar
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List

from celery import current_task
from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from lyo_app.core.celery_app import celery_app
from lyo_app.core.config import settings
from lyo_app.auth.models import User

logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = getattr(settings, "DATABASE_URL", "postgresql+asyncpg://lyo_user:lyo_password@localhost:5432/lyo_db")
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg2://")

sync_engine = create_engine(SYNC_DATABASE_URL)
SyncSessionLocal = sessionmaker(bind=sync_engine)

ASYNC_DATABASE_URL = DATABASE_URL
async_engine = create_async_engine(ASYNC_DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


def get_sync_db() -> Session:
    return SyncSessionLocal()


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="lyo_app.tasks.calendar_sync.sync_user_calendar")
def sync_user_calendar_task(self, user_id: int, connection_data: dict):
    """
    Sync a user's calendar and detect learning events.
    """
    logger.info(f"Syncing calendar for user {user_id}")

    try:
        async def _sync():
            from lyo_app.integrations.calendar_integration import (
                calendar_service,
                CalendarConnection,
                CalendarProvider
            )

            # Reconstruct connection from stored data
            connection = CalendarConnection(
                user_id=user_id,
                provider=CalendarProvider(connection_data["provider"]),
                access_token=connection_data["access_token"],
                refresh_token=connection_data.get("refresh_token"),
                token_expires_at=datetime.fromisoformat(connection_data["token_expires_at"]) if connection_data.get("token_expires_at") else None,
                calendar_id=connection_data.get("calendar_id", "primary"),
                sync_enabled=True,
                last_sync=None,
                created_at=datetime.utcnow()
            )

            # Fetch events
            events = await calendar_service.fetch_google_events(connection, days_ahead=14)

            # Find events needing prep
            prep_events = calendar_service.get_events_needing_prep(events, max_days_ahead=7)

            # Queue prep reminders for each event
            for event in prep_events:
                queue_event_prep_reminder.delay(
                    user_id=user_id,
                    event_id=event.id,
                    event_title=event.title,
                    event_category=event.category.value,
                    event_time=event.start_time.isoformat(),
                    prep_days=event.prep_days_before,
                    keywords=event.learning_keywords
                )

            return {
                "events_found": len(events),
                "prep_events": len(prep_events),
                "event_titles": [e.title for e in prep_events[:5]]
            }

        result = run_async(_sync())
        logger.info(f"Calendar sync complete for user {user_id}: {result}")
        return {"status": "success", "user_id": user_id, **result}

    except Exception as e:
        logger.exception(f"Calendar sync failed for user {user_id}: {e}")
        raise self.retry(exc=e, countdown=300, max_retries=2)


@celery_app.task(bind=True, name="lyo_app.tasks.calendar_sync.queue_event_prep_reminder")
def queue_event_prep_reminder(
    self,
    user_id: int,
    event_id: str,
    event_title: str,
    event_category: str,
    event_time: str,
    prep_days: int,
    keywords: List[str]
):
    """
    Queue a preparation reminder for a calendar event.
    """
    logger.info(f"Queueing prep reminder for user {user_id}, event: {event_title}")

    try:
        event_dt = datetime.fromisoformat(event_time)
        days_until = (event_dt - datetime.utcnow()).days

        # Generate personalized message based on category
        category_messages = {
            "exam": f"Your exam '{event_title}' is in {days_until} days. Ready for a review session?",
            "interview": f"Interview '{event_title}' coming up in {days_until} days. Let's practice!",
            "presentation": f"Presentation '{event_title}' is in {days_until} days. Want to prepare?",
            "quiz": f"Quiz '{event_title}' in {days_until} days. Quick review?",
            "test": f"Test '{event_title}' coming up. Time to prepare!",
            "deadline": f"Deadline '{event_title}' approaching in {days_until} days."
        }

        message = category_messages.get(
            event_category,
            f"'{event_title}' is coming up in {days_until} days."
        )

        # Send push notification
        from lyo_app.tasks.notifications import send_push_notification_task
        send_push_notification_task.delay(
            user_id=str(user_id),
            title=f"Prepare for {event_category.title()}",
            body=message,
            data={
                "type": "calendar_prep",
                "event_id": event_id,
                "event_category": event_category,
                "keywords": keywords,
                "action": "start_prep_session"
            }
        )

        return {
            "status": "queued",
            "user_id": user_id,
            "event": event_title,
            "days_until": days_until
        }

    except Exception as e:
        logger.exception(f"Failed to queue prep reminder: {e}")
        raise


@celery_app.task(bind=True, name="lyo_app.tasks.calendar_sync.generate_prep_session")
def generate_prep_session_task(
    self,
    user_id: int,
    event_id: str,
    event_title: str,
    event_category: str,
    keywords: List[str]
):
    """
    Generate a personalized prep session based on a calendar event.
    """
    logger.info(f"Generating prep session for user {user_id}, event: {event_title}")

    try:
        async def _generate():
            from lyo_app.services.memory_synthesis import memory_synthesis_service
            from lyo_app.integrations.calendar_integration import calendar_service, CalendarEvent, EventCategory

            async with AsyncSessionLocal() as db:
                # Get user's memory for personalization
                memory = await memory_synthesis_service.get_memory_for_prompt(user_id, db)

                # Create a minimal event for prep plan
                event = CalendarEvent(
                    id=event_id,
                    title=event_title,
                    description=None,
                    start_time=datetime.utcnow() + timedelta(days=3),  # Placeholder
                    end_time=datetime.utcnow() + timedelta(days=3, hours=1),
                    location=None,
                    category=EventCategory(event_category),
                    learning_keywords=keywords,
                    preparation_needed=True,
                    prep_days_before=2,
                    confidence=0.9
                )

                # Generate prep plan
                plan = await calendar_service.generate_prep_plan(event, memory)

                return plan

        result = run_async(_generate())
        logger.info(f"Prep session generated for user {user_id}")
        return {"status": "success", "user_id": user_id, "plan": result}

    except Exception as e:
        logger.exception(f"Failed to generate prep session: {e}")
        raise


@celery_app.task(bind=True, name="lyo_app.tasks.calendar_sync.batch_calendar_sync")
def batch_calendar_sync_task(self):
    """
    Batch sync calendars for all connected users.
    Runs daily to check for new events.
    """
    logger.info("Running batch calendar sync...")

    # In a real implementation, we'd query a CalendarConnection table
    # For now, this is a placeholder that would iterate through connected users

    return {
        "status": "success",
        "message": "Batch sync would process all connected calendars"
    }
