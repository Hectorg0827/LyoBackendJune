"""
Proactive Engagement Celery Tasks

Scheduled and on-demand tasks for proactive user engagement.
These tasks run periodically to identify users who need nudges
and queue personalized notifications.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from celery import current_task
from sqlalchemy import create_engine, select, func, and_
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from lyo_app.core.celery_app import celery_app
from lyo_app.core.config import settings
from lyo_app.auth.models import User
from lyo_app.ai_agents.models import MentorInteraction
from lyo_app.gamification.models import Streak
from lyo_app.personalization.models import SpacedRepetitionSchedule

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
    """Get synchronous database session for Celery tasks."""
    return SyncSessionLocal()


def run_async(coro):
    """Helper to run async code in sync Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ==================== Scheduled Tasks ====================

@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.check_streak_reminders")
def check_streak_reminders_task(self):
    """
    Check for users whose streaks are about to break and send reminders.

    Runs every hour to catch users before their 24-hour window closes.
    """
    logger.info("Running streak reminder check...")
    db = get_sync_db()

    try:
        # Find streaks that will break in 4-6 hours
        now = datetime.utcnow()
        warning_threshold = now - timedelta(hours=20)  # 20 hours since last activity

        # Get streaks at risk
        streaks_at_risk = db.query(Streak).filter(
            and_(
                Streak.current_count >= 3,  # Only remind if they have a real streak
                Streak.last_activity_at <= warning_threshold,
                Streak.last_activity_at >= warning_threshold - timedelta(hours=4)  # Don't re-remind
            )
        ).all()

        logger.info(f"Found {len(streaks_at_risk)} streaks at risk")

        queued_count = 0
        for streak in streaks_at_risk:
            # Queue individual nudge
            send_streak_nudge_task.delay(
                user_id=streak.user_id,
                streak_count=streak.current_count,
                nudge_type="warning"
            )
            queued_count += 1

        return {
            "status": "success",
            "streaks_checked": len(streaks_at_risk),
            "nudges_queued": queued_count
        }

    except Exception as e:
        logger.exception(f"Streak reminder check failed: {e}")
        raise
    finally:
        db.close()


@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.check_spaced_repetition_due")
def check_spaced_repetition_due_task(self):
    """
    Check for users with spaced repetition items due for review.

    Runs twice daily (morning and evening) to remind users.
    """
    logger.info("Running spaced repetition due check...")
    db = get_sync_db()

    try:
        now = datetime.utcnow()

        # Get users with items due
        result = db.execute(
            select(
                SpacedRepetitionSchedule.user_id,
                func.count(SpacedRepetitionSchedule.id).label("due_count")
            )
            .where(SpacedRepetitionSchedule.next_review <= now)
            .group_by(SpacedRepetitionSchedule.user_id)
            .having(func.count(SpacedRepetitionSchedule.id) >= 3)  # At least 3 items due
        )
        users_with_due_items = result.fetchall()

        logger.info(f"Found {len(users_with_due_items)} users with items due")

        queued_count = 0
        for row in users_with_due_items:
            user_id, due_count = row
            send_spaced_rep_nudge_task.delay(
                user_id=user_id,
                due_count=due_count
            )
            queued_count += 1

        return {
            "status": "success",
            "users_checked": len(users_with_due_items),
            "nudges_queued": queued_count
        }

    except Exception as e:
        logger.exception(f"Spaced repetition check failed: {e}")
        raise
    finally:
        db.close()


@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.check_inactive_users")
def check_inactive_users_task(self, inactive_days: int = 7):
    """
    Check for users who haven't been active and send comeback nudges.

    Runs daily to identify users who might be churning.
    """
    logger.info(f"Running inactive user check (threshold: {inactive_days} days)...")
    db = get_sync_db()

    try:
        cutoff = datetime.utcnow() - timedelta(days=inactive_days)
        max_cutoff = datetime.utcnow() - timedelta(days=inactive_days + 7)  # Don't re-nudge

        # Find users with last interaction in the window
        result = db.execute(
            select(
                MentorInteraction.user_id,
                func.max(MentorInteraction.timestamp).label("last_active")
            )
            .group_by(MentorInteraction.user_id)
            .having(
                and_(
                    func.max(MentorInteraction.timestamp) <= cutoff,
                    func.max(MentorInteraction.timestamp) >= max_cutoff
                )
            )
        )
        inactive_users = result.fetchall()

        logger.info(f"Found {len(inactive_users)} inactive users")

        queued_count = 0
        for row in inactive_users:
            user_id, last_active = row
            days_inactive = (datetime.utcnow() - last_active).days
            send_comeback_nudge_task.delay(
                user_id=user_id,
                days_inactive=days_inactive
            )
            queued_count += 1

        return {
            "status": "success",
            "users_checked": len(inactive_users),
            "nudges_queued": queued_count
        }

    except Exception as e:
        logger.exception(f"Inactive user check failed: {e}")
        raise
    finally:
        db.close()


