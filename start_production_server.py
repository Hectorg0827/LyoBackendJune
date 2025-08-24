#!/usr/bin/env python3
"""
Production startup script for LyoBackend.
Handles database migrations, Redis setup, and server startup.
"""

import asyncio
import logging
import os
import sys
import subprocess
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from lyo_app.core.config import settings
from lyo_app.core.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_database():
    """Check database connection and run migrations if needed."""
    logger.info("Checking database connection...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("✓ Database connection successful")
        
        # Run Alembic migrations
        logger.info("Running database migrations...")
        result = subprocess.run([
            "alembic", "upgrade", "head"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✓ Database migrations completed")
        else:
            logger.error(f"Database migration failed: {result.stderr}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        return False


def check_redis():
    """Check Redis connection."""
    logger.info("Checking Redis connection...")
    
    try:
        import redis
        client = redis.Redis.from_url(settings.redis_url)
        client.ping()
        logger.info("✓ Redis connection successful")
        return True
        
    except Exception as e:
        logger.error(f"Redis check failed: {e}")
        return False


def start_celery_workers():
    """Start Celery workers in background."""
    logger.info("Starting Celery workers...")
    
    try:
        # Start Celery worker process
        worker_process = subprocess.Popen([
            "celery", "-A", "lyo_app.core.celery_app", "worker",
            "--loglevel=info",
            "--concurrency=4",
            "--queues=default,course_generation,push_notifications,feed_curation"
        ])
        
        logger.info(f"✓ Celery worker started (PID: {worker_process.pid})")
        return worker_process
        
    except Exception as e:
        logger.error(f"Failed to start Celery workers: {e}")
        return None


def start_server():
    """Start the FastAPI server."""
    logger.info("Starting FastAPI server...")
    
    try:
        import uvicorn
        
        # Production server configuration
        config = uvicorn.Config(
            app="production_main:app",
            host=settings.host,
            port=settings.port,
            workers=4 if settings.environment == "production" else 1,
            log_level=settings.log_level.lower(),
            access_log=True,
            reload=settings.debug,
            proxy_headers=True,
            forwarded_allow_ips="*"
        )
        
        server = uvicorn.Server(config)
        return server
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return None


async def main():
    """Main startup routine."""
    logger.info("🚀 Starting LyoBackend production server...")
    
    # Check prerequisites
    logger.info("Checking system prerequisites...")
    
    # Check database
    if not await check_database():
        logger.error("Database check failed. Exiting.")
        sys.exit(1)
    
    # Check Redis
    if not check_redis():
        logger.error("Redis check failed. Exiting.")
        sys.exit(1)
    
    logger.info("✓ All system prerequisites satisfied")
    
    # Start background services
    celery_process = None
    if settings.environment == "production":
        celery_process = start_celery_workers()
        if not celery_process:
            logger.warning("Celery workers failed to start - continuing without background tasks")
    
    # Start web server
    server = start_server()
    if not server:
        logger.error("Failed to start web server. Exiting.")
        if celery_process:
            celery_process.terminate()
        sys.exit(1)
    
    try:
        logger.info("🎉 LyoBackend production server is running!")
        logger.info(f"📍 Server: http://{settings.host}:{settings.port}")
        logger.info(f"📖 API Docs: http://{settings.host}:{settings.port}/docs")
        logger.info(f"🏥 Health Check: http://{settings.host}:{settings.port}/api/v1/health/")
        logger.info("Press CTRL+C to stop the server...")
        
        # Start the server
        await server.serve()
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal...")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        # Cleanup
        logger.info("Shutting down services...")
        if celery_process:
            logger.info("Terminating Celery workers...")
            celery_process.terminate()
            celery_process.wait()
        
        logger.info("✓ LyoBackend shutdown complete")


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 11):
        logger.error("Python 3.11 or higher is required")
        sys.exit(1)
    
    # Set environment variables if not set
    if not os.getenv("DATABASE_URL"):
        logger.warning("DATABASE_URL not set - using default PostgreSQL connection")
    
    if not os.getenv("REDIS_URL"):
        logger.warning("REDIS_URL not set - using default Redis connection")
    
    # Run the startup routine
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Startup interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        sys.exit(1)
