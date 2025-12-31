"""
Memory Synthesis Celery Tasks

Background tasks for synthesizing and maintaining user memory profiles.
These tasks run after chat sessions to update the persistent memory that
makes Lyo feel like an indispensable companion.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from celery import current_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from lyo_app.core.celery_app import celery_app
from lyo_app.core.config import settings
from lyo_app.auth.models import User
from lyo_app.ai_agents.models import MentorInteraction

logger = logging.getLogger(__name__)

# Database setup for Celery tasks
DATABASE_URL = getattr(settings, "DATABASE_URL", "postgresql+asyncpg://lyo_user:lyo_password@localhost:5432/lyo_db")
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg2://")

# Sync engine for Celery
sync_engine = create_engine(SYNC_DATABASE_URL)
SyncSessionLocal = sessionmaker(bind=sync_engine)

# Async engine for async operations within tasks
ASYNC_DATABASE_URL = DATABASE_URL
async_engine = create_async_engine(ASYNC_DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


def get_sync_db() -> Session:
    """Get synchronous database session for Celery tasks."""
    return SyncSessionLocal()


async def get_async_db() -> AsyncSession:
    """Get async database session."""
    async with AsyncSessionLocal() as session:
        yield session


def run_async(coro):
    """Helper to run async code in sync Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="lyo_app.tasks.memory_synthesis.synthesize_session_memory")
def synthesize_session_memory_task(
    self,
    user_id: int,
    session_id: str
):
    """
    Synthesize memory after a chat session completes.

    This task runs asynchronously after each meaningful chat session to:
    1. Extract key insights from the conversation
    2. Update the user's persistent memory profile
    3. Identify learning patterns and emotional signals

    Args:
        user_id: The user's database ID
        session_id: The chat session ID
    """
    logger.info(f"Starting memory synthesis for user {user_id}, session {session_id}")

    try:
        async def _synthesize():
            from lyo_app.services.memory_synthesis import memory_synthesis_service

            async with AsyncSessionLocal() as db:
                result = await memory_synthesis_service.synthesize_session_memory(
                    user_id=user_id,
                    session_id=session_id,
                    db=db
                )
                return result

        result = run_async(_synthesize())

        if result:
            logger.info(f"Memory synthesis completed for user {user_id}")
            return {"status": "success", "user_id": user_id, "session_id": session_id}
        else:
            logger.warning(f"Memory synthesis returned no result for user {user_id}")
            return {"status": "no_result", "user_id": user_id}

    except Exception as e:
        logger.exception(f"Memory synthesis failed for user {user_id}: {e}")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries), max_retries=3)


@celery_app.task(bind=True, name="lyo_app.tasks.memory_synthesis.synthesize_full_memory")
def synthesize_full_memory_task(
    self,
    user_id: int,
    lookback_days: int = 30
):
    """
    Full memory synthesis from all recent interactions.

    This task performs a comprehensive memory refresh, typically run:
    - When a user hasn't been active for a while
    - Periodically (weekly) for active users
    - When explicitly requested

    Args:
        user_id: The user's database ID
        lookback_days: How many days of history to consider
    """
    logger.info(f"Starting full memory synthesis for user {user_id}, lookback {lookback_days} days")

    try:
        async def _synthesize():
            from lyo_app.services.memory_synthesis import memory_synthesis_service

            async with AsyncSessionLocal() as db:
                result = await memory_synthesis_service.synthesize_full_memory(
                    user_id=user_id,
                    db=db,
                    lookback_days=lookback_days
                )
                return result

        result = run_async(_synthesize())

        if result:
            logger.info(f"Full memory synthesis completed for user {user_id}")
            return {"status": "success", "user_id": user_id, "memory_length": len(result)}
        else:
            logger.warning(f"Full memory synthesis returned no result for user {user_id}")
            return {"status": "no_result", "user_id": user_id}

    except Exception as e:
        logger.exception(f"Full memory synthesis failed for user {user_id}: {e}")
        raise self.retry(exc=e, countdown=120 * (2 ** self.request.retries), max_retries=2)


@celery_app.task(bind=True, name="lyo_app.tasks.memory_synthesis.batch_memory_refresh")
def batch_memory_refresh_task(
    self,
    user_ids: Optional[list] = None,
    inactive_days: int = 7,
    batch_size: int = 50
):
    """
    Batch refresh memories for multiple users.

    This task is designed to run periodically (e.g., nightly) to:
    - Refresh memories for recently active users
    - Create initial memories for users who don't have one yet

    Args:
        user_ids: Specific user IDs to refresh (optional)
        inactive_days: Only refresh users active within this many days
        batch_size: Maximum users to process in one batch
    """
    logger.info(f"Starting batch memory refresh")

    db = get_sync_db()

    try:
        if user_ids:
            # Refresh specific users
            users_to_refresh = user_ids[:batch_size]
        else:
            # Find users who need refresh:
            # 1. Active in last N days
            # 2. Either no memory or memory is stale
            since = datetime.utcnow() - timedelta(days=inactive_days)

            # Find users with recent interactions
            result = db.execute(
                select(MentorInteraction.user_id)
                .where(MentorInteraction.timestamp >= since)
                .distinct()
                .limit(batch_size)
            )
            users_to_refresh = [row[0] for row in result.fetchall()]

        # Queue individual refresh tasks
        queued_count = 0
        for user_id in users_to_refresh:
            synthesize_full_memory_task.delay(user_id=user_id, lookback_days=30)
            queued_count += 1

        logger.info(f"Batch memory refresh queued {queued_count} users")
        return {"status": "success", "queued_count": queued_count}

    except Exception as e:
        logger.exception(f"Batch memory refresh failed: {e}")
        raise
    finally:
        db.close()


@celery_app.task(bind=True, name="lyo_app.tasks.memory_synthesis.cleanup_stale_memories")
def cleanup_stale_memories_task(
    self,
    stale_days: int = 90
):
    """
    Clean up memory data for inactive users.

    For privacy and storage efficiency, this task:
    - Identifies users inactive for extended periods
    - Optionally anonymizes or clears their memory data

    Args:
        stale_days: Days of inactivity before considering cleanup
    """
    logger.info(f"Starting stale memory cleanup for users inactive > {stale_days} days")

    db = get_sync_db()

    try:
        cutoff = datetime.utcnow() - timedelta(days=stale_days)

        # Find users with old memories but no recent activity
        # Note: This is a soft cleanup - we don't delete, just flag

        # For now, just log candidates - actual cleanup requires policy decisions
        result = db.execute(
            select(User.id, User.last_login)
            .where(User.last_login < cutoff)
            .where(User.user_context_summary.isnot(None))
            .limit(100)
        )

        candidates = result.fetchall()
        logger.info(f"Found {len(candidates)} users with potentially stale memories")

        # In production, you might:
        # - Send retention notifications
        # - Anonymize data
        # - Archive to cold storage

        return {"status": "success", "candidates_found": len(candidates)}

    except Exception as e:
        logger.exception(f"Stale memory cleanup failed: {e}")
        raise
    finally:
        db.close()


# Helper function to trigger memory synthesis from other parts of the app
def trigger_session_memory_synthesis(user_id: int, session_id: str, delay_seconds: int = 10):
    """
    Queue a memory synthesis task after a session.

    Args:
        user_id: The user's ID
        session_id: The session ID
        delay_seconds: Delay before running (allows session to fully complete)
    """
    synthesize_session_memory_task.apply_async(
        args=[user_id, session_id],
        countdown=delay_seconds
    )
    logger.info(f"Queued memory synthesis for user {user_id}, session {session_id} in {delay_seconds}s")
