"""Enhanced LyoBackend FastAPI Application (clean restored version)."""

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:  # Config import (enhanced first)
    from lyo_app.core.enhanced_config import settings
except ImportError:  # Fallback
    from lyo_app.core.config import settings

from lyo_app.core.database import close_db, init_db
from lyo_app.core.logging import setup_logging, logger
from lyo_app.core.exceptions import setup_error_handlers
from lyo_app.core.enhanced_monitoring import (
    enhanced_error_handler,
    performance_monitor,
    ErrorCategory,  # noqa: F401 (kept for potential future use)
)

try:  # Sentry optional
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:  # pragma: no cover
    SENTRY_AVAILABLE = False

try:  # Prometheus optional
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    PROMETHEUS_AVAILABLE = False

from lyo_app.auth.security_middleware import (
    security_headers_middleware,
    request_size_middleware,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup & shutdown lifecycle."""
    logger.info("Starting LyoBackend with enhanced features...")
    setup_logging()
    await init_db()
    logger.info("Database initialized")
    if (
        hasattr(settings, "SENTRY_DSN")
        and getattr(settings, "SENTRY_DSN", None)
        and SENTRY_AVAILABLE
    ):
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            release=settings.APP_VERSION,
            traces_sample_rate=0.1 if settings.is_production() else 1.0,
        )
        logger.info("Sentry monitoring initialized")
    # Redis
    try:
        from lyo_app.core.redis_client import init_redis

        await init_redis()
        logger.info("Redis cache initialized")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Redis initialization failed: {e}")
    # Storage
    try:
        from lyo_app.storage.enhanced_storage import enhanced_storage

        await enhanced_storage._initialize_clients()
        logger.info("Enhanced storage system initialized")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Storage system initialization failed: {e}")
    # AI Resilience
    try:
        from lyo_app.core.ai_resilience import ai_resilience_manager

        await ai_resilience_manager.initialize()
        logger.info("AI resilience system initialized")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"AI system initialization failed: {e}")
    # Firebase optional
    try:
        from lyo_app.integrations.firebase_client import firebase_client

        logger.info(
            "Firebase client initialized (Firestore/Storage available)"
            if firebase_client.is_enabled()
            else "Firebase not enabled or credentials not present - continuing without it"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Firebase initialization failed: {e}")
    # Vertex AI optional
    try:
        from lyo_app.integrations.vertex_ai_client import vertex_ai_client

        logger.info(
            "Vertex AI client ready"
            if vertex_ai_client.is_enabled()
            else "Vertex AI not enabled (credentials or library missing) - continuing"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Vertex AI initialization skipped/failed: {e}")
    logger.info("LyoBackend startup completed successfully")
    yield
    logger.info("Shutting down LyoBackend...")
    await close_db()
    try:
        from lyo_app.core.redis_client import close_redis

        await close_redis()
    except Exception:  # noqa: BLE001
        pass
    logger.info("LyoBackend shutdown completed")


async def enhanced_error_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:  # noqa: BLE001
        user_id = getattr(getattr(request.state, "user", None), "id", None)
        return await enhanced_error_handler.handle_error(
            error=e, request=request, user_id=user_id
        )


async def performance_monitoring_middleware(request: Request, call_next):
    start_time = time.time()
    with performance_monitor.track_performance(
        endpoint=str(request.url.path),
        method=request.method,
        user_id=getattr(getattr(request.state, "user", {}), "id", None),
    ):
        response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.time() - start_time)
    return response


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url=None if settings.is_production() else "/docs",
        redoc_url=None if settings.is_production() else "/redoc",
    )
    # Middleware
    app.add_middleware(CORSMiddleware, **settings.get_cors_config())
    app.middleware("http")(performance_monitoring_middleware)
    app.middleware("http")(enhanced_error_middleware)
    app.middleware("http")(security_headers_middleware)
    app.middleware("http")(request_size_middleware)
    setup_error_handlers(app)
    # Routers
    from lyo_app.auth.routes import router as auth_router
    from lyo_app.ai_study.clean_routes import router as ai_study_router
    from lyo_app.feeds.enhanced_routes import router as feeds_router
    from lyo_app.storage.enhanced_routes import router as storage_router
    from lyo_app.monetization.routes import router as ads_router
    try:
        from lyo_app.api.v1 import api_router

        app.include_router(api_router, prefix="/api/v1")
        logger.info("✅ API v1 routes integrated - 10/10 backend achieved!")
    except ImportError as e:  # noqa: BLE001
        logger.warning(f"API v1 routes not available: {e}")
    app.include_router(auth_router)
    app.include_router(ai_study_router)
    app.include_router(feeds_router)
    app.include_router(storage_router)
    app.include_router(ads_router)
    
    # Phase 1: Generative AI Tutor Foundation
    try:
        from lyo_app.personalization.routes import router as personalization_router
        app.include_router(personalization_router)
        logger.info("✅ Personalization routes integrated - Deep Knowledge Tracing active!")
    except ImportError as e:
        logger.warning(f"Personalization routes not available: {e}")
    
    # Phase 2: Advanced AI Tutoring Features
    try:
        from lyo_app.gen_curriculum.routes import router as gen_curriculum_router
        app.include_router(gen_curriculum_router)
        logger.info("✅ Generative Curriculum routes integrated - AI-powered content generation active!")
    except ImportError as e:
        logger.warning(f"Generative Curriculum routes not available: {e}")
    
    try:
        from lyo_app.collaboration.routes import router as collaboration_router
        app.include_router(collaboration_router)
        logger.info("✅ Collaborative Learning routes integrated - Peer learning and study groups active!")
    except ImportError as e:
        logger.warning(f"Collaborative Learning routes not available: {e}")
    
    # Optional legacy/feature routers (only include if present)
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

    @app.get("/health")
    async def enhanced_health_check():  # noqa: D401
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "features": settings.get_feature_flags(),
            "services": {},
        }
        # DB
        try:
            from lyo_app.core.database import engine
            async with engine.begin() as conn:
                await conn.execute("SELECT 1")
            health_status["services"]["database"] = "healthy"
        except Exception as e:  # noqa: BLE001
            health_status["services"]["database"] = f"unhealthy: {e}"
            health_status["status"] = "degraded"
        # Redis
        try:
            from lyo_app.core.redis_client import redis_client
            if redis_client:
                await redis_client.ping()
                health_status["services"]["redis"] = "healthy"
            else:
                health_status["services"]["redis"] = "not_configured"
        except Exception as e:  # noqa: BLE001
            health_status["services"]["redis"] = f"unhealthy: {e}"
        # AI
        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            health_status["services"]["ai"] = await ai_resilience_manager.get_health_status()
        except Exception as e:  # noqa: BLE001
            health_status["services"]["ai"] = f"unhealthy: {e}"
        # Storage
        try:
            from lyo_app.storage.enhanced_storage import enhanced_storage
            stats = await enhanced_storage.get_upload_stats()
            health_status["services"]["storage"] = {
                "status": "healthy",
                "providers": stats["storage_providers"],
            }
        except Exception as e:  # noqa: BLE001
            health_status["services"]["storage"] = f"unhealthy: {e}"
        # Firebase
        try:
            from lyo_app.integrations.firebase_client import firebase_client
            health_status["services"]["firebase"] = (
                "enabled" if firebase_client.is_enabled() else "disabled"
            )
        except Exception as e:  # noqa: BLE001
            health_status["services"]["firebase"] = f"error: {e}"
        # Secrets
        try:
            from lyo_app.integrations.gcp_secrets import get_secret
            key_present = bool(get_secret("GEMINI_API_KEY"))
            health_status["services"]["secrets"] = (
                "available" if key_present else "fallback_env"
            )
        except Exception as e:  # noqa: BLE001
            health_status["services"]["secrets"] = f"error: {e}"
        # Vertex AI
        try:
            from lyo_app.integrations.vertex_ai_client import vertex_ai_client
            health_status["services"]["vertex_ai"] = (
                "enabled" if vertex_ai_client.is_enabled() else "disabled"
            )
        except Exception as e:  # noqa: BLE001
            health_status["services"]["vertex_ai"] = f"error: {e}"
        return health_status

    @app.get("/metrics")
    async def get_metrics():  # noqa: D401
        if not settings.ENABLE_METRICS:
            raise HTTPException(status_code=404, detail="Metrics disabled")
        metrics = performance_monitor.get_performance_summary()
        import psutil

        metrics.update(
            {
                "system": {
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_percent": psutil.disk_usage("/").percent,
                    "active_connections": len(psutil.net_connections()),
                },
                "application": {
                    "uptime_seconds": time.time() - app.state.start_time
                    if hasattr(app.state, "start_time")
                    else 0,
                    "environment": settings.ENVIRONMENT,
                    "version": settings.APP_VERSION,
                },
            }
        )
        return metrics

    if settings.is_development():
        @app.get("/debug/config")
        async def get_debug_config():  # noqa: D401
            return {
                "app": {
                    "name": settings.APP_NAME,
                    "version": settings.APP_VERSION,
                    "environment": settings.ENVIRONMENT,
                    "debug": settings.DEBUG,
                },
                "features": settings.get_feature_flags(),
                "database": {
                    "echo": getattr(settings, "DATABASE_ECHO", False),
                    "pool_size": getattr(settings, "DATABASE_POOL_SIZE", None),
                },
                "ai": {
                    "default_model": getattr(
                        settings, "GEMINI_MODEL_DEFAULT", "gemini-pro"
                    ),
                    "temperature": getattr(settings, "GEMINI_TEMPERATURE", 0.7),
                },
            }

    app.state.start_time = time.time()
    logger.info(
        f"FastAPI application created successfully - {settings.APP_NAME} v{settings.APP_VERSION}"
    )
    return app


app = create_app()

if PROMETHEUS_AVAILABLE and settings.ENABLE_METRICS:
    @app.get("/prometheus")
    async def get_prometheus_metrics():  # noqa: D401
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():  # noqa: D401
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": settings.APP_DESCRIPTION,
        "environment": settings.ENVIRONMENT,
        "status": "operational",
        "documentation": {
            "swagger_ui": "/docs"
            if not settings.is_production()
            else "disabled_in_production",
            "redoc": "/redoc"
            if not settings.is_production()
            else "disabled_in_production",
        },
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics" if settings.ENABLE_METRICS else "disabled",
            "auth": "/api/v1/auth",
            "ai_study": "/api/v1/ai-study",
            "feeds": "/api/v1/feeds",
            "storage": "/api/v1/storage",
            "personalization": "/api/v1/personalization",
            "gen_curriculum": "/api/v1/gen-curriculum",
            "collaboration": "/api/v1/collaboration",
        },
        "features": {
            "ai_study_mode": getattr(settings, "ENABLE_AI_STUDY_MODE", True),
            "addictive_feeds": getattr(settings, "ENABLE_ADDICTIVE_FEED", True),
            "enhanced_storage": getattr(
                settings, "ENABLE_IMAGE_OPTIMIZATION", True
            ),
            "performance_monitoring": getattr(
                settings, "ENABLE_PERFORMANCE_MONITORING", True
            ),
            "deep_knowledge_tracing": True,
            "generative_curriculum": True,
            "collaborative_learning": True,
            "peer_assessment": True,
            "ai_tutoring": True,
        },
        "timestamp": time.time(),
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.getenv("PORT", getattr(settings, "PORT", 8000)))
    uvicorn.run(
        "lyo_app.main:app",
        host="0.0.0.0",
        port=port,
        workers=getattr(settings, "WORKERS", 1),
        log_level=getattr(settings, "LOG_LEVEL", "info").lower(),
        access_log=not settings.is_production(),
        reload=settings.is_development(),
        loop="uvloop" if not settings.is_development() else "auto",
    )
