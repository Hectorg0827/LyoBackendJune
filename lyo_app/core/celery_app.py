"""
Production Celery worker configuration for async task processing.
Handles course generation and other background tasks with Redis pub/sub.
Includes Celery Beat for scheduled proactive engagement tasks.
"""

import os
import logging
from typing import Callable, Optional, Dict, Any
from celery import Celery
from celery.signals import worker_ready, worker_shutting_down
from celery.schedules import crontab
from kombu import Queue

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

# Celery configuration
CELERY_BROKER_URL = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = getattr(settings, "CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# Create Celery app
celery_app = Celery("lyo_backend")

# Configure Celery
celery_app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,
    task_default_queue="lyo_tasks",
    task_routes={
        "lyo_app.tasks.course_generation.*": {"queue": "course_generation"},
        "lyo_app.tasks.notifications.*": {"queue": "notifications"},
        "lyo_app.tasks.feeds.*": {"queue": "feeds"},
        "lyo_app.tasks.memory_synthesis.*": {"queue": "memory"},
        "lyo_app.tasks.proactive_engagement.*": {"queue": "engagement"},
        "lyo_app.tasks.calendar_sync.*": {"queue": "calendar"},
    },
    task_queues=(
        Queue("lyo_tasks", routing_key="lyo_tasks"),
        Queue("course_generation", routing_key="course_generation"),
        Queue("notifications", routing_key="notifications"),
        Queue("feeds", routing_key="feeds"),
        Queue("memory", routing_key="memory"),
        Queue("engagement", routing_key="engagement"),
        Queue("calendar", routing_key="calendar"),
    ),
    # Retry configuration
    task_retry_jitter=True,
    task_retry_max_delay=60 * 5,  # 5 minutes

    # ==================== Celery Beat Schedule ====================
    # These scheduled tasks power the proactive engagement system
    beat_schedule={
        # Check for streaks about to break - every hour
        "check-streak-reminders-hourly": {
            "task": "lyo_app.tasks.proactive_engagement.check_streak_reminders",
            "schedule": crontab(minute=0),  # Every hour at :00
            "options": {"queue": "engagement"}
        },

        # Check for spaced repetition items due - twice daily
        "check-spaced-rep-morning": {
            "task": "lyo_app.tasks.proactive_engagement.check_spaced_repetition_due",
            "schedule": crontab(hour=9, minute=0),  # 9 AM UTC
            "options": {"queue": "engagement"}
        },
        "check-spaced-rep-evening": {
            "task": "lyo_app.tasks.proactive_engagement.check_spaced_repetition_due",
            "schedule": crontab(hour=18, minute=0),  # 6 PM UTC
            "options": {"queue": "engagement"}
        },

        # Check for inactive users - daily at noon
        "check-inactive-users-daily": {
            "task": "lyo_app.tasks.proactive_engagement.check_inactive_users",
            "schedule": crontab(hour=12, minute=0),  # 12 PM UTC
            "options": {"queue": "engagement"}
        },

        # Send weekly digests - Sunday at 6 PM
        "send-weekly-digests": {
            "task": "lyo_app.tasks.proactive_engagement.send_weekly_digests",
            "schedule": crontab(hour=18, minute=0, day_of_week=0),  # Sunday 6 PM
            "options": {"queue": "engagement"}
        },

        # Batch memory refresh - nightly at 3 AM
        "batch-memory-refresh-nightly": {
            "task": "lyo_app.tasks.memory_synthesis.batch_memory_refresh",
            "schedule": crontab(hour=3, minute=0),  # 3 AM UTC
            "options": {"queue": "memory"}
        },
    },
)

# Worker event handlers
@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Handle worker ready event."""
    logger.info(f"Celery worker ready: {sender}")


@worker_shutting_down.connect
def worker_shutting_down_handler(sender=None, **kwargs):
    """Handle worker shutdown event."""
    logger.info(f"Celery worker shutting down: {sender}")
