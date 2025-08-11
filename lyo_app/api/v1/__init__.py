"""
API v1 package initialization
"""

from fastapi import APIRouter

# Import all routers
from .auth import router as auth_router
from .learning import router as learning_router
from .ai_study import router as ai_study_router
from .health import router as health_router

# Create main v1 router
api_router = APIRouter()

# Include all sub-routers
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(learning_router, prefix="/learning", tags=["Learning"])
api_router.include_router(ai_study_router, prefix="/ai-study", tags=["AI Study Mode"])
api_router.include_router(health_router, prefix="/health", tags=["Health Check"])

__all__ = ["api_router"]