@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.send_weekly_digests")
def send_weekly_digests_task(self):
    """
    Send weekly learning digests to active users.

    Runs every Sunday evening.
    """
    logger.info("Sending weekly digests...")
    db = get_sync_db()

    try:
        since = datetime.utcnow() - timedelta(days=7)

        # Find users with activity this week
        result = db.execute(
            select(MentorInteraction.user_id)
            .where(MentorInteraction.timestamp >= since)
            .distinct()
        )
        active_users = [row[0] for row in result.fetchall()]

        logger.info(f"Sending digests to {len(active_users)} active users")

        queued_count = 0
        for user_id in active_users:
            generate_weekly_digest_task.delay(user_id=user_id)
            queued_count += 1

        return {
            "status": "success",
            "users": len(active_users),
            "digests_queued": queued_count
        }

    except Exception as e:
        logger.exception(f"Weekly digest send failed: {e}")
        raise
    finally:
        db.close()


# ==================== Individual Nudge Tasks ====================

@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.send_streak_nudge")
def send_streak_nudge_task(
    self,
    user_id: int,
    streak_count: int,
    nudge_type: str = "warning"
):
    """
    Send a streak-related nudge to a specific user.
    """
    logger.info(f"Sending streak nudge to user {user_id} (type: {nudge_type})")

    try:
        async def _send_nudge():
            from lyo_app.services.proactive_engagement import proactive_engagement_service

            async with AsyncSessionLocal() as db:
                nudge = await proactive_engagement_service.generate_streak_nudge(user_id, db)

                if nudge:
                    # Send via push notification
                    from lyo_app.tasks.notifications import send_push_notification_task
                    send_push_notification_task.delay(
                        user_id=str(user_id),
                        title=nudge.title,
                        body=nudge.message,
                        data={
                            "type": nudge.nudge_type.value,
                            "action_url": nudge.action_url,
                            "context": nudge.context_data
                        }
                    )
                    return True
                return False

        result = run_async(_send_nudge())
        return {"status": "sent" if result else "skipped", "user_id": user_id}

    except Exception as e:
        logger.exception(f"Failed to send streak nudge to user {user_id}: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=2)


@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.send_spaced_rep_nudge")
def send_spaced_rep_nudge_task(
    self,
    user_id: int,
    due_count: int
):
    """
    Send a spaced repetition review reminder to a specific user.
    """
    logger.info(f"Sending spaced rep nudge to user {user_id} ({due_count} items due)")

    try:
        async def _send_nudge():
            from lyo_app.services.proactive_engagement import proactive_engagement_service

            async with AsyncSessionLocal() as db:
                nudge = await proactive_engagement_service.generate_spaced_rep_nudge(user_id, db)

                if nudge:
                    from lyo_app.tasks.notifications import send_push_notification_task
                    send_push_notification_task.delay(
                        user_id=str(user_id),
                        title=nudge.title,
                        body=nudge.message,
                        data={
                            "type": nudge.nudge_type.value,
                            "action_url": nudge.action_url,
                            "due_count": due_count
                        }
                    )
                    return True
                return False

        result = run_async(_send_nudge())
        return {"status": "sent" if result else "skipped", "user_id": user_id}

    except Exception as e:
        logger.exception(f"Failed to send spaced rep nudge to user {user_id}: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=2)


@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.send_comeback_nudge")
def send_comeback_nudge_task(
    self,
    user_id: int,
    days_inactive: int
):
    """
    Send a comeback nudge to an inactive user.
    """
    logger.info(f"Sending comeback nudge to user {user_id} ({days_inactive} days inactive)")

    try:
        async def _send_nudge():
            from lyo_app.services.proactive_engagement import proactive_engagement_service

            async with AsyncSessionLocal() as db:
                nudge = await proactive_engagement_service.generate_comeback_nudge(user_id, db)

                if nudge:
                    from lyo_app.tasks.notifications import send_push_notification_task
                    send_push_notification_task.delay(
                        user_id=str(user_id),
                        title=nudge.title,
                        body=nudge.message,
                        data={
                            "type": nudge.nudge_type.value,
                            "action_url": nudge.action_url,
                            "days_inactive": days_inactive
                        }
                    )
                    return True
                return False

        result = run_async(_send_nudge())
        return {"status": "sent" if result else "skipped", "user_id": user_id}

    except Exception as e:
        logger.exception(f"Failed to send comeback nudge to user {user_id}: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=2)


@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.generate_weekly_digest")
def generate_weekly_digest_task(self, user_id: int):
    """
    Generate and send a weekly learning digest to a user.
    """
    logger.info(f"Generating weekly digest for user {user_id}")

    try:
        async def _generate_digest():
            from lyo_app.services.proactive_engagement import proactive_engagement_service

            async with AsyncSessionLocal() as db:
                nudge = await proactive_engagement_service.generate_weekly_digest(user_id, db)

                if nudge:
                    from lyo_app.tasks.notifications import send_push_notification_task
                    send_push_notification_task.delay(
                        user_id=str(user_id),
                        title=nudge.title,
                        body=nudge.message,
                        data={
                            "type": nudge.nudge_type.value,
                            "action_url": nudge.action_url,
                            "context": nudge.context_data
                        }
                    )
                    return nudge.context_data
                return None

        result = run_async(_generate_digest())
        return {"status": "sent" if result else "skipped", "user_id": user_id, "stats": result}

    except Exception as e:
        logger.exception(f"Failed to generate weekly digest for user {user_id}: {e}")
        raise self.retry(exc=e, countdown=120, max_retries=2)


# ==================== User-Triggered Tasks ====================

@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.analyze_user_engagement")
def analyze_user_engagement_task(self, user_id: int):
    """
    Analyze a user's engagement patterns and update their optimal notification timing.
    """
    logger.info(f"Analyzing engagement patterns for user {user_id}")

    try:
        async def _analyze():
            from lyo_app.services.proactive_engagement import proactive_engagement_service

            async with AsyncSessionLocal() as db:
                patterns = await proactive_engagement_service.analyze_user_patterns(user_id, db)

                return {
                    "user_id": user_id,
                    "preferred_hours": patterns.preferred_hours,
                    "preferred_days": patterns.preferred_days,
                    "engagement_score": patterns.engagement_score,
                    "is_at_risk": patterns.is_at_risk,
                    "current_streak": patterns.current_streak
                }

        result = run_async(_analyze())
        logger.info(f"Engagement analysis for user {user_id}: score={result['engagement_score']:.2f}")
        return result

    except Exception as e:
        logger.exception(f"Failed to analyze engagement for user {user_id}: {e}")
        raise


@celery_app.task(bind=True, name="lyo_app.tasks.proactive_engagement.get_pending_nudges")
def get_pending_nudges_task(self, user_id: int):
    """
    Get all pending nudges for a user (for display in app).
    """
    logger.info(f"Getting pending nudges for user {user_id}")

    try:
        async def _get_nudges():
            from lyo_app.services.proactive_engagement import proactive_engagement_service

            async with AsyncSessionLocal() as db:
                nudges = await proactive_engagement_service.get_pending_nudges_for_user(user_id, db)

                return [
                    {
                        "type": n.nudge_type.value,
                        "title": n.title,
                        "message": n.message,
                        "priority": n.priority.value,
                        "action_url": n.action_url,
                        "action_label": n.action_label,
                        "context": n.context_data
                    }
                    for n in nudges
                ]

        result = run_async(_get_nudges())
        return {"status": "success", "user_id": user_id, "nudges": result}

    except Exception as e:
        logger.exception(f"Failed to get pending nudges for user {user_id}: {e}")
        raise
