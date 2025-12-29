"""
Production API v1 package initialization.
Includes all required routes per the backend specification.
Uses resilient imports to prevent model failures from blocking working endpoints.
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Create main v1 router
api_router = APIRouter()

# Import chat first - it has NO database dependencies
try:
    from .chat import router as chat_router
    api_router.include_router(chat_router, tags=["Chat"])
    logger.info("✅ Chat router loaded")
except Exception as e:
    logger.error(f"❌ Failed to load chat router: {e}")

# Import health router - minimal dependencies
try:
    from .health import router as health_router
    api_router.include_router(health_router, prefix="/health", tags=["Health Check"])
    logger.info("✅ Health router loaded")
except Exception as e:
    logger.error(f"❌ Failed to load health router: {e}")

# Import other routers with graceful error handling
# These may fail if there are database model conflicts

try:
    from .auth import router as auth_router
    api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
    logger.info("✅ Auth router loaded")
except Exception as e:
    logger.warning(f"⚠️ Auth router not loaded: {e}")

try:
    from .courses import router as courses_router
    api_router.include_router(courses_router, prefix="/courses", tags=["Courses"])
    logger.info("✅ Courses router loaded")
except Exception as e:
    logger.warning(f"⚠️ Courses router not loaded: {e}")

try:
    from .tasks import router as tasks_router
    api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
    logger.info("✅ Tasks router loaded")
except Exception as e:
    logger.warning(f"⚠️ Tasks router not loaded: {e}")

try:
    from .websocket import router as websocket_router
    api_router.include_router(websocket_router, prefix="/ws", tags=["WebSocket"])
    logger.info("✅ WebSocket router loaded")
except Exception as e:
    logger.warning(f"⚠️ WebSocket router not loaded: {e}")

try:
    from .feeds import router as feeds_router
    api_router.include_router(feeds_router, prefix="/feeds", tags=["Feeds"])
    logger.info("✅ Feeds router loaded")
except Exception as e:
    logger.warning(f"⚠️ Feeds router not loaded: {e}")

try:
    from .gamification import router as gamification_router
    api_router.include_router(gamification_router, prefix="/gamification", tags=["Gamification"])
    logger.info("✅ Gamification router loaded")
except Exception as e:
    logger.warning(f"⚠️ Gamification router not loaded: {e}")

try:
    from .push import router as push_router
    api_router.include_router(push_router, prefix="/push", tags=["Push Notifications"])
    logger.info("✅ Push router loaded")
except Exception as e:
    logger.warning(f"⚠️ Push router not loaded: {e}")

__all__ = ["api_router"]

