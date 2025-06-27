"""
Celery configuration and background tasks for LyoApp.
Handles async email sending, analytics processing, and other background jobs.
"""

import os
from celery import Celery
from kombu import Exchange, Queue

from lyo_app.core.config import settings
from lyo_app.core.logging import get_logger

logger = get_logger(__name__)

# Celery configuration
celery_app = Celery(
    "lyoapp",
    broker=getattr(settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/1'),
    backend=getattr(settings, 'CELERY_RESULT_BACKEND', 'redis://localhost:6379/2'),
    include=[
        'lyo_app.core.celery_tasks.email_tasks',
        'lyo_app.core.celery_tasks.analytics_tasks',
        'lyo_app.core.celery_tasks.cleanup_tasks'
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Task routing
    task_routes={
        'lyo_app.core.celery_tasks.email_tasks.*': {'queue': 'email'},
        'lyo_app.core.celery_tasks.analytics_tasks.*': {'queue': 'analytics'},
        'lyo_app.core.celery_tasks.cleanup_tasks.*': {'queue': 'cleanup'},
    },
    
    # Default queue configuration
    task_default_queue='default',
    task_queues=(
        Queue('default', Exchange('default'), routing_key='default'),
        Queue('email', Exchange('email'), routing_key='email'),
        Queue('analytics', Exchange('analytics'), routing_key='analytics'),
        Queue('cleanup', Exchange('cleanup'), routing_key='cleanup'),
    ),
    
    # Task execution settings
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    
    # Result backend settings
    result_expires=3600,  # 1 hour
    
    # Worker settings
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)
