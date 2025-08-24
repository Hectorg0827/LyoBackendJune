"""Celery application configuration for async task processing."""

import os
from celery import Celery
from lyo_app.core.settings import settings

# Create Celery instance
celery_app = Celery(
    "lyo_backend",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "lyo_app.workers.course_generation",
        "lyo_app.workers.push_notifications",
        "lyo_app.workers.content_processing"
    ]
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task routing
    task_routes={
        "lyo_app.workers.course_generation.*": {"queue": "generation"},
        "lyo_app.workers.push_notifications.*": {"queue": "notifications"},
        "lyo_app.workers.content_processing.*": {"queue": "content"},
    },
    
    # Worker settings
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    
    # Result settings - IMPORTANT: Keep results small!
    # Store large data in database, not Redis
    result_expires=3600,  # 1 hour
    result_compression='zlib',
    
    # Task timeouts
    task_soft_time_limit=settings.CELERY_TASK_TIMEOUT - 60,  # Grace period
    task_time_limit=settings.CELERY_TASK_TIMEOUT,
    
    # Retry settings
    task_default_retry_delay=60,
    task_max_retries=3,
    
    # Beat schedule (if using celery beat)
    beat_schedule={
        'cleanup-expired-tasks': {
            'task': 'lyo_app.workers.maintenance.cleanup_expired_tasks',
            'schedule': 3600.0,  # Every hour
        },
        'update-user-streaks': {
            'task': 'lyo_app.workers.gamification.update_daily_streaks',
            'schedule': 86400.0,  # Daily at midnight UTC
        },
    },
)

# Task state mapping from Celery to API
CELERY_STATE_MAPPING = {
    "PENDING": "QUEUED",
    "STARTED": "RUNNING", 
    "PROGRESS": "RUNNING",
    "SUCCESS": "DONE",
    "FAILURE": "ERROR",
    "REVOKED": "ERROR",
    "RETRY": "RUNNING",
}


def get_api_task_state(celery_state: str) -> str:
    """Convert Celery task state to API task state."""
    return CELERY_STATE_MAPPING.get(celery_state, "QUEUED")
