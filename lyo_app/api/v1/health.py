"""
Health Check API endpoints for monitoring and status
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import time
import psutil

from lyo_app.core.database import get_db
from lyo_app.core.config import settings

router = APIRouter()

@router.get("/")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.app_version,
        "environment": settings.environment
    }

@router.get("/detailed")
async def detailed_health_check(db: Session = Depends(get_db)):
    """Detailed health check with system metrics"""
    start_time = time.time()
    
    # Test database connection
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
        db_response_time = time.time() - start_time
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        db_response_time = None
    
    # System metrics
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        system_metrics = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": (disk.used / disk.total) * 100,
            "memory_available_gb": memory.available / (1024**3),
            "disk_free_gb": disk.free / (1024**3)
        }
    except Exception:
        system_metrics = {"error": "Unable to fetch system metrics"}
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.app_version,
        "environment": settings.environment,
        "database": {
            "status": db_status,
            "response_time_ms": db_response_time * 1000 if db_response_time else None
        },
        "system": system_metrics,
        "uptime_seconds": time.time() - start_time
    }

@router.get("/readiness")
async def readiness_check(db: Session = Depends(get_db)):
    """Kubernetes-style readiness probe"""
    try:
        # Test critical dependencies
        db.execute("SELECT 1")
        
        return {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "not_ready",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.get("/liveness")
async def liveness_check():
    """Kubernetes-style liveness probe"""
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat()
    }
