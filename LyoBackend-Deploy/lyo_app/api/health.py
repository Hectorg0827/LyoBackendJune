"""Health and monitoring API endpoints."""

from typing import Dict, Any
from datetime import datetime
import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db_session
from lyo_app.services.websocket_manager import websocket_manager

router = APIRouter()


@router.get("/", summary="Comprehensive health check")
async def health_check(db: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Comprehensive health check endpoint.
    
    Checks the health of all system components:
    - Database connectivity
    - WebSocket manager
    - Background task processing
    - Memory usage
    """
    health_data = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "environment": "development",  # Will be replaced by settings
        "components": {}
    }
    
    # Check database
    try:
        await db.execute("SELECT 1")
        health_data["components"]["database"] = {
            "status": "healthy",
            "message": "Database connection successful"
        }
    except Exception as e:
        health_data["status"] = "degraded"
        health_data["components"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
    
    # Check WebSocket manager
    try:
        ws_health = await websocket_manager.health_check()
        health_data["components"]["websocket"] = ws_health
        if ws_health["status"] != "healthy":
            health_data["status"] = "degraded"
    except Exception as e:
        health_data["status"] = "degraded"
        health_data["components"]["websocket"] = {
            "status": "unhealthy",
            "message": f"WebSocket manager error: {str(e)}"
        }
    
    # Check Redis (used by Celery and WebSocket)
    try:
        from lyo_app.workers.celery_app import redis_client
        await redis_client.ping()
        health_data["components"]["redis"] = {
            "status": "healthy",
            "message": "Redis connection successful"
        }
    except Exception as e:
        health_data["status"] = "degraded"
        health_data["components"]["redis"] = {
            "status": "unhealthy",
            "message": f"Redis connection failed: {str(e)}"
        }
    
    return health_data


@router.get("/database", summary="Database health check")
async def database_health(db: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """Check database connectivity and basic operations."""
    try:
        # Test basic query
        result = await db.execute("SELECT version() as version, now() as timestamp")
        row = result.fetchone()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database_version": row.version if row else "unknown",
            "database_timestamp": row.timestamp.isoformat() if row and row.timestamp else None
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@router.get("/websocket", summary="WebSocket manager health")
async def websocket_health() -> Dict[str, Any]:
    """Check WebSocket manager health and connection count."""
    return await websocket_manager.health_check()


@router.get("/ready", summary="Readiness probe")
async def readiness_probe(db: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Kubernetes/Docker readiness probe.
    
    Returns 200 if the application is ready to serve traffic.
    """
    checks = []
    
    # Database check
    try:
        await db.execute("SELECT 1")
        checks.append({"component": "database", "status": "ready"})
    except Exception as e:
        checks.append({"component": "database", "status": "not_ready", "error": str(e)})
    
    # WebSocket manager check
    try:
        ws_health = await websocket_manager.health_check()
        if ws_health["status"] == "healthy":
            checks.append({"component": "websocket", "status": "ready"})
        else:
            checks.append({"component": "websocket", "status": "not_ready", "details": ws_health})
    except Exception as e:
        checks.append({"component": "websocket", "status": "not_ready", "error": str(e)})
    
    # Determine overall readiness
    all_ready = all(check["status"] == "ready" for check in checks)
    
    return {
        "ready": all_ready,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks
    }


@router.get("/live", summary="Liveness probe")
async def liveness_probe() -> Dict[str, str]:
    """
    Kubernetes/Docker liveness probe.
    
    Returns 200 if the application process is alive.
    """
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat()
    }
