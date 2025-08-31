"""Enhanced LyoBackend FastAPI Application.

Cloud Run compatible FastAPI application with comprehensive health checks,
proper port configuration, and production-ready features.
"""

import os
import time
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any

# Set up basic logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Try imports with graceful fallbacks
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    logger.warning("FastAPI not available, creating placeholder")
    FASTAPI_AVAILABLE = False
    
    # Create placeholder classes for structure
    class FastAPI:
        def __init__(self, **kwargs):
            self.state = type('State', (), {'start_time': time.time()})()
            logger.info("Placeholder FastAPI app created")
        
        def get(self, path):
            def decorator(func):
                return func
            return decorator
        
        def add_middleware(self, middleware_class, **kwargs):
            pass
            
        def include_router(self, router):
            pass
    
    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)
    
    class CORSMiddleware:
        pass
    
    class JSONResponse(dict):
        pass

# Basic settings class with fallbacks
class BasicSettings:
    """Minimal settings for Cloud Run deployment"""
    APP_NAME = os.getenv("APP_NAME", "LyoBackend")
    APP_DESCRIPTION = os.getenv("APP_DESCRIPTION", "LyoBackend AI-Powered Learning Platform")
    APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    PORT = int(os.getenv("PORT", 8080))
    HOST = os.getenv("HOST", "0.0.0.0")
    
    def is_production(self):
        return self.ENVIRONMENT == "production"
    
    def is_development(self):
        return self.ENVIRONMENT == "development"
    
    def get_cors_config(self):
        return {
            'allow_origins': ["*"],
            'allow_credentials': True,
            'allow_methods': ["*"],
            'allow_headers': ["*"],
        }

# Try to import real settings, fallback to basic
try:
    from lyo_app.core.enhanced_config import settings
    logger.info("Using enhanced_config")
except ImportError:
    try:
        from lyo_app.core.unified_config import settings
        logger.info("Using unified_config")
    except ImportError:
        try:
            from lyo_app.core.config import settings
            logger.info("Using basic config")
        except ImportError:
            settings = BasicSettings()
            logger.info("Using fallback BasicSettings")

# Optional imports with fallbacks
try:
    from lyo_app.core.database import init_db, close_db
except ImportError:
    init_db = None
    close_db = None

try:
    from lyo_app.core.unified_errors import setup_error_handlers
except ImportError:
    def setup_error_handlers(app, **kwargs):
        logger.info("Error handlers not available, using defaults")

