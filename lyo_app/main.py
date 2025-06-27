"""
Main FastAPI application entry point.
Configures the application, middleware, and routes with enhanced security.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from lyo_app.core.config import settings
from lyo_app.core.database import close_db, init_db
from lyo_app.core.logging import setup_logging
from lyo_app.core.exceptions import setup_error_handlers
from lyo_app.auth.security_middleware import (
    rate_limit_middleware,
    security_headers_middleware,
    request_size_middleware
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    setup_logging()
    await init_db()
    
    # Initialize Redis if available
    try:
        from lyo_app.core.redis_client import init_redis
        await init_redis()
    except Exception as e:
        print(f"Redis initialization failed: {e}")
    
    yield
    
    # Shutdown
    await close_db()
    
    # Close Redis
    try:
        from lyo_app.core.redis_client import close_redis
        await close_redis()
    except Exception:
        pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="LyoApp Backend",
        description="A Scalable, Offline-First Modular Monolith for AI-driven EdTech",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add security middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        return await security_headers_middleware(request, call_next)
    
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
    
    app.include_router(auth_router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"])
    app.include_router(email_router, tags=["email"])
    app.include_router(learning_router, prefix=f"{settings.api_v1_prefix}/learning", tags=["learning"])
    app.include_router(feeds_router, prefix=f"{settings.api_v1_prefix}/feeds", tags=["feeds"])
    app.include_router(community_router, prefix=f"{settings.api_v1_prefix}/community", tags=["community"])
    app.include_router(gamification_router, prefix=f"{settings.api_v1_prefix}/gamification", tags=["gamification"])
    app.include_router(admin_router, prefix=f"{settings.api_v1_prefix}/admin", tags=["admin"])
    app.include_router(file_router, tags=["files"])
    app.include_router(health_router, tags=["health"])
    
    # Setup error handlers
    setup_error_handlers(app)
    
    @app.get("/")
    async def root():
        """Root endpoint for health check."""
        return {
            "message": "LyoApp Backend API",
            "version": "1.0.0",
            "environment": settings.environment,
            "docs": "/docs",
            "health": "/health"
        }
    
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
