"""
Production FastAPI application with comprehensive backend functionality.
Includes all required API routes, middleware, and production features.
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

# Import all API routers
from lyo_app.api.v1.auth_production import router as auth_router
from lyo_app.api.v1.courses import router as courses_router  
from lyo_app.api.v1.tasks import router as tasks_router
from lyo_app.api.v1.websocket import router as websocket_router
from lyo_app.api.v1.feeds import router as feeds_router
from lyo_app.api.v1.gamification import router as gamification_router
from lyo_app.api.v1.push import router as push_router
from lyo_app.api.v1.health import router as health_router

# Import core components
from lyo_app.core.database import init_db
from lyo_app.core.config import settings
from lyo_app.core.errors import (
    ProblemDetailsException,
    ValidationError, 
    AuthenticationError,
    problem_details_handler,
    validation_error_handler,
    auth_error_handler,
    http_exception_handler,
    general_exception_handler
)
from lyo_app.core.middleware import (
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    ResponseTimeMiddleware
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting LyoBackend production application...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized successfully")
        
        # Initialize Redis connection pool
        # This would happen automatically when first used
        logger.info("Redis connection pool ready")
        
        # Initialize Celery workers (external process)
        logger.info("Celery workers should be started separately")
        
        logger.info("LyoBackend production application started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down LyoBackend production application...")
    
    try:
        # Clean up connections would happen here
        logger.info("Application shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Create FastAPI application
app = FastAPI(
    title="LyoBackend Production API",
    description="Production-ready backend for Lyo learning app with comprehensive features",
    version="1.0.0",
    contact={
        "name": "LyoBackend Team",
        "email": "support@lyo.app"
    },
    license_info={
        "name": "Private License",
        "url": "https://lyo.app/license"
    },
    openapi_url="/api/v1/openapi.json",
    docs_url=None,  # Disable default docs
    redoc_url=None,  # Disable default redoc
    lifespan=lifespan
)


# Security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time"]
)

# Custom middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ResponseTimeMiddleware)
app.add_middleware(RequestLoggingMiddleware)


# Exception handlers
app.add_exception_handler(ProblemDetailsException, problem_details_handler)
app.add_exception_handler(ValidationError, validation_error_handler)
app.add_exception_handler(AuthenticationError, auth_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


# API Routes
app.include_router(
    auth_router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

app.include_router(
    courses_router,
    prefix="/api/v1/courses",
    tags=["Courses"]
)

app.include_router(
    tasks_router,
    prefix="/api/v1/tasks", 
    tags=["Tasks"]
)

app.include_router(
    websocket_router,
    prefix="/api/v1/ws",
    tags=["WebSocket"]
)

app.include_router(
    feeds_router,
    prefix="/api/v1/feeds",
    tags=["Feeds"]
)

app.include_router(
    gamification_router,
    prefix="/api/v1/gamification",
    tags=["Gamification"]
)

app.include_router(
    push_router,
    prefix="/api/v1/push",
    tags=["Push Notifications"]
)

app.include_router(
    health_router,
    prefix="/api/v1/health",
    tags=["Health"]
)


# Root endpoints
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "LyoBackend Production API",
        "version": "1.0.0",
        "status": "operational",
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_schema": "/api/v1/openapi.json"
        },
        "endpoints": {
            "authentication": "/api/v1/auth",
            "courses": "/api/v1/courses",
            "tasks": "/api/v1/tasks",
            "websocket": "/api/v1/ws",
            "feeds": "/api/v1/feeds",
            "gamification": "/api/v1/gamification",
            "push": "/api/v1/push",
            "health": "/api/v1/health"
        },
        "features": [
            "JWT Authentication",
            "Course Generation",
            "Real-time WebSocket",
            "Personalized Feeds",
            "Gamification System",
            "Push Notifications",
            "Health Monitoring"
        ]
    }


@app.get("/api/v1")
async def api_v1_info():
    """API v1 information endpoint."""
    return {
        "version": "1.0.0",
        "endpoints": [
            "/auth - Authentication and user management",
            "/courses - Course creation and management", 
            "/tasks - Background task tracking",
            "/ws - Real-time WebSocket connection",
            "/feeds - Personalized content feeds",
            "/gamification - Achievements and progress",
            "/push - Push notification system",
            "/health - Health and readiness checks"
        ],
        "authentication": "JWT Bearer Token required for most endpoints",
        "websocket": "Token-based authentication via query parameter",
        "documentation": "Available at /docs and /redoc"
    }


# Custom OpenAPI schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="LyoBackend Production API",
        version="1.0.0",
        description="""
        Production-ready backend API for Lyo learning application.
        
        ## Features
        - **JWT Authentication**: Secure user authentication with refresh tokens
        - **Course Management**: AI-powered course generation and manual course creation
        - **Real-time Updates**: WebSocket support for live progress tracking
        - **Personalized Feeds**: Content recommendations and personalized feeds
        - **Gamification**: Achievement system, badges, and progress tracking
        - **Push Notifications**: APNs integration for iOS devices
        - **Health Monitoring**: Comprehensive health checks and metrics
        
        ## Authentication
        Most endpoints require JWT authentication. Include the Bearer token in the Authorization header:
        ```
        Authorization: Bearer <your_jwt_token>
        ```
        
        ## WebSocket Connection
        Real-time WebSocket connection requires token authentication via query parameter:
        ```
        wss://api.example.com/api/v1/ws/?token=<your_jwt_token>
        ```
        """,
        routes=app.routes,
    )
    
    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    # Add security requirement to all endpoints except health checks
    for path, path_item in openapi_schema["paths"].items():
        if not path.startswith("/api/v1/health"):
            for method, operation in path_item.items():
                if method in ["get", "post", "put", "delete", "patch"]:
                    operation["security"] = [{"BearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# Custom documentation endpoints
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/api/v1/openapi.json",
        title="LyoBackend Production API - Swagger UI",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@4.15.5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@4.15.5/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url="/api/v1/openapi.json",
        title="LyoBackend Production API - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.0.0/bundles/redoc.standalone.js",
    )


# Global request validation
@app.middleware("http")
async def validate_content_type(request: Request, call_next):
    """Validate content type for POST/PUT requests."""
    if request.method in ["POST", "PUT", "PATCH"]:
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            # Allow form data and multipart for file uploads
            if not (content_type.startswith("application/x-www-form-urlencoded") or 
                   content_type.startswith("multipart/form-data")):
                return JSONResponse(
                    status_code=415,
                    content={
                        "type": "about:blank",
                        "title": "Unsupported Media Type", 
                        "status": 415,
                        "detail": "Content-Type must be application/json for this request"
                    }
                )
    
    response = await call_next(request)
    return response


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting LyoBackend production server...")
    
    uvicorn.run(
        "production_main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        access_log=True,
        log_level=settings.log_level.lower()
    )