try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup & shutdown lifecycle - optimized for Cloud Run."""
    logger.info("Starting LyoBackend enhanced application...")
    
    # Fast startup mode for Cloud Run - minimal initialization
    fast_startup = os.getenv("FAST_STARTUP", "true").lower() == "true"
    
    if fast_startup:
        logger.info("Fast startup mode enabled - minimal initialization")
        # Set start time immediately
        app.state.start_time = time.time()
        
        # Only do critical initialization
        logger.info("Enhanced application startup completed (fast mode)")
        yield
        logger.info("Enhanced application shutdown completed (fast mode)")
        return
    
    # Full initialization mode
    logger.info("Full initialization mode")
    
    # Initialize database if available
    if init_db:
        try:
            await init_db()
            logger.info("Database initialized")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")
    
    # Initialize Sentry if available
    if (hasattr(settings, 'SENTRY_DSN') and 
        getattr(settings, 'SENTRY_DSN', None) and 
        SENTRY_AVAILABLE):
        try:
            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                environment=getattr(settings, 'ENVIRONMENT', 'development'),
                release=getattr(settings, 'APP_VERSION', '1.0.0'),
                traces_sample_rate=0.1 if getattr(settings, 'is_production', lambda: False)() else 1.0,
            )
            logger.info("Sentry monitoring initialized")
        except Exception as e:
            logger.warning(f"Sentry initialization failed: {e}")
    
    logger.info("Enhanced application startup completed")
    
    # Application runs here
    yield
    
    # Shutdown
    logger.info("Shutting down enhanced application...")
    
    if close_db:
        try:
            await close_db()
            logger.info("Database connections closed")
        except Exception as e:
            logger.warning(f"Database shutdown error: {e}")
    
    logger.info("Enhanced application shutdown completed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=getattr(settings, 'APP_NAME', 'LyoBackend'),
        description=getattr(settings, 'APP_DESCRIPTION', 'LyoBackend AI-Powered Learning Platform'),
        version=getattr(settings, 'APP_VERSION', '1.0.0'),
        debug=getattr(settings, 'DEBUG', False),
        lifespan=lifespan if FASTAPI_AVAILABLE else None,
        docs_url=None if getattr(settings, 'is_production', lambda: False)() else "/docs",
        redoc_url=None if getattr(settings, 'is_production', lambda: False)() else "/redoc",
    )
    
    # Add CORS middleware
    if FASTAPI_AVAILABLE:
        try:
            cors_config = getattr(settings, 'get_cors_config', lambda: {
                'allow_origins': ['*'],
                'allow_credentials': True,
                'allow_methods': ['*'],
                'allow_headers': ['*'],
            })()
            app.add_middleware(CORSMiddleware, **cors_config)
        except Exception as e:
            logger.warning(f"CORS configuration failed: {e}")
            # Fallback CORS configuration
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
    
    # Set up error handlers
    setup_error_handlers(app, debug_mode=getattr(settings, 'DEBUG', False))
    
    # Include routers with error handling - skip missing routers for Cloud Run compatibility
    router_modules = [
        ('lyo_app.auth.routes', 'auth_router'),
        ('lyo_app.ai_study.clean_routes', 'ai_study_router'),
        ('lyo_app.feeds.enhanced_routes', 'feeds_router'),
        ('lyo_app.storage.enhanced_routes', 'storage_router'),
        ('lyo_app.monetization.routes', 'ads_router'),
    ]
    
    included_routers = 0
    for module_path, router_name in router_modules:
        try:
            module = __import__(module_path, fromlist=[router_name])
            router = getattr(module, 'router', None)
            if router:
                app.include_router(router)
                logger.info(f"Included router from {module_path}")
                included_routers += 1
        except ImportError as e:
            logger.warning(f"Could not import router from {module_path}: {e}")
        except Exception as e:
            logger.error(f"Error including router from {module_path}: {e}")
    
    logger.info(f"Successfully included {included_routers}/{len(router_modules)} routers")
    
    # Health check endpoint - critical for Cloud Run
    @app.get("/health")
    async def health_check():
        """Basic health check endpoint for Cloud Run."""
        try:
            current_time = time.time()
            health_data = {
                "status": "healthy",
                "timestamp": current_time,
                "environment": getattr(settings, 'ENVIRONMENT', 'unknown'),
                "version": getattr(settings, 'APP_VERSION', '1.0.0'),
                "uptime_seconds": current_time - getattr(app.state, 'start_time', current_time),
                "port": os.getenv("PORT", "8080"),
                "host": os.getenv("HOST", "0.0.0.0"),
                "fastapi_available": FASTAPI_AVAILABLE
            }
            
            return health_data
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            if FASTAPI_AVAILABLE:
                raise HTTPException(status_code=503, detail="Service unhealthy")
            else:
                return {"status": "error", "error": str(e)}
    
    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "LyoBackend Enhanced API",
            "version": getattr(settings, 'APP_VERSION', '1.0.0'),
            "docs_url": "/docs" if not getattr(settings, 'is_production', lambda: False)() else None,
            "port": os.getenv("PORT", "8080"),
            "health_url": "/health"
        }
    
    # Additional endpoints for Cloud Run compatibility
    @app.get("/healthz")
    async def healthz():
        """Kubernetes-style health check."""
        return {"status": "ok", "port": os.getenv("PORT", "8080")}
    
    @app.get("/readiness")
    async def readiness():
        """Readiness check."""
        return {"status": "ready", "port": os.getenv("PORT", "8080")}
    
    # Add a simple test endpoint
    @app.get("/test")
    async def test_endpoint():
        """Simple test endpoint to verify the API is responding."""
        return {
            "message": "API is working",
            "timestamp": time.time(),
            "port": os.getenv("PORT", "8080")
        }
    
    # Set app state start time
    app.state.start_time = time.time()
    
    logger.info(f"FastAPI application created: {getattr(settings, 'APP_NAME', 'LyoBackend')} v{getattr(settings, 'APP_VERSION', '1.0.0')}")
    return app


# Create the FastAPI application instance for import
app = create_app()


if __name__ == "__main__":
    # Only run if being executed directly
    logger.info("Enhanced_main.py being executed directly")
    
    try:
        import uvicorn
        UVICORN_AVAILABLE = True
    except ImportError:
        UVICORN_AVAILABLE = False
    
    port = int(os.getenv("PORT", 8080))  # Default to 8080 for Cloud Run
    host = os.getenv("HOST", "0.0.0.0")
    environment = os.getenv("ENVIRONMENT", "production")
    
    logger.info(f"Configuration - Host: {host}, Port: {port}, Environment: {environment}")
    logger.info(f"FastAPI available: {FASTAPI_AVAILABLE}, Uvicorn available: {UVICORN_AVAILABLE}")
    
    if UVICORN_AVAILABLE:
        logger.info("Starting with uvicorn...")
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )
    else:
        logger.error("Uvicorn not available, cannot start server")
        logger.info("This module should be imported by gunicorn, not run directly")
        import sys
        sys.exit(1)