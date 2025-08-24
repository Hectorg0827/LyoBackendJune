"""Enhanced LyoBackend FastAPI Application v2 with async course generation."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from lyo_app.core.settings import settings
from lyo_app.core.problems import problem_details_handler
from lyo_app.core.database import init_db, close_db
from lyo_app.services.websocket_manager import websocket_manager

# Import API routers
from lyo_app.api.auth import router as auth_router
from lyo_app.api.learning import router as learning_router
from lyo_app.api.tasks import router as tasks_router

# Import health and monitoring endpoints
from lyo_app.api.health import router as health_router
from lyo_app.api.users import router as users_router
from lyo_app.api.feeds import router as feeds_router
from lyo_app.api.community import router as community_router
from lyo_app.api.gamification import router as gamification_router
from lyo_app.api.push import router as push_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle management.
    
    Handles startup and shutdown tasks including:
    - Database initialization
    - WebSocket manager setup
    - Background task scheduling
    - Model loading (if configured)
    - Cleanup on shutdown
    """
    # Startup
    logger.info("Starting LyoBackend v2 with enhanced async features...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Initialize WebSocket manager
        await websocket_manager.initialize()
        logger.info("WebSocket manager initialized")
        
        # Initialize model manager (lazy loading)
        try:
            from lyo_app.models.loading import model_manager
            # Don't load model at startup - it will be loaded on first use
            logger.info("Model manager ready for lazy loading")
        except Exception as e:
            logger.warning(f"Model manager initialization warning: {e}")
        
        # Initialize monitoring (optional)
        try:
            import sentry_sdk
            if settings.SENTRY_DSN:
                sentry_sdk.init(
                    dsn=settings.SENTRY_DSN,
                    traces_sample_rate=0.1 if settings.ENVIRONMENT == "production" else 1.0,
                    environment=settings.ENVIRONMENT
                )
                logger.info("Sentry monitoring initialized")
        except ImportError:
            logger.info("Sentry not available, continuing without error monitoring")
        
        logger.info("🚀 LyoBackend v2 startup complete!")
        
        yield
        
    finally:
        # Shutdown
        logger.info("Shutting down LyoBackend v2...")
        
        # Cleanup WebSocket manager
        await websocket_manager.shutdown()
        
        # Close database connections
        await close_db()
        
        logger.info("LyoBackend v2 shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    # Create FastAPI app with enhanced configuration
    app = FastAPI(
        title="LyoApp Backend API",
        version="2.0.0",
        description="""
        Enhanced LyoApp Backend with async course generation, WebSocket progress updates, 
        and comprehensive learning management features.
        
        ## Features
        
        * **JWT Authentication** - Secure authentication with access and refresh tokens
        * **Async Course Generation** - AI-powered course creation with real-time progress
        * **WebSocket Support** - Real-time updates for long-running tasks
        * **RFC 9457 Problem Details** - Standardized error responses
        * **Comprehensive Learning API** - Course management and progress tracking
        * **Community Features** - Social learning with feeds and gamification
        * **Push Notifications** - Mobile app integration with APNs/FCM
        * **Content Curation** - AI-powered content discovery and organization
        
        ## Authentication
        
        Most endpoints require authentication. Use the `/v1/auth/login` endpoint to obtain
        access tokens, then include them in the Authorization header:
        
        ```
        Authorization: Bearer <access_token>
        ```
        
        ## WebSocket Endpoints
        
        WebSocket endpoints are not documented in OpenAPI. See the README for details:
        
        * `GET /v1/tasks/ws/{task_id}` - Real-time task progress updates
        
        ## Rate Limiting
        
        API endpoints are rate-limited to prevent abuse. Limits vary by endpoint type.
        """,
        contact={
            "name": "LyoApp Support",
            "email": "support@lyoapp.com",
        },
        license_info={
            "name": "Proprietary",
        },
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
        docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
        redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.DEBUG else None,
        lifespan=lifespan
    )
    
    # Add middleware stack (order matters!)
    
    # Security headers
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]  # Configure for production
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
        expose_headers=["X-Request-ID"]
    )
    
    # Request size limiting
    @app.middleware("http")
    async def request_size_middleware(request: Request, call_next):
        """Limit request body size to prevent abuse."""
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.MAX_REQUEST_SIZE:
            from lyo_app.core.problems import ValidationProblem
            raise ValidationProblem(f"Request body too large. Maximum size: {settings.MAX_REQUEST_SIZE} bytes")
        
        response = await call_next(request)
        return response
    
    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        """Add unique request ID to all requests for tracking."""
        import uuid
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    
    # Compression middleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Add global exception handler for RFC 9457 Problem Details
    app.add_exception_handler(Exception, problem_details_handler)
    
    # Include API routers with v1 prefix
    v1_router = FastAPI()
    
    v1_router.include_router(auth_router, prefix="/auth", tags=["authentication"])
    v1_router.include_router(learning_router, prefix="/courses", tags=["learning"]) 
    v1_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
    v1_router.include_router(health_router, prefix="/health", tags=["health"])
    v1_router.include_router(users_router, prefix="/users", tags=["users"])
    v1_router.include_router(feeds_router, prefix="/feeds", tags=["feeds"])
    v1_router.include_router(community_router, prefix="/community", tags=["community"])
    v1_router.include_router(gamification_router, prefix="/gamification", tags=["gamification"])
    v1_router.include_router(push_router, prefix="/push", tags=["push"])
    
    app.mount(settings.API_V1_PREFIX, v1_router)
    
    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "LyoApp Backend API",
            "version": "2.0.0",
            "environment": settings.ENVIRONMENT,
            "api_docs": f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
            "features": [
                "async_course_generation",
                "websocket_progress",
                "jwt_authentication", 
                "rfc9457_errors",
                "ai_content_curation",
                "push_notifications",
                "gamification",
                "community_feeds"
            ],
            "status": "healthy"
        }
    
    # Health check endpoint (outside v1 for load balancers)
    @app.get("/health")
    async def health_check():
        """Simple health check for load balancers."""
        return {
            "status": "healthy",
            "timestamp": "2025-01-01T00:00:00Z",  # Will be replaced by actual timestamp
            "version": "2.0.0"
        }
    
    return app


# Create app instance
app = create_app()

# Export for WSGI servers
application = app

if __name__ == "__main__":
    import uvicorn
    
    # Development server configuration
    uvicorn.run(
        "lyo_app.enhanced_main_v2:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug",
        access_log=True,
        ws_ping_interval=30,
        ws_ping_timeout=30
    )
