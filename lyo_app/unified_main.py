"""
Unified Main Application Entry Point
----------------------------------
This is the main application entry point that uses all the improved components:
- Unified configuration management
- PostgreSQL in production
- Standardized error handling
- Consistent API response schema
- Plugin system for modularity
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import our improved configuration
from lyo_app.core.unified_config import settings
from lyo_app.core.unified_errors import setup_error_handlers
from lyo_app.core.database import init_db, close_db
from lyo_app.core.plugin_system import plugin_manager

# Import optimization systems
from lyo_app.core.performance_monitor import performance_monitor, get_performance_monitor
from lyo_app.core.cache import get_cache, initialize_caching, shutdown_caching
from lyo_app.core.database_optimizer import initialize_database_optimization, db_optimizer
from lyo_app.core.error_handler import error_handler, request_id_middleware, error_handling_middleware
from lyo_app.core.api_optimizer import initialize_api_optimization, api_optimizer

# Import Phase 3 systems
from lyo_app.core.distributed_tracing import (
    initialize_tracing,
    shutdown_tracing,
    integrate_tracing_with_monitoring,
    get_tracing_health_status
)
from lyo_app.core.ai_optimizer import OptimizationEngine

try:  # Sentry optional
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

try:  # Prometheus optional
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Configure logger
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application startup and shutdown lifecycle.
    
    Handles:
    - Database initialization
    - Redis connection
    - Plugin initialization
    - External service connections
    - Graceful shutdown
    """
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} ({settings.ENVIRONMENT})...")
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    # Initialize Sentry if available and configured
    if SENTRY_AVAILABLE and settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            release=settings.APP_VERSION,
            traces_sample_rate=0.1 if settings.is_production() else 1.0,
        )
        logger.info("Sentry monitoring initialized")
    
    # Initialize Redis
    try:
        from lyo_app.core.redis_client import init_redis

        await init_redis()
        logger.info("Redis cache initialized")
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e}")
    
    # Initialize storage
    try:
        from lyo_app.storage.enhanced_storage import enhanced_storage

        await enhanced_storage._initialize_clients()
        logger.info("Storage system initialized")
    except Exception as e:
        logger.warning(f"Storage system initialization failed: {e}")
    
    # Initialize AI services
    try:
        from lyo_app.core.ai_resilience import ai_resilience_manager

        await ai_resilience_manager.initialize()
        logger.info("AI resilience system initialized")
    except Exception as e:
        logger.warning(f"AI system initialization failed: {e}")
    
    # Initialize performance monitoring
    try:
        await performance_monitor.initialize_redis()
        await performance_monitor.start_monitoring()
        logger.info("Performance monitoring system initialized")
    except Exception as e:
        logger.warning(f"Performance monitoring initialization failed: {e}")
    
    # Initialize caching system
    try:
        await initialize_caching()
        logger.info("Caching system initialized")
    except Exception as e:
        logger.warning(f"Caching system initialization failed: {e}")
    
    # Initialize database optimization
    try:
        await initialize_database_optimization()
        logger.info("Database optimization system initialized")
    except Exception as e:
        logger.warning(f"Database optimization initialization failed: {e}")
    
    # Initialize API optimization
    try:
        initialize_api_optimization()
        logger.info("API optimization system initialized")
    except Exception as e:
        logger.warning(f"API optimization initialization failed: {e}")
    
    # Initialize distributed tracing (Phase 3.1)
    try:
        await initialize_tracing()
        await integrate_tracing_with_monitoring()
        logger.info("Distributed tracing system initialized")
    except Exception as e:
        logger.warning(f"Distributed tracing initialization failed: {e}")
    
    # Initialize AI optimization engine (Phase 3.2)
    ai_optimizer = None
    try:
        from lyo_app.core.distributed_tracing import DistributedTracingManager
        from lyo_app.core.cache import CacheManager

        tracing_manager = DistributedTracingManager()
        cache_manager = CacheManager()

        ai_optimizer = OptimizationEngine(
            tracing_manager=tracing_manager,
            performance_monitor=performance_monitor,
            cache_manager=cache_manager
        )

        # Start optimization loop
        asyncio.create_task(ai_optimizer.start_optimization_loop())
        logger.info("AI optimization engine initialized and started")
    except Exception as e:
        logger.warning(f"AI optimization engine initialization failed: {e}")
        ai_optimizer = None
    
    # Initialize plugins
    try:
        # Discover plugins
        discovered = await plugin_manager.discover_plugins("lyo_app.plugins")
        logger.info(f"Discovered {len(discovered)} plugins: {', '.join(discovered)}")
        
        # Initialize plugins
        plugin_results = await plugin_manager.initialize_all_plugins(app)
        initialized = len([success for success in plugin_results.values() if success])
        logger.info(f"Initialized {initialized}/{len(plugin_results)} plugins")
        
        # Start plugins
        started = await plugin_manager.start_all_plugins()
        active = len([success for success in started.values() if success])
        logger.info(f"Started {active}/{len(started)} plugins")
    except Exception as e:
        logger.exception(f"Plugin initialization failed: {e}")
    
    logger.info(f"{settings.APP_NAME} startup completed successfully")
    
    # Application runs here
    yield
    
    # Shutdown process
    logger.info(f"Shutting down {settings.APP_NAME}...")
    
    # Stop plugins
    try:
        stopped = await plugin_manager.stop_all_plugins()
        logger.info(f"Stopped {len([s for s in stopped.values() if s])}/{len(stopped)} plugins")
    except Exception as e:
        logger.exception(f"Error stopping plugins: {e}")
    
    # Close database connections
    await close_db()
    logger.info("Database connections closed")
    
    # Close Redis connections
    try:
        from lyo_app.core.redis_client import close_redis

        await close_redis()
        logger.info("Redis connections closed")
    except Exception:
        pass
    
    # Shutdown optimization systems
    try:
        await performance_monitor.stop_monitoring()
        await performance_monitor.close_redis()
        logger.info("Performance monitoring system shutdown")
    except Exception as e:
        logger.warning(f"Performance monitoring shutdown failed: {e}")
    
    try:
        await shutdown_caching()
        logger.info("Caching system shutdown")
    except Exception as e:
        logger.warning(f"Caching system shutdown failed: {e}")
    
    # Shutdown distributed tracing
    try:
        await shutdown_tracing()
        logger.info("Distributed tracing system shutdown")
    except Exception as e:
        logger.warning(f"Distributed tracing shutdown failed: {e}")
    
    # Shutdown AI optimization engine
    try:
        if ai_optimizer:
            await ai_optimizer.stop_optimization_loop()
            logger.info("AI optimization engine shutdown")
    except Exception as e:
        logger.warning(f"AI optimization engine shutdown failed: {e}")
    
    logger.info(f"{settings.APP_NAME} shutdown completed")


