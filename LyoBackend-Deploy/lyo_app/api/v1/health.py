"""
Production health check API routes.
System health monitoring and readiness checks.
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from lyo_app.core.database import get_db
from lyo_app.core.redis_production import RedisPubSub
from lyo_app.core.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str = "1.0.0"
    checks: Dict[str, Any]


class ReadinessResponse(BaseModel):
    ready: bool
    timestamp: str
    services: Dict[str, bool]
    details: Dict[str, Any] = None


@router.get("/", response_model=HealthResponse)
async def health_check():
    """
    Basic health check endpoint.
    Returns 200 if service is running.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        checks={
            "api": "healthy",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Comprehensive readiness check.
    Verifies all required services are operational.
    """
    services = {}
    details = {}
    all_ready = True
    
    # Check database connection
    try:
        result = await db.execute(text("SELECT 1"))
        result.fetchone()
        services["database"] = True
        details["database"] = "Connected"
    except Exception as e:
        services["database"] = False
        details["database"] = f"Connection failed: {str(e)}"
        all_ready = False
        logger.error(f"Database health check failed: {e}")
    
    # Check Redis connection
    try:
        redis_client = RedisPubSub()
        await redis_client.ping()
        services["redis"] = True
        details["redis"] = "Connected"
        await redis_client.close()
    except Exception as e:
        services["redis"] = False
        details["redis"] = f"Connection failed: {str(e)}"
        all_ready = False
        logger.error(f"Redis health check failed: {e}")
    
    # Check Celery workers
    try:
        # Inspect active workers
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        
        if active_workers:
            services["celery"] = True
            details["celery"] = f"Active workers: {len(active_workers)}"
        else:
            services["celery"] = False
            details["celery"] = "No active workers found"
            all_ready = False
    except Exception as e:
        services["celery"] = False
        details["celery"] = f"Worker check failed: {str(e)}"
        all_ready = False
        logger.error(f"Celery health check failed: {e}")
    
    return ReadinessResponse(
        ready=all_ready,
        timestamp=datetime.utcnow().isoformat(),
        services=services,
        details=details
    )


@router.get("/liveness")
async def liveness_check():
    """
    Kubernetes liveness probe endpoint.
    Simple check to verify the service is responsive.
    """
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/startup")
async def startup_check(db: AsyncSession = Depends(get_db)):
    """
    Kubernetes startup probe endpoint.
    Verifies the service has completed initialization.
    """
    try:
        # Check if database is accessible
        await db.execute(text("SELECT 1"))
        
        return {
            "started": True,
            "timestamp": datetime.utcnow().isoformat(),
            "database": "ready"
        }
        
    except Exception as e:
        logger.error(f"Startup check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Service not ready"
        )


@router.get("/metrics")
async def metrics():
    """
    Basic application metrics for monitoring.
    """
    try:
        metrics_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": 0,  # Would be calculated from app start time
            "requests_total": 0,  # Would be tracked by middleware
            "active_connections": 0,  # Would be tracked by WebSocket manager
            "memory_usage_mb": 0,  # Would use psutil to get actual memory
            "cpu_usage_percent": 0  # Would use psutil to get actual CPU
        }
        
        return metrics_data
        
    except Exception as e:
        logger.error(f"Metrics collection error: {e}")
        raise HTTPException(status_code=500, detail="Metrics collection failed")


@router.get("/version")
async def version_info():
    """
    Application version and build information.
    """
    return {
        "version": "1.0.0",
        "build_date": "2024-01-01",
        "git_commit": "production",
        "environment": "production",
        "python_version": "3.11",
        "dependencies": {
            "fastapi": "0.104.1",
            "sqlalchemy": "2.0.23",
            "redis": "5.0.0",
            "celery": "5.3.4"
        }
    }


@router.get("/database")
async def database_health(db: AsyncSession = Depends(get_db)):
    """
    Detailed database health check.
    """
    try:
        # Check connection
        start_time = datetime.utcnow()
        await db.execute(text("SELECT 1"))
        connection_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Check table existence
        tables_check = await db.execute(text("""
            SELECT count(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        table_count = tables_check.scalar()
        
        return {
            "status": "healthy",
            "connection_time_ms": round(connection_time, 2),
            "tables_count": table_count,
            "database_name": "lyo_app",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Database health check failed: {str(e)}"
        )


@router.get("/redis")
async def redis_health():
    """
    Detailed Redis health check.
    """
    try:
        redis_client = RedisPubSub()
        
        # Test ping
        start_time = datetime.utcnow()
        await redis_client.ping()
        ping_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Test set/get
        test_key = "health_check"
        test_value = "ok"
        await redis_client.set_cache(test_key, test_value, 5)  # 5 second expiry
        retrieved_value = await redis_client.get_cache(test_key)
        
        # Clean up
        await redis_client.delete_cache(test_key)
        await redis_client.close()
        
        return {
            "status": "healthy",
            "ping_time_ms": round(ping_time, 2),
            "cache_test": "passed" if retrieved_value == test_value else "failed",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Redis health check failed: {str(e)}"
        )
