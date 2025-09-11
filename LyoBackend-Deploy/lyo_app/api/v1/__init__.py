"""
Production API v1 package initialization.
Includes all required routes per the backend specification.
"""

from fastapi import APIRouter

# Import all routers
from .auth import router as auth_router
from .courses import router as courses_router
from .tasks import router as tasks_router
from .websocket import router as websocket_router
from .feeds import router as feeds_router
from .gamification import router as gamification_router
from .push import router as push_router
from .health import router as health_router

# Create main v1 router
api_router = APIRouter()

# Include all sub-routers with proper prefixes
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(courses_router, prefix="/courses", tags=["Courses"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(websocket_router, prefix="/ws", tags=["WebSocket"])
api_router.include_router(feeds_router, prefix="/feeds", tags=["Feeds"])
api_router.include_router(gamification_router, prefix="/gamification", tags=["Gamification"])
api_router.include_router(push_router, prefix="/push", tags=["Push Notifications"])
api_router.include_router(health_router, prefix="/health", tags=["Health Check"])

__all__ = ["api_router"]
