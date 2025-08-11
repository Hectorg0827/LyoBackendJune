"""
Enhanced LyoBackend FastAPI Application
Production-ready AI-powered learning platform with 10/10 rating enhancements
"""

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Core configuration system
from lyo_app.core.config import settings
from lyo_app.core.database import close_db, init_db
from lyo_app.core.logging import setup_logging, logger
from lyo_app.core.exceptions import setup_error_handlers

# Enhanced monitoring and error handling (optional)
try:
    from lyo_app.core.enhanced_monitoring import (
        enhanced_error_handler, 
        performance_monitor, 
        ErrorCategory
    )
    ENHANCED_MONITORING_AVAILABLE = True
except ImportError:
    ENHANCED_MONITORING_AVAILABLE = False

# Optional integrations
try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

try:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Security middleware
from lyo_app.auth.security_middleware import (
    security_headers_middleware,
    request_size_middleware
)
from lyo_app.core.rate_limiter import rate_limit_middleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Enhanced application lifespan manager with comprehensive initialization
    """
    # Startup sequence
    logger.info("Starting LyoBackend with enhanced features...")
    
    # Initialize logging
    setup_logging()
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    # Initialize Sentry if configured and available
    if hasattr(settings, 'SENTRY_DSN') and settings.SENTRY_DSN and SENTRY_AVAILABLE:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            release=settings.APP_VERSION,
            traces_sample_rate=0.1 if settings.is_production() else 1.0
        )
        logger.info("Sentry monitoring initialized")
    
    # Initialize Redis if available
    try:
        from lyo_app.core.redis_client import init_redis
        await init_redis()
        logger.info("Redis cache initialized")
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e}")
    
    # Initialize enhanced storage system
    try:
        from lyo_app.storage.enhanced_storage import enhanced_storage
        await enhanced_storage._initialize_clients()
        logger.info("Enhanced storage system initialized")
    except Exception as e:
        logger.warning(f"Storage system initialization failed: {e}")
    
    # Initialize AI resilience system
    try:
        from lyo_app.core.ai_resilience import ai_resilience_manager
        await ai_resilience_manager.initialize()
        logger.info("AI resilience system initialized")
    except Exception as e:
        logger.warning(f"AI system initialization failed: {e}")
    
    logger.info("LyoBackend startup completed successfully")
    
    yield
    
    # Shutdown sequence
    logger.info("Shutting down LyoBackend...")
    
    await close_db()
    
    # Close Redis
    try:
        from lyo_app.core.redis_client import close_redis
        await close_redis()
    except Exception:
        pass
    
    logger.info("LyoBackend shutdown completed")


async def enhanced_error_middleware(request: Request, call_next):
    """Enhanced error handling middleware"""
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        # Get user info if available
        user_id = None
        if hasattr(request.state, 'user'):
            user_id = request.state.user.id
        
        # Handle error with enhanced error handler
        return await enhanced_error_handler.handle_error(
            error=e,
            request=request,
            user_id=user_id
        )


async def performance_monitoring_middleware(request: Request, call_next):
    """Performance monitoring middleware"""
    start_time = time.time()
    
    # Track performance
    with performance_monitor.track_performance(
        endpoint=str(request.url.path),
        method=request.method,
        user_id=getattr(request.state, 'user', {}).get('id') if hasattr(request.state, 'user') else None
    ):
        response = await call_next(request)
    
    # Add performance headers
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


def create_app() -> FastAPI:
    """Create and configure the enhanced FastAPI application"""
    
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add security middleware using production-ready rate limiter
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        return await security_headers_middleware(request, call_next)
    
    # Add production rate limiting middleware  
    @app.middleware("http")
    async def add_rate_limiting(request: Request, call_next):
        return await rate_limit_middleware(request, call_next)
    
    @app.middleware("http")
    async def add_request_size_limit(request: Request, call_next):
        return await request_size_middleware(request, call_next)
    
    # Include routers
    from lyo_app.auth.routes import router as auth_router
    from lyo_app.auth.email_routes import router as email_router
    from lyo_app.learning.routes import router as learning_router
    from lyo_app.feeds.routes import router as feeds_router
    from lyo_app.community.routes import router as community_router
    from lyo_app.gamification.routes import router as gamification_router
    from lyo_app.admin.routes import router as admin_router
    from lyo_app.core.file_routes import router as file_router
    from lyo_app.core.health import router as health_router
    from lyo_app.ai_agents import ai_router  # AI agents router
    from lyo_app.resources.routes import router as resources_router  # Educational resources router
    from lyo_app.api.social import router as social_router  # Stories & Messenger router
    from lyo_app.ai_study.clean_routes import router as ai_study_router  # AI Study Mode router

    app.include_router(auth_router, prefix=f"{settings.api_prefix}/auth", tags=["auth"])
    app.include_router(email_router, tags=["email"])
    app.include_router(learning_router, prefix=f"{settings.api_prefix}/learning", tags=["learning"])
    app.include_router(feeds_router, prefix=f"{settings.api_prefix}/feeds", tags=["feeds"])
    app.include_router(community_router, prefix=f"{settings.api_prefix}/community", tags=["community"])
    app.include_router(gamification_router, prefix=f"{settings.api_prefix}/gamification", tags=["gamification"])
    app.include_router(admin_router, prefix=f"{settings.api_prefix}/admin", tags=["admin"])
    app.include_router(file_router, tags=["files"])
    app.include_router(health_router, tags=["health"])
    # Include AI agents API
    app.include_router(ai_router, prefix=f"{settings.api_prefix}/ai", tags=["ai"])
    # Include Educational Resources API
    app.include_router(resources_router, prefix=f"{settings.api_prefix}/resources", tags=["educational-resources"])
    # Include Stories & Messenger API
    app.include_router(social_router, prefix=f"{settings.api_prefix}", tags=["stories-messenger"])
    # Include AI Study Mode API
    app.include_router(ai_study_router, tags=["ai-study-mode"])

    # Setup error handlers
    setup_error_handlers(app)
    
    @app.get("/health")
    async def health_check():
        """Basic health check endpoint."""
        return {
            "status": "healthy", 
            "environment": settings.environment,
            "version": "1.0.0"
        }
    
    return app


# Create the app instance
app = create_app()

# Simple global root endpoint to confirm backend is running
@app.get("/", include_in_schema=False)
async def root_global():
    """Global root endpoint confirming service is up"""
    return {"message": "LyoApp backend is running. Visit /docs for API documentation."}

# Expose Prometheus metrics (temporarily disabled)
# @app.get("/metrics")
# def metrics() -> Response:
#     """Prometheus metrics endpoint"""
#     if not PROMETHEUS_AVAILABLE:
#         return Response("Prometheus client not available", status_code=503)
#     
#     data = generate_latest()
#     return Response(data, media_type=CONTENT_TYPE_LATEST)
