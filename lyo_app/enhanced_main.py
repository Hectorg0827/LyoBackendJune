import asyncio
import os
import time
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, List, Optional, Any, Callable

# BOOTSTRAP HEARTBEAT - Monitors slow import performance on Cloud Run
pid = os.getpid()
print(f">>> [PID {pid}] BOOTSTRAP STARTING (enhanced_main.py)...", flush=True)

print(f">>> [PID {pid}] BOOTSTRAP: Loading FastAPI...", flush=True)
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
print(f">>> [PID {pid}] BOOTSTRAP: FastAPI loaded", flush=True)

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

# Setup secure logging (masks API keys) - optional module
try:
    from lyo_app.core.secure_config import setup_secure_logging
    setup_secure_logging()
except ImportError:
    pass  # secure_config is optional

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


# Parallel initialization helpers
async def _init_redis_safe():
    """Initialize Redis with error handling"""
    try:
        from lyo_app.core.redis_client import init_redis
        await init_redis()
        logger.info("✓ Redis cache initialized")
        return True
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e}")
        return False


async def _init_storage_safe():
    """Initialize storage with error handling"""
    try:
        from lyo_app.storage.enhanced_storage import enhanced_storage
        await enhanced_storage._initialize_clients()
        logger.info("✓ Enhanced storage system initialized")
        return True
    except Exception as e:
        logger.warning(f"Storage system initialization failed: {e}")
        return False


async def _init_ai_safe():
    """Initialize AI with error handling"""
    try:
        from lyo_app.core.ai_resilience import ai_resilience_manager
        from lyo_app.ai_agents.optimization.performance_optimizer import ai_performance_optimizer
        
        await ai_resilience_manager.initialize()
        await ai_performance_optimizer.initialize()
        
        logger.info("✓ AI resilience & performance systems initialized")
        return True
    except Exception as e:
        logger.warning(f"AI system initialization failed: {e}")
        return False


async def _init_firebase_safe():
    """Initialize Firebase with error handling (offloaded to thread)"""
    try:
        from lyo_app.integrations.firebase_client import firebase_client
        # Run blocking initialization in a separate thread
        await asyncio.to_thread(firebase_client.initialize_app)
        
        if firebase_client.is_enabled():
            logger.info("✓ Firebase client initialized (Firestore/Storage available)")
        else:
            logger.info("Firebase not enabled - continuing without it")
        return True
    except Exception as e:
        logger.warning(f"Firebase initialization failed: {e}")
        return False


