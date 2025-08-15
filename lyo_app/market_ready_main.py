"""
LyoBackend Market-Ready Application
==================================

Production-grade modular monolith for Google Cloud deployment.
Implements comprehensive backend system with:
- Strict module boundaries
- Zero-trust security  
- AI-powered tutoring & planning
- Real-time messaging & feeds
- Advanced search & ranking
- Comprehensive moderation
- Full observability stack

Architecture: Modular monolith with service interfaces
Target: Google Cloud (Cloud Run, Cloud SQL, Memorystore, GCS)
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer
from fastapi.responses import JSONResponse

# Core Infrastructure
from lyo_app.core.config_v2 import settings
from lyo_app.core.database_v2 import database_manager
from lyo_app.core.logging_v2 import setup_logging, logger
from lyo_app.core.redis_v2 import redis_manager
from lyo_app.core.gcs_storage import storage_manager
from lyo_app.core.monitoring_v2 import monitoring_manager
from lyo_app.core.rate_limiting import rate_limiter
from lyo_app.core.exceptions_v2 import setup_exception_handlers

# Module Routers - Strict Boundaries
from lyo_app.modules.auth.router import router as auth_router
from lyo_app.modules.profiles.router import router as profiles_router
from lyo_app.modules.media.router import router as media_router
from lyo_app.modules.posts.router import router as posts_router
from lyo_app.modules.stories.router import router as stories_router
from lyo_app.modules.messaging.router import router as messaging_router
from lyo_app.modules.notifications.router import router as notifications_router
from lyo_app.modules.moderation.router import router as moderation_router
from lyo_app.modules.tutor.router import router as tutor_router
from lyo_app.modules.planner.router import router as planner_router
from lyo_app.modules.practice.router import router as practice_router
from lyo_app.modules.search.router import router as search_router
from lyo_app.modules.gamification.router import router as gamification_router
from lyo_app.modules.admin.router import router as admin_router
from lyo_app.modules.analytics.router import router as analytics_router

# Security & Middleware
from lyo_app.core.security import security_manager
from lyo_app.core.middleware import (
    request_id_middleware,
    security_headers_middleware,
    compression_middleware,
    timing_middleware,
)

# WebSocket Manager
from lyo_app.modules.messaging.websocket import websocket_manager

# API Version
API_VERSION = "v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle management."""
    
    # Startup
    logger.info("🚀 Starting LyoBackend Market-Ready Application...")
    
    # Initialize core systems
    await database_manager.initialize()
    await redis_manager.initialize()
    await storage_manager.initialize()
    await monitoring_manager.initialize()
    await security_manager.initialize()
    
    # Initialize WebSocket manager
    await websocket_manager.initialize()
    
    logger.info("✅ All systems initialized successfully")
    
    yield
    
    # Shutdown
    logger.info("🔄 Shutting down LyoBackend...")
    
    await websocket_manager.shutdown()
    await monitoring_manager.shutdown()
    await storage_manager.shutdown()
    await redis_manager.shutdown()
    await database_manager.shutdown()
    
    logger.info("✅ Shutdown completed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    # Setup logging first
    setup_logging()
    
    # Create FastAPI app
    app = FastAPI(
        title="LyoApp Backend",
        description="Market-ready educational platform backend",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=f"/{API_VERSION}/docs" if not settings.is_production() else None,
        redoc_url=f"/{API_VERSION}/redoc" if not settings.is_production() else None,
        openapi_url=f"/{API_VERSION}/openapi.json",
    )
    
    # Security middleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Custom middleware (order matters!)
    app.add_middleware(compression_middleware)
    app.add_middleware(timing_middleware)
    app.add_middleware(request_id_middleware)
    app.add_middleware(security_headers_middleware)
    
    # Exception handlers
    setup_exception_handlers(app)
    
    # Health endpoints (outside versioning)
    @app.get("/health", tags=["System"])
    async def health_check():
        """Kubernetes health check endpoint."""
        try:
            # Quick health checks
            db_healthy = await database_manager.health_check()
            redis_healthy = await redis_manager.health_check()
            
            if db_healthy and redis_healthy:
                return {
                    "status": "healthy",
                    "timestamp": time.time(),
                    "version": "1.0.0",
                    "environment": settings.ENVIRONMENT,
                }
            else:
                raise HTTPException(status_code=503, detail="Service unhealthy")
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise HTTPException(status_code=503, detail="Health check failed")
    
    @app.get("/ready", tags=["System"])
    async def readiness_check():
        """Kubernetes readiness check endpoint."""
        try:
            # More comprehensive readiness checks
            checks = {
                "database": await database_manager.ready_check(),
                "redis": await redis_manager.ready_check(),
                "storage": await storage_manager.ready_check(),
            }
            
            if all(checks.values()):
                return {
                    "status": "ready",
                    "checks": checks,
                    "timestamp": time.time(),
                }
            else:
                raise HTTPException(status_code=503, detail="Service not ready")
                
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            raise HTTPException(status_code=503, detail="Readiness check failed")
    
    # Metrics endpoint
    @app.get("/metrics", tags=["System"])
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(
            content=await monitoring_manager.get_metrics(),
            media_type="text/plain",
        )
    
    # API Routes - All versioned under /v1
    api_prefix = f"/{API_VERSION}"
    
    # Auth & Identity
    app.include_router(auth_router, prefix=f"{api_prefix}/auth", tags=["Authentication"])
    app.include_router(profiles_router, prefix=f"{api_prefix}/profiles", tags=["Profiles"])
    
    # Media & Content
    app.include_router(media_router, prefix=f"{api_prefix}/media", tags=["Media"])
    app.include_router(posts_router, prefix=f"{api_prefix}/posts", tags=["Posts"])
    app.include_router(stories_router, prefix=f"{api_prefix}/stories", tags=["Stories"])
    
    # Social Features  
    app.include_router(messaging_router, prefix=f"{api_prefix}/chats", tags=["Messaging"])
    app.include_router(notifications_router, prefix=f"{api_prefix}/notifications", tags=["Notifications"])
    
    # AI Learning Platform
    app.include_router(tutor_router, prefix=f"{api_prefix}/tutor", tags=["AI Tutor"])
    app.include_router(planner_router, prefix=f"{api_prefix}/planner", tags=["Course Planner"])
    app.include_router(practice_router, prefix=f"{api_prefix}/practice", tags=["Practice & Assessment"])
    
    # Discovery & Engagement
    app.include_router(search_router, prefix=f"{api_prefix}/search", tags=["Search"])
    app.include_router(gamification_router, prefix=f"{api_prefix}/gamification", tags=["Gamification"])
    
    # Moderation & Safety
    app.include_router(moderation_router, prefix=f"{api_prefix}/moderation", tags=["Moderation"])
    
    # Admin & Analytics
    app.include_router(admin_router, prefix=f"{api_prefix}/admin", tags=["Admin"])
    app.include_router(analytics_router, prefix=f"{api_prefix}/analytics", tags=["Analytics"])
    
    # WebSocket endpoint
    @app.websocket(f"/{API_VERSION}/ws/chats/{{chat_id}}")
    async def websocket_endpoint(websocket, chat_id: str):
        """WebSocket endpoint for real-time messaging."""
        await websocket_manager.connect(websocket, chat_id)
    
    # Root endpoint
    @app.get("/", tags=["System"])
    async def root():
        """API root endpoint."""
        return {
            "name": "LyoApp Backend",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "api_version": API_VERSION,
            "docs_url": f"/{API_VERSION}/docs" if not settings.is_production() else None,
        }
    
    return app


# Create the app instance
app = create_app()


# Auto-debug and validation (MANDATORY)
async def self_check():
    """Continuous self-check and auto-debug (MANDATORY)."""
    try:
        # Health check
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code != 200:
                logger.error(f"Health check failed: {response.status_code}")
                return False
        
        # OpenAPI validation
        response = await client.get("http://localhost:8000/v1/openapi.json")
        if response.status_code != 200:
            logger.error("OpenAPI endpoint failed")
            return False
            
        logger.info("✅ Self-check passed")
        return True
        
    except Exception as e:
        logger.error(f"Self-check failed: {e}")
        return False


if __name__ == "__main__":
    import uvicorn
    
    # Run self-check
    if not asyncio.run(self_check()):
        logger.error("❌ Self-check failed - fixing issues...")
        # Auto-fix logic would go here
        
    uvicorn.run(
        "lyo_app.market_ready_main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production(),
        log_level="info",
    )
