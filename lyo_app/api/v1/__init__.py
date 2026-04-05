"""
Production API v1 package initialization.
Includes all required routes per the backend specification.
Uses resilient imports to prevent model failures from blocking working endpoints.
"""

import logging
import traceback
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Create main v1 router
api_router = APIRouter()

# ── Lyo 2.0 Router — layered A/B/C architecture ──────────────────────────────
# Both routers are wrapped individually so a failure in one doesn't block the other.
# If imports fail (e.g. AI module not available on Cloud Run cold-start), we register
# STUB routes that return HTTP 503 so iOS shows a retry-able error instead of 404.

_lyo2_chat_loaded = False
_lyo2_stream_loaded = False

try:
    from .chat_lyo2 import router as chat_lyo2_router
    api_router.include_router(chat_lyo2_router, prefix="/lyo2", tags=["Lyo 2.0"])
    _lyo2_chat_loaded = True
    logger.info("✅ Lyo 2.0 Chat router loaded")
except Exception as e:
    logger.error(
        f"❌ Failed to load Lyo 2.0 Chat router — stub registered.\n"
        f"   Error: {e}\n"
        f"   {traceback.format_exc()}"
    )

try:
    from .stream_lyo2 import router as stream_lyo2_router
    api_router.include_router(stream_lyo2_router, prefix="/lyo2", tags=["Lyo 2.0 Streaming"])
    _lyo2_stream_loaded = True
    logger.info("✅ Lyo 2.0 Streaming router loaded")
except Exception as e:
    logger.error(
        f"❌ Failed to load Lyo 2.0 Streaming router — stub registered.\n"
        f"   Error: {e}\n"
        f"   {traceback.format_exc()}"
    )

# Register stub routes for any Lyo 2.0 endpoints that failed to load
# This prevents 404 errors and gives iOS a 503 it can handle gracefully.
if not _lyo2_stream_loaded or not _lyo2_chat_loaded:
    _stub_router = APIRouter(prefix="/lyo2", tags=["Lyo 2.0 Stub"])

    if not _lyo2_stream_loaded:
        @_stub_router.post("/chat/stream")
        async def lyo2_stream_stub(request: Request):
            logger.warning("⚠️  lyo2/chat/stream stub hit — real router failed to load at boot")
            return JSONResponse(
                status_code=503,
                content={
                    "error": "service_unavailable",
                    "message": "AI streaming service is starting up. Please retry in a moment.",
                    "retry_after": 5,
                },
                headers={"Retry-After": "5"},
            )

    if not _lyo2_chat_loaded:
        @_stub_router.post("/chat")
        async def lyo2_chat_stub(request: Request):
            logger.warning("⚠️  lyo2/chat stub hit — real router failed to load at boot")
            return JSONResponse(
                status_code=503,
                content={
                    "error": "service_unavailable",
                    "message": "AI chat service is starting up. Please retry in a moment.",
                    "retry_after": 5,
                },
                headers={"Retry-After": "5"},
            )

        @_stub_router.post("/legacy")
        async def lyo2_legacy_stub(request: Request):
            logger.warning("⚠️  lyo2/legacy stub hit — real router failed to load at boot")
            return JSONResponse(
                status_code=503,
                content={
                    "error": "service_unavailable",
                    "message": "AI chat service is starting up. Please retry in a moment.",
                    "retry_after": 5,
                },
                headers={"Retry-After": "5"},
            )

    api_router.include_router(_stub_router)

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