async def performance_monitoring_middleware(request: Request, call_next):
    """Middleware for performance monitoring."""
    start_time = time.time()
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log slow requests
        if process_time > 1.0:  # Threshold of 1 second
            logger.warning(f"Slow request: {request.method} {request.url.path} took {process_time:.4f}s")
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Request error: {request.method} {request.url.path} took {process_time:.4f}s - {str(e)}")
        raise
    

async def request_logging_middleware(request: Request, call_next):
    """Middleware for request logging."""
    logger.debug(f"Request: {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    logger.debug(f"Response: {request.method} {request.url.path} - {response.status_code}")
    return response


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url=None if settings.is_production() else "/docs",
        redoc_url=None if settings.is_production() else "/redoc",
    )
    
    # Add CORS middleware
    app.add_middleware(CORSMiddleware, **settings.get_cors_config())
    
    # Add performance monitoring middleware
    if settings.ENABLE_METRICS:
        app.middleware("http")(performance_monitoring_middleware)
    
    # Add request logging middleware (development only)
    if settings.is_development():
        app.middleware("http")(request_logging_middleware)
    
    # Add error handling middleware
    app.middleware("http")(error_handling_middleware)
    
    # Add request ID middleware
    app.middleware("http")(request_id_middleware)
    
    # Set up error handlers
    setup_error_handlers(
        app,
        debug_mode=settings.DEBUG,
        environment=str(settings.ENVIRONMENT),
    )
    
    # Include routers
    # Core routers
    from lyo_app.auth.routes import router as auth_router
    app.include_router(auth_router)
    
    # Try to include optional routers
    try:
        from lyo_app.ai_study.clean_routes import router as ai_study_router
        app.include_router(ai_study_router)
    except ImportError as e:
        logger.warning(f"AI Study routes not available: {e}")
    
    try:
        from lyo_app.feeds.enhanced_routes import router as feeds_router
        app.include_router(feeds_router)
    except ImportError as e:
        logger.warning(f"Feeds routes not available: {e}")
    
    try:
        from lyo_app.storage.enhanced_routes import router as storage_router
        app.include_router(storage_router)
    except ImportError as e:
        logger.warning(f"Storage routes not available: {e}")
    
    try:
        from lyo_app.community.routes import router as community_router
        app.include_router(community_router)
    except ImportError:
        pass
    
    try:
        from lyo_app.gamification.routes import router as gamification_router
        app.include_router(gamification_router)
    except ImportError:
        pass
    
    try:
        from lyo_app.learning.routes import router as learning_router
        app.include_router(learning_router)
    except ImportError:
        pass
    
    # Add health check endpoint
    @app.get("/health")
    async def health_check():
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "features": settings.get_feature_flags(),
            "services": {},
        }
        
        # Database health check
        try:
            from lyo_app.core.database import check_db_health
            db_health = await check_db_health()
            health_status["services"]["database"] = db_health
        except Exception as e:
            health_status["services"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        # Redis health check
        try:
            from lyo_app.core.redis_client import redis_client
            if redis_client:
                await redis_client.ping()
                health_status["services"]["redis"] = {"status": "healthy"}
            else:
                health_status["services"]["redis"] = {"status": "not_configured"}
        except Exception as e:
            health_status["services"]["redis"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # AI service health check
        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            health_status["services"]["ai"] = await ai_resilience_manager.get_health_status()
        except Exception as e:
            health_status["services"]["ai"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Plugin system health check
        try:
            plugins_info = plugin_manager.get_all_plugin_info()
            health_status["services"]["plugins"] = {
                "status": "healthy",
                "total": len(plugins_info),
                "active": len([p for p in plugins_info.values() if p["state"] == "active"]),
                "error": len([p for p in plugins_info.values() if p["state"] == "error"]),
                "plugins": plugins_info
            }
        except Exception as e:
            health_status["services"]["plugins"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        return health_status
    
    # Add metrics endpoint
    if PROMETHEUS_AVAILABLE and settings.ENABLE_METRICS:
        @app.get("/metrics")
        async def metrics():
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    
    # Add optimization health check endpoints
    @app.get("/health/optimization")
    async def optimization_health():
        """Comprehensive optimization systems health check"""
        health_data = {
            "timestamp": time.time(),
            "systems": {}
        }
        
        # Performance monitoring health
        try:
            perf_stats = get_performance_monitor().get_current_metrics()
            health_data["systems"]["performance_monitoring"] = {
                "status": "healthy",
                "uptime_seconds": perf_stats.get("uptime_seconds", 0),
                "avg_response_time": perf_stats.get("application", {}).get("avg_response_time", 0)
            }
        except Exception as e:
            health_data["systems"]["performance_monitoring"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Caching system health
        try:
            cache_stats = get_cache().get_stats()
            health_data["systems"]["caching"] = {
                "status": "healthy",
                "cache_stats": cache_stats
            }
        except Exception as e:
            health_data["systems"]["caching"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Database optimization health
        try:
            db_analysis = await db_optimizer.analyze_query_performance()
            health_data["systems"]["database_optimization"] = {
                "status": "healthy",
                "analysis_time": db_analysis.get("analysis_time", 0),
                "slow_queries_count": len(db_analysis.get("slow_queries", []))
            }
        except Exception as e:
            health_data["systems"]["database_optimization"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Error handling health
        try:
            error_stats = error_handler.get_error_statistics()
            health_data["systems"]["error_handling"] = {
                "status": "healthy",
                "total_errors": error_stats.get("total_errors", 0),
                "unique_error_types": error_stats.get("unique_error_types", 0)
            }
        except Exception as e:
            health_data["systems"]["error_handling"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # API optimization health
        try:
            api_health = await api_optimizer.get_api_optimization_health()
            health_data["systems"]["api_optimization"] = api_health
        except Exception as e:
            health_data["systems"]["api_optimization"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Distributed tracing health (Phase 3.1)
        try:
            tracing_health = await get_tracing_health_status()
            health_data["systems"]["distributed_tracing"] = tracing_health
        except Exception as e:
            health_data["systems"]["distributed_tracing"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # AI optimization engine health (Phase 3.2)
        try:
            if ai_optimizer:
                optimizer_stats = ai_optimizer.get_optimization_stats()
                health_data["systems"]["ai_optimization"] = {
                    "status": "healthy",
                    "stats": optimizer_stats,
                    "is_running": ai_optimizer.is_running
                }
            else:
                health_data["systems"]["ai_optimization"] = {
                    "status": "not_initialized"
                }
        except Exception as e:
            health_data["systems"]["ai_optimization"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Overall status
        unhealthy_systems = [
            system for system in health_data["systems"].values()
            if system.get("status") == "unhealthy"
        ]
        
        health_data["overall_status"] = "healthy" if not unhealthy_systems else "degraded"
        health_data["unhealthy_systems_count"] = len(unhealthy_systems)
        
        return health_data
    
    # Add root endpoint
    @app.get("/")
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "description": settings.APP_DESCRIPTION,
            "environment": settings.ENVIRONMENT,
            "status": "operational",
            "documentation": {
                "swagger_ui": "/docs" if not settings.is_production() else "disabled_in_production",
                "redoc": "/redoc" if not settings.is_production() else "disabled_in_production",
            },
            "endpoints": {
                "health": "/health",
                "metrics": "/metrics" if settings.ENABLE_METRICS else "disabled",
                "auth": "/api/v1/auth",
                "ai_study": "/api/v1/ai-study",
                "feeds": "/api/v1/feeds",
                "storage": "/api/v1/storage",
            },
            "features": settings.get_feature_flags(),
            "timestamp": time.time(),
        }
    
    # Set app state start time
    app.state.start_time = time.time()
    
    logger.info(f"FastAPI application created: {settings.APP_NAME} v{settings.APP_VERSION}")
    return app


# Create the FastAPI application
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", settings.PORT))
    
    uvicorn.run(
        "lyo_app.unified_main:app",
        host=settings.HOST,
        port=port,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        reload=settings.is_development(),
    )
