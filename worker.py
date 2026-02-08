#!/usr/bin/env python
"""
Lyo Temporal Worker - Runs AI workflows durably

This is a SEPARATE PROCESS from the FastAPI server.
It connects to Temporal and runs activities/workflows.

Start with:
    python worker.py

Environment variables:
    TEMPORAL_HOST: Temporal server address (default: localhost:7233)
    TEMPORAL_NAMESPACE: Temporal namespace (default: default)
    TEMPORAL_TASK_QUEUE: Task queue name (default: lyo-ai-queue)
"""

import asyncio
import logging
import os
import signal
import sys

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from temporalio.client import Client
from temporalio.worker import Worker

# Import activities and workflows
from lyo_app.temporal.activities.curriculum_activities import (
    generate_curriculum_activity,
    generate_lesson_activity,
    generate_learning_path_activity,
)
from lyo_app.temporal.workflows.course_generation import CourseGenerationWorkflowV1

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("worker.log"),
    ]
)
logger = logging.getLogger(__name__)

# Configuration
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "lyo-ai-queue")

# Graceful shutdown flag
shutdown_event = asyncio.Event()


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


async def run_worker():
    """Main worker function - connects to Temporal and runs activities."""
    logger.info(f"🚀 Starting Lyo Temporal Worker")
    logger.info(f"   Temporal Host: {TEMPORAL_HOST}")
    logger.info(f"   Namespace: {TEMPORAL_NAMESPACE}")
    logger.info(f"   Task Queue: {TASK_QUEUE}")
    
    try:
        # Connect to Temporal server
        logger.info("Connecting to Temporal server...")
        client = await Client.connect(
            TEMPORAL_HOST,
            namespace=TEMPORAL_NAMESPACE,
        )
        logger.info("✅ Connected to Temporal server")
        
        # Create worker
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            # Register workflows
            workflows=[
                CourseGenerationWorkflowV1,
            ],
            # Register activities
            activities=[
                generate_curriculum_activity,
                generate_lesson_activity,
                generate_learning_path_activity,
            ],
        )
        
        logger.info("✅ Worker configured with:")
        logger.info("   Workflows: CourseGenerationWorkflowV1")
        logger.info("   Activities: generate_curriculum_activity, generate_lesson_activity, generate_learning_path_activity")
        
        # Run worker
        logger.info(f"🔄 Worker listening on task queue: {TASK_QUEUE}")
        
        # Run until shutdown signal
        async with worker:
            await shutdown_event.wait()
        
        logger.info("Worker shut down gracefully")
        
    except Exception as e:
        logger.error(f"❌ Worker failed: {e}")
        raise


def main():
    """Entry point for the worker."""
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
