"""
Production Celery worker configuration for async task processing.
Handles course generation and other background tasks with Redis pub/sub.
"""

import os
import logging
from typing import Callable, Optional, Dict, Any
from celery import Celery
from celery.signals import worker_ready, worker_shutting_down
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
    },
    task_queues=(
        Queue("lyo_tasks", routing_key="lyo_tasks"),
        Queue("course_generation", routing_key="course_generation"),
        Queue("notifications", routing_key="notifications"),
        Queue("feeds", routing_key="feeds"),
        Queue("memory", routing_key="memory"),
    ),
    # Retry configuration
    task_retry_jitter=True,
    task_retry_max_delay=60 * 5,  # 5 minutes
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