async def _init_vertex_safe():
    """Initialize Vertex AI with error handling (offloaded to thread)"""
    try:
        from lyo_app.integrations.vertex_ai_client import vertex_ai_client
        # Run blocking initialization in a separate thread
        await asyncio.to_thread(vertex_ai_client.initialize_app)

        if vertex_ai_client.is_enabled():
            logger.info("✓ Vertex AI client ready")
        else:
            logger.info("Vertex AI not enabled - continuing")
        return True
    except Exception as e:
        logger.warning(f"Vertex AI initialization skipped/failed: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup & shutdown lifecycle with parallel initialization."""
    print(">>> [LIFESPAN] STARTING...", flush=True)
    start_time = time.time()
    logger.info("🚀 Starting LyoBackend with enhanced features...")
    setup_logging()
    
    # Database must init first (dependencies need it)
    try:
        print(">>> [LIFESPAN] Initializing database...", flush=True)
        logger.info("⏳ Initializing database...")
        await init_db()
        print(">>> [LIFESPAN] Database initialized", flush=True)
        logger.info("✅ Database initialized")
    except Exception as e:
        print(f">>> [LIFESPAN] Database initialization FAILED: {e}", flush=True)
        logger.error(f"❌ Database initialization failed: {e}")
    
    # Sentry (synchronous, fast)
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
        logger.info("✓ Sentry monitoring initialized")
    
    # PARALLEL INITIALIZATION - Major performance boost!
    # Re-enabled after isolating boot performance to library import times
    logger.info("Initializing services (AI/Firebase/Vertex)...")
    init_tasks = [
        _init_redis_safe(),
        _init_storage_safe(),
        _init_ai_safe(),
        _init_firebase_safe(),
        _init_vertex_safe(),
    ]
    
    results = await asyncio.gather(*init_tasks, return_exceptions=True)
    successful = sum(1 for r in results if r is True)
    
    elapsed = time.time() - start_time
    logger.info(f"🎉 LyoBackend startup completed in {elapsed:.2f}s ({successful}/5 services)")
    
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
    logger.info("🛠️ FastAPI instance created")
    # Middleware - Security First
    from lyo_app.middleware.security_middleware import SecurityMiddleware
    from lyo_app.middleware.usage_middleware import UsageMiddleware
    from lyo_app.core.structured_logging import setup_logging as setup_structured_logging
    
    # Setup structured logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_structured_logging(
        environment=settings.ENVIRONMENT,
        log_level=log_level,
        json_logs=(settings.ENVIRONMENT in ("production", "staging"))
    )
    
    # Add usage middleware (inner layer, runs after security)
    app.add_middleware(UsageMiddleware)
    
    # Add security middleware (rate limiting, audit logging, security headers)
    app.add_middleware(
        SecurityMiddleware,
        enable_rate_limiting=True,
        enable_audit_logging=True,
        enable_security_headers=True
    )
    
    # CORS
    app.add_middleware(CORSMiddleware, **settings.get_cors_config())
    
    # Add response compression for bandwidth optimization (60-80% reduction)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    logger.info("🛡️ Middlewares added")
    
    # Performance and error monitoring
    app.middleware("http")(performance_monitoring_middleware)
    app.middleware("http")(enhanced_error_middleware)
    app.middleware("http")(request_size_middleware)
    setup_error_handlers(app)
    # Routers
    print(">>> IMPORTING AUTH ROUTES...", flush=True)
    from lyo_app.auth.routes import router as auth_router
    print(">>> AUTH ROUTES IMPORTED", flush=True)
    try:
        print(">>> IMPORTING AI STUDY ROUTES...", flush=True)
        from lyo_app.ai_study.clean_routes import router as ai_study_router
        print(">>> AI STUDY ROUTES IMPORTED", flush=True)
    except ImportError:
        from lyo_app.ai_study.routes import router as ai_study_router
        logger.warning("Using basic AI study routes (clean routes unavailable)")
    
    # Vision routes
    try:
        from lyo_app.ai_study.vision_routes import router as vision_router
        app.include_router(vision_router)
        logger.info("✅ Gemini Vision routes integrated - Multimodal image analysis active!")
    except ImportError as e:
        logger.warning(f"⚠️ Could not import Vision routes: {e}")

    # Recommendations routes
    try:
        from lyo_app.ai_study.recommendations_routes import router as recommendations_router
        app.include_router(recommendations_router)
        logger.info("✅ Recommendations & Embeddings routes integrated - Smart content discovery active!")
    except ImportError as e:
        logger.warning(f"⚠️ Could not import Recommendations routes: {e}")
    
    try:
        from lyo_app.feeds.enhanced_routes import router as feeds_router
    except ImportError:
        from lyo_app.feeds.routes import router as feeds_router
        logger.warning("Using basic feeds routes (enhanced routes unavailable)")
    # Use storage_routes which includes both enhanced_routes AND iOS-compatible uploads alias
    try:
        from lyo_app.storage_routes import router as storage_router
        logger.info("✅ Storage routes loaded (with iOS uploads alias)")
    except ImportError:
        try:
            from lyo_app.storage.enhanced_routes import router as storage_router
            logger.warning("Using storage.enhanced_routes (iOS alias unavailable)")
        except ImportError:
            storage_router = None
            logger.warning("Storage routes unavailable")
    # from lyo_app.monetization.routes import router as ads_router  # TODO: stripe_service doesn't exist
    try:
        print(">>> IMPORTING API V1 ROUTES...", flush=True)
        from lyo_app.api.v1 import api_router

        app.include_router(api_router, prefix="/api/v1")
        print(">>> API V1 ROUTES INTEGRATED", flush=True)
    except ImportError as e:  # noqa: BLE001
        logger.warning(f"API v1 routes not available: {e}")

    # Analytics & Profiling
    try:
        from lyo_app.api.analytics import router as analytics_router
        app.include_router(analytics_router, prefix="/api/v1")
        logger.info("✅ Analytics routes integrated - Implicit Behavioral Profiling active!")
    except ImportError as e:
        logger.warning(f"Analytics routes not available: {e}")

    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(ai_study_router)
    app.include_router(feeds_router, prefix="/api/v1")
    if storage_router:
        app.include_router(storage_router)
    # app.include_router(ads_router)  # TODO: Monetization module incomplete
    # AI API Routes
    try:
        from lyo_app.routers.ai_routes import router as ai_router
        app.include_router(ai_router)
    except ImportError:
        pass
    
    # AI Chat
    try:
        from lyo_app.ai_chat.routes import router as ai_chat_router
        app.include_router(ai_chat_router)
    except ImportError:
        pass
    
    # TTS
    try:
        from lyo_app.tts.routes import router as tts_router
        app.include_router(tts_router)
    except ImportError:
        pass
    
    # Image Generation
    try:
        from lyo_app.image_gen.routes import router as image_gen_router
        app.include_router(image_gen_router)
    except ImportError:
        pass
    
    # AI Classroom
    try:
        from lyo_app.ai_classroom.routes import router as ai_classroom_router
        app.include_router(ai_classroom_router)
    except ImportError:
        pass

    # AI Classroom Playback - Interactive Cinema API (separate router)
    try:
        from lyo_app.ai_classroom.playback_routes import router as playback_router
        app.include_router(playback_router)
        logger.info("✅ AI Classroom Playback routes integrated - Interactive Cinema active!")
    except ImportError as e:
        logger.warning(f"AI Classroom Playback routes not available: {e}")
    
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
    
    try:
        from lyo_app.adaptive_learning.routes import router as adaptive_router
        app.include_router(adaptive_router)
        logger.info("✅ Adaptive Learning routes integrated - AI-powered personalized sessions active!")
    except ImportError as e:
        logger.warning(f"Adaptive Learning routes not available: {e}")
    
    # Chat Module - Mode-based routing with agents
    try:
        from lyo_app.chat import chat_router
        app.include_router(chat_router, prefix="/api/v1")
        logger.info("✅ Chat routes integrated - Mode-based routing (Explainer, Planner, Practice, Notes) active!")
    except ImportError as e:
        logger.warning(f"Chat routes not available: {e}")
    
    # Optional legacy/feature routers (only include if present)
    # Health Check Routes (Phase 4: Observability)
    try:
        from lyo_app.routers.health_routes import router as health_router
        app.include_router(health_router)
        logger.info("✅ Health check routes integrated - /health/live, /health/ready endpoints active!")
    except ImportError as e:
        logger.warning(f"Health check routes not available: {e}")
    
    # Clips Router - Educational video clips with AI course generation
    try:
        from lyo_app.routers.clips import router as clips_router
        app.include_router(clips_router, prefix="/api/v1", tags=["clips"])
        logger.info("✅ Clips routes integrated - Video clips with AI course generation active!")
    except ImportError as e:
        logger.warning(f"Clips routes not available: {e}")
    
    # Optional legacy/feature routers (only include if present)
    try:
        from lyo_app.community.routes import router as community_router
        app.include_router(community_router, prefix="/community", tags=["community"])
        app.include_router(community_router, prefix="/api/v1/community", tags=["community"])
    except ImportError:
        pass
    try:
        from lyo_app.gamification.routes import router as gamification_router
        app.include_router(gamification_router, prefix="/gamification", tags=["gamification"])
        app.include_router(gamification_router, prefix="/api/v1/gamification", tags=["gamification"])
    except ImportError:
        pass
    try:
        from lyo_app.learning.routes import router as learning_router
        app.include_router(learning_router, prefix="/learning", tags=["learning"])
        app.include_router(learning_router, prefix="/api/v1/learning", tags=["learning"])
    except ImportError:
        pass
    try:
        from lyo_app.storage_routes import router as storage_router
        app.include_router(storage_router)
        logger.info("✅ Google Cloud Storage routes integrated - File uploads and processing active!")
    except ImportError as e:
        logger.warning(f"Storage routes not available: {e}")

    try:
        from lyo_app.stack.routes import router as stack_router
        app.include_router(stack_router, prefix="/stack")
        app.include_router(stack_router, prefix="/api/v1/stack")
        logger.info("✅ Stack routes integrated at /stack and /api/v1/stack - Personal knowledge stack active!")
    except ImportError as e:
        logger.warning(f"Stack routes not available: {e}")

    # Stories Router - Instagram-style 24h expiring stories
    try:
        from lyo_app.routers.stories import router as stories_router
        app.include_router(stories_router, prefix="/api/v1")
        logger.info("✅ Stories routes integrated at /api/v1/stories - Ephemeral content active!")
    except ImportError as e:
        logger.warning(f"Stories routes not available: {e}")

    try:
        from lyo_app.classroom.routes import router as classroom_router
        app.include_router(classroom_router)
        logger.info("✅ Classroom routes integrated - Virtual classroom sessions active!")
    except ImportError as e:
        logger.warning(f"Classroom routes not available: {e}")
    
    # Multi-Agent Course Generation v2
    try:
        from lyo_app.ai_agents.multi_agent_v2.routes import router as course_gen_router
        app.include_router(course_gen_router)
        logger.info("✅ Multi-Agent Course Generation v2 integrated - 5-agent pipeline with Gemini 2.5 Pro + 1.5 Flash!")
    except ImportError as e:
        logger.warning(f"Multi-Agent Course Generation v2 routes not available: {e}")
    
    # AI Tutor and Exercise Validation v2
    try:
        from lyo_app.ai_agents.multi_agent_v2.tutor_routes import router as tutor_router
        app.include_router(tutor_router)
        logger.info("✅ AI Tutor & Exercise Validator integrated - Context-aware tutoring with code sandbox!")
    except ImportError as e:
        logger.warning(f"AI Tutor v2 routes not available: {e}")
    
    # Multi-Agent V2 - Streaming Support (NEW - Gemini Enhancements)
    try:
        from lyo_app.ai_agents.multi_agent_v2.routes_streaming import streaming_router
        app.include_router(streaming_router)
        logger.info("✅ Multi-agent v2 streaming routes loaded - Real-time progress updates!")
    except ImportError as e:
        logger.warning(f"⚠️ Streaming routes not available: {e}")
    
    # Multi-Agent V2 - Analytics (NEW - Gemini Enhancements)
    try:
        from lyo_app.ai_agents.multi_agent_v2.routes_analytics import analytics_router
        app.include_router(analytics_router)
        logger.info("✅ Multi-agent v2 analytics routes loaded - Usage tracking active!")
    except ImportError as e:
        logger.warning(f"⚠️ Analytics routes not available: {e}")

    # A2A Protocol - Google Agent-to-Agent Course Generation (NEW)
    try:
        from lyo_app.ai_agents.a2a import include_a2a_routes
        include_a2a_routes(app)
        logger.info("✅ A2A Protocol routes integrated - Multi-agent pipeline with AgentCards, streaming, and discovery!")
    except ImportError as e:
        logger.warning(f"⚠️ A2A Protocol routes not available: {e}")

    # Multi-Tenant SaaS API
    try:
        from lyo_app.tenants.routes import router as tenants_router
        app.include_router(tenants_router, prefix="/api/v1")
        logger.info("✅ Tenant routes integrated - Multi-tenant SaaS API active!")
    except ImportError as e:
        logger.warning(f"Tenant routes not available: {e}")

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
            from sqlalchemy import text
            from lyo_app.core.database import engine
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            health_status["services"]["database"] = "healthy"
        except Exception as e:  # noqa: BLE001
            health_status["services"]["database"] = f"unhealthy: {e}"
            health_status["status"] = "degraded"
        # Redis
        try:
            from lyo_app.core.redis_client import redis_client
            if redis_client:
                if await redis_client.ping():
                    health_status["services"]["redis"] = "healthy"
                else:
                    health_status["services"]["redis"] = "not_connected"
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
    async def prometheus_metrics():
        """
        Prometheus metrics endpoint (Phase 4: Observability)
        Returns metrics in Prometheus format if available
        """
        try:
            from lyo_app.core.prometheus_metrics import (
                metrics_endpoint_handler,
                get_metrics_content_type,
                PROMETHEUS_AVAILABLE
            )
            
            if PROMETHEUS_AVAILABLE:
                from fastapi.responses import Response
                metrics_data = metrics_endpoint_handler()
                return Response(
                    content=metrics_data,
                    media_type=get_metrics_content_type()
                )
            else:
                # Fallback to basic metrics
                return {
                    "message": "Prometheus not installed, showing basic metrics",
                    "metrics": performance_monitor.get_performance_summary()
                }
        except Exception as e:
            logger.error(f"Metrics endpoint error: {e}")
            return {"error": str(e)}
    
    @app.get("/metrics/legacy")
    async def get_legacy_metrics():  # noqa: D401
        """Legacy metrics endpoint with system information"""
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


# Create app lazily to avoid import-time errors
_app = None

def get_app():
    print(">>> CHECKING REVISION: SECURITY FIX APPLIED <<<")
    global _app
    if _app is None:
        _app = create_app()
    return _app

app = get_app()

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
            "course_generation_v2": "/api/v2/courses",
            "a2a_generation": "/api/v2/courses/generate-a2a",
            "a2a_streaming": "/api/v2/courses/stream-a2a",
            "a2a_agents": "/api/v2/agents",
            "a2a_discovery": "/.well-known/agent.json",
            "tutor_v2": "/api/v2/tutor",
            "exercises_v2": "/api/v2/exercises",
            "media_v2": "/api/v2/media",
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
            "a2a_protocol": True,
            "multi_agent_streaming": True,
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
