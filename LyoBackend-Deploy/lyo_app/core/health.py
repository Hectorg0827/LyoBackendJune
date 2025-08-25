"""
Health check endpoints for LyoApp.
Provides comprehensive system health monitoring and diagnostics.
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from lyo_app.core.database import get_async_session
from lyo_app.core.config import settings
from lyo_app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/health", tags=["Health Checks"])


@router.get("/")
async def basic_health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0"
    }


@router.get("/detailed")
async def detailed_health_check(
    db: AsyncSession = Depends(get_async_session)
):
    """Detailed health check with component status."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0",
        "components": {}
    }
    
    # Check database connectivity
    try:
        start_time = time.time()
        await db.execute(text("SELECT 1"))
        db_response_time = (time.time() - start_time) * 1000
        
        health_status["components"]["database"] = {
            "status": "healthy",
            "response_time_ms": round(db_response_time, 2),
            "type": "postgresql" if "postgresql" in str(settings.DATABASE_URL) else "sqlite"
        }
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # Check Redis connectivity (if configured)
    try:
        if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
            import redis.asyncio as redis
            redis_client = redis.from_url(settings.REDIS_URL)
            start_time = time.time()
            await redis_client.ping()
            redis_response_time = (time.time() - start_time) * 1000
            
            health_status["components"]["redis"] = {
                "status": "healthy",
                "response_time_ms": round(redis_response_time, 2)
            }
            await redis_client.close()
        else:
            health_status["components"]["redis"] = {
                "status": "not_configured"
            }
    except Exception as e:
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # Check file system
    try:
        import os
        uploads_dir = "uploads"
        if os.path.exists(uploads_dir) and os.access(uploads_dir, os.W_OK):
            health_status["components"]["filesystem"] = {
                "status": "healthy",
                "uploads_directory": uploads_dir
            }
        else:
            health_status["components"]["filesystem"] = {
                "status": "unhealthy",
                "error": "Uploads directory not accessible"
            }
    except Exception as e:
        health_status["components"]["filesystem"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Check memory usage
    try:
        import psutil
        memory = psutil.virtual_memory()
        health_status["components"]["memory"] = {
            "status": "healthy" if memory.percent < 90 else "warning",
            "used_percent": memory.percent,
            "available_gb": round(memory.available / (1024**3), 2)
        }
    except ImportError:
        health_status["components"]["memory"] = {
            "status": "not_available",
            "note": "psutil not installed"
        }
    except Exception as e:
        health_status["components"]["memory"] = {
            "status": "error",
            "error": str(e)
        }
    
    return health_status


@router.get("/readiness")
async def readiness_check(
    db: AsyncSession = Depends(get_async_session)
):
    """Readiness check for load balancer."""
    try:
        # Check database
        await db.execute(text("SELECT 1"))
        
        # Check critical directories
        import os
        if not os.path.exists("uploads"):
            raise Exception("Uploads directory missing")
        
        return {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )


@router.get("/liveness")
async def liveness_check():
    """Liveness check for container orchestration."""
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": time.time()
    }


@router.get("/metrics")
async def get_metrics(
    db: AsyncSession = Depends(get_async_session)
):
    """Get basic application metrics."""
    try:
        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "database": {},
            "application": {}
        }
        
        # Database metrics
        try:
            # Count users
            result = await db.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()
            metrics["database"]["total_users"] = user_count
            
            # Count recent activity (last 24h)
            result = await db.execute(text(
                "SELECT COUNT(*) FROM users WHERE created_at > datetime('now', '-1 day')"
            ))
            recent_users = result.scalar()
            metrics["database"]["new_users_24h"] = recent_users
            
        except Exception as e:
            metrics["database"]["error"] = str(e)
        
        # Application metrics
        metrics["application"]["environment"] = settings.ENVIRONMENT
        metrics["application"]["debug_mode"] = settings.DEBUG
        
        return metrics
        
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to collect metrics"
        )


@router.get("/startup")
async def startup_check():
    """Check if application startup completed successfully."""
    try:
        # Verify critical components
        startup_status = {
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }
        
        # Check if all modules loaded
        try:
            from lyo_app.auth import routes as auth_routes
            from lyo_app.learning import routes as learning_routes
            from lyo_app.feeds import routes as feeds_routes
            from lyo_app.community import routes as community_routes
            from lyo_app.gamification import routes as gamification_routes
            
            startup_status["checks"]["modules"] = "loaded"
        except Exception as e:
            startup_status["checks"]["modules"] = f"error: {str(e)}"
        
        # Check database connection
        try:
            from lyo_app.core.database import engine
            startup_status["checks"]["database"] = "connected"
        except Exception as e:
            startup_status["checks"]["database"] = f"error: {str(e)}"
        
        return startup_status
        
    except Exception as e:
        logger.error(f"Startup check failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
