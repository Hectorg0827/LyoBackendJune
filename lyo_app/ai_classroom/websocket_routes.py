"""
Lyo AI Classroom - WebSocket Routes for Real-Time Scene Streaming
================================================================

FastAPI WebSocket endpoints that integrate the Scene Lifecycle Engine with real-time client streaming.
Replaces the current SSE endpoints with full bidirectional WebSocket communication.

Architecture: iOS Client ←→ WebSocket Routes ←→ Scene Lifecycle Engine ←→ Existing Multi-Agent System
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user_or_guest, get_db
from lyo_app.auth.schemas import UserRead
from lyo_app.core.database import get_async_session

from lyo_app.ai_classroom.websocket_manager import WebSocketManager, get_websocket_manager, StreamingMode
from lyo_app.ai_classroom.scene_lifecycle_engine import SceneLifecycleEngine, TriggerType, Trigger, ActionIntent
from lyo_app.ai_classroom.sdui_models import (
    WebSocketEventType, UserActionPayload, SystemStatePayload,
    Component, Scene, SceneType
)

logger = logging.getLogger(__name__)

# Router setup
router = APIRouter(prefix="/api/v1/classroom/ws", tags=["AI Classroom WebSocket"])


# ═══════════════════════════════════════════════════════════════════════════════════
# 🔐 AUTHENTICATION FOR WEBSOCKETS
# ═══════════════════════════════════════════════════════════════════════════════════

async def authenticate_websocket(
    token: Optional[str] = Query(None, description="JWT access token"),
    api_key: Optional[str] = Query(None, description="API key for guests"),
    db: AsyncSession = Depends(get_db)
) -> UserRead:
    """Authenticate WebSocket connection using query parameters"""

    if token:
        try:
            # Verify JWT token
            from lyo_app.auth.jwt_auth import verify_token_async
            from lyo_app.auth.service import AuthService

            token_data = await verify_token_async(token, expected_type="access")
            if token_data.user_id:
                user_id = int(token_data.user_id)
                auth_service = AuthService()
                user = await auth_service.get_user_by_id(db, user_id)
                if user:
                    return user
        except Exception as e:
            logger.warning(f"WebSocket JWT authentication failed: {e}")

    if api_key:
        # Allow guest access with API key
        from lyo_app.models.enhanced import User
        return User(
            id="guest_session",
            username="Guest Learner",
            email="guest@lyo.app",
            is_active=True
        )

    raise HTTPException(status_code=401, detail="Authentication required for WebSocket")


# ═══════════════════════════════════════════════════════════════════════════════════
# 🔌 WEBSOCKET ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════════

@router.websocket("/connect")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str = Query(..., description="Learning session ID"),
    device_id: Optional[str] = Query(None, description="Device identifier"),
    streaming_mode: StreamingMode = Query(StreamingMode.ADAPTIVE, description="Scene streaming mode"),
    ws_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Main WebSocket endpoint for real-time classroom streaming.

    Handles:
    - Scene-by-scene streaming from Classroom Director
    - User action feedback (taps, submissions, requests)
    - Typing indicators and progressive reveals
    - System state synchronization
    """

    connection = None
    lifecycle_engine = None

    try:
        # Extract authentication from query parameters
        # Note: We can't use normal Depends() in WebSocket, so we parse manually
        token = websocket.query_params.get("token")
        api_key = websocket.query_params.get("api_key")

        # Basic authentication
        if not token and not api_key:
            await websocket.close(code=4001, reason="Authentication required")
            return

        # For simplicity, we'll extract user_id from token or use guest
        user_id = "guest_session"  # Default
        if token:
            try:
                from lyo_app.auth.jwt_auth import verify_token_async
                token_data = await verify_token_async(token, expected_type="access")
                user_id = str(token_data.user_id) if token_data.user_id else "guest_session"
            except:
                user_id = "guest_session"

        # Connect client
        connection = await ws_manager.connect_client(
            websocket=websocket,
            user_id=user_id,
            session_id=session_id,
            device_id=device_id
        )

        # Ensure connection is promoted to ACTIVE so scenes can be streamed
        from lyo_app.ai_classroom.websocket_manager import ConnectionState
        if connection.state != ConnectionState.ACTIVE:
            connection.state = ConnectionState.ACTIVE
            logger.info(f"🔓 Connection promoted to ACTIVE: {connection.connection_id}")

        # Initialize Scene Lifecycle Engine for this connection
        lifecycle_engine = None
        try:
            async for db in get_async_session():
                lifecycle_engine = SceneLifecycleEngine(db, ws_manager)
                break
        except Exception as e:
            logger.error(f"❌ Failed to initialize SceneLifecycleEngine: {e}", exc_info=True)
            # Send fallback welcome so iOS doesn't hang on "Connecting..."
            fallback = {
                "type": "scene_stream",
                "session_id": session_id,
                "data": {
                    "event_type": "SCENE_START",
                    "scene": {
                        "scene_id": f"db_error_{session_id}",
                        "scene_type": "welcome",
                        "components": [{
                            "component_id": f"db_err_msg_{session_id}",
                            "type": "TeacherMessage",
                            "content": "Welcome! Setting up your classroom...",
                            "delay_ms": 0,
                            "animation": "fade_in"
                        }]
                    }
                }
            }
            try:
                await websocket.send_text(json.dumps(fallback))
            except:
                pass

        # Register event handlers
        if lifecycle_engine:
            await _register_lifecycle_handlers(ws_manager, lifecycle_engine)

        logger.info(f"🎭 WebSocket connected: {connection.connection_id} (mode: {streaming_mode})")

        # Send initial scene if this is a new session
        await _send_welcome_scene(lifecycle_engine, connection, streaming_mode)

        # Message handling loop
        while True:
            try:
                # Receive message from client
                raw_message = await websocket.receive_text()

                # Handle the message
                await ws_manager.handle_client_message(connection.connection_id, raw_message)

            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket client disconnected: {connection.connection_id}")
                break
            except Exception as e:
                logger.error(f"❌ WebSocket message handling error: {e}")
                # Send error to client but keep connection alive
                error_payload = {
                    "event_type": WebSocketEventType.ERROR.value,
                    "session_id": session_id,
                    "user_id": user_id,
                    "data": {"error": str(e)},
                    "timestamp": "now"
                }
                await websocket.send_text(json.dumps(error_payload))

    except Exception as e:
        logger.error(f"💥 WebSocket connection error: {e}")
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close(code=4000, reason=f"Server error: {str(e)}")

    finally:
        # Clean up connection
        if connection and ws_manager:
            await ws_manager.disconnect_client(connection.connection_id)


async def _register_lifecycle_handlers(
    ws_manager: WebSocketManager,
    lifecycle_engine: SceneLifecycleEngine
):
    """Register handlers to connect WebSocket events to Scene Lifecycle Engine"""

    async def handle_user_action_event(payload: UserActionPayload, connection):
        """Handle user actions from WebSocket and trigger scene lifecycle"""
        try:
            # Convert WebSocket user action to Scene Lifecycle trigger
            scene = await lifecycle_engine.handle_user_action(
                user_id=payload.user_id or connection.user_id,
                session_id=payload.session_id,
                action_intent=ActionIntent(payload.action_intent),
                action_data=payload.answer_data,
                component_id=payload.component_id
            )

            # Scene will be automatically streamed by the lifecycle engine
            logger.info(f"🎯 User action processed: {payload.action_intent} → scene {scene.scene_id}")

        except Exception as e:
            logger.error(f"❌ User action handling failed: {e}")

    # Register the handler
    ws_manager.register_event_handler("user_action", handle_user_action_event)


async def _send_welcome_scene(
    lifecycle_engine: Optional[SceneLifecycleEngine],
    connection,
    streaming_mode: StreamingMode
):
    """Send initial welcome scene for new sessions"""
    if not lifecycle_engine:
        logger.warning(f"⚠️ No lifecycle engine available — sending fallback welcome for {connection.connection_id}")
        # Send a minimal welcome message directly so the client isn't stuck
        from lyo_app.ai_classroom.websocket_manager import WebSocketPayload, WebSocketEventType
        fallback = {
            "type": "scene_stream",
            "session_id": connection.session_id,
            "data": {
                "event_type": "SCENE_START",
                "scene": {
                    "scene_id": f"welcome_{connection.session_id}",
                    "scene_type": "welcome",
                    "components": [
                        {
                            "component_id": f"welcome_msg_{connection.session_id}",
                            "type": "TeacherMessage",
                            "content": "Welcome to your classroom! Let's begin learning.",
                            "delay_ms": 0,
                            "animation": "fade_in"
                        }
                    ]
                }
            }
        }
        try:
            await connection.websocket.send_text(json.dumps(fallback))
            logger.info(f"👋 Fallback welcome sent to {connection.connection_id}")
        except Exception as send_err:
            logger.error(f"❌ Failed to send fallback welcome: {send_err}")
        return

    try:
        # Resolve topic from the ConversationManager session (if one exists)
        # Also ensure a ConversationSession exists for lesson tracking
        topic = None
        course_id = None
        try:
            from lyo_app.ai_classroom.conversation_flow import get_conversation_manager
            cm = get_conversation_manager()
            conv_session = cm.get_session(connection.session_id)
            if conv_session:
                topic = conv_session.current_topic
                course_id = conv_session.current_course_id
            else:
                # iOS sends courseId as session_id — create a session for it
                from lyo_app.ai_classroom.conversation_flow import ConversationSession as ConvSession
                conv_session = ConvSession(
                    session_id=connection.session_id,
                    user_id=connection.user_id,
                    current_course_id=connection.session_id,
                    current_lesson_index=0,
                )
                cm._sessions[connection.session_id] = conv_session
                course_id = connection.session_id
                logger.info(f"📚 Created ConversationSession for WS classroom: {connection.session_id}")
        except Exception as e:
            logger.warning(f"⚠️ Could not resolve topic from ConversationManager: {e}")

        # iOS sends courseId as session_id, so always try it as course_id
        if not course_id:
            course_id = connection.session_id

        # Create welcome trigger with topic context
        welcome_trigger = Trigger(
            trigger_type=TriggerType.SYSTEM_TIMEOUT,
            user_id=connection.user_id,
            session_id=connection.session_id,
            course_id=course_id,
            action_data={"welcome": True, "topic": topic} if topic else {"welcome": True},
            urgency=1
        )

        # Process through lifecycle engine
        welcome_scene = await asyncio.wait_for(
            lifecycle_engine.process_trigger(welcome_trigger),
            timeout=10.0
        )

        logger.info(f"👋 Welcome scene sent: {welcome_scene.scene_id}")

    except Exception as e:
        logger.error(f"❌ Welcome scene failed: {e}", exc_info=True)
        # Send fallback so the client isn't stuck on "Connecting..."
        try:
            fallback = {
                "type": "scene_stream",
                "session_id": connection.session_id,
                "data": {
                    "event_type": "SCENE_START",
                    "scene": {
                        "scene_id": f"error_welcome_{connection.session_id}",
                        "scene_type": "welcome",
                        "components": [
                            {
                                "component_id": f"error_msg_{connection.session_id}",
                                "type": "TeacherMessage",
                                "content": "Welcome! I'm setting up your classroom. Let me know what you'd like to learn.",
                                "delay_ms": 0,
                                "animation": "fade_in"
                            }
                        ]
                    }
                }
            }
            await connection.websocket.send_text(json.dumps(fallback))
            logger.info(f"👋 Error-fallback welcome sent to {connection.connection_id}")
        except Exception as send_err:
            logger.error(f"❌ Failed to send error-fallback welcome: {send_err}")


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 HTTP ENDPOINTS FOR WEBSOCKET MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_websocket_stats(
    ws_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """Get WebSocket connection and streaming statistics"""
    return {
        "status": "active",
        "stats": ws_manager.get_connection_stats(),
        "features": [
            "real_time_streaming",
            "progressive_component_rendering",
            "reliable_message_delivery",
            "adaptive_streaming_modes",
            "scene_lifecycle_integration"
        ]
    }


@router.post("/trigger-scene/{session_id}")
async def trigger_scene_manually(
    session_id: str,
    scene_type: SceneType,
    urgency: int = 5,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
    ws_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Manually trigger a scene for testing/debugging.
    Useful for simulating different educational scenarios.
    """

    try:
        # Initialize lifecycle engine
        lifecycle_engine = SceneLifecycleEngine(db, ws_manager)

        # Create manual trigger
        trigger = Trigger(
            trigger_type=TriggerType.SYSTEM_TIMEOUT,
            user_id=str(current_user.id),
            session_id=session_id,
            action_data={"manual_trigger": True, "requested_scene_type": scene_type},
            urgency=urgency,
            expected_scene_types=[scene_type]
        )

        # Process trigger
        scene = await lifecycle_engine.process_trigger(trigger)

        return {
            "success": True,
            "scene_id": scene.scene_id,
            "scene_type": scene.scene_type,
            "components_count": len(scene.components),
            "message": f"Scene {scene.scene_id} triggered and streamed to session {session_id}"
        }

    except Exception as e:
        logger.error(f"❌ Manual scene trigger failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scene trigger failed: {str(e)}")


@router.post("/quiz-submit/{session_id}")
async def submit_quiz_answer(
    session_id: str,
    quiz_component_id: str,
    selected_option_id: str,
    response_time_ms: int,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
    ws_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    HTTP endpoint for quiz submission (alternative to WebSocket).
    Useful for clients that prefer HTTP for certain interactions.
    """

    try:
        # Initialize lifecycle engine
        lifecycle_engine = SceneLifecycleEngine(db, ws_manager)

        # TODO: Determine if answer is correct (would query quiz data)
        is_correct = selected_option_id == "b"  # Mock logic

        # Process quiz submission
        scene = await lifecycle_engine.handle_quiz_submission(
            user_id=str(current_user.id),
            session_id=session_id,
            quiz_component_id=quiz_component_id,
            selected_option_id=selected_option_id,
            is_correct=is_correct,
            response_time_ms=response_time_ms
        )

        return {
            "success": True,
            "is_correct": is_correct,
            "scene_id": scene.scene_id,
            "scene_type": scene.scene_type,
            "feedback_components": len([c for c in scene.components if c.type in ["TeacherMessage", "Celebration"]]),
            "next_action_required": any(c.type == "CTAButton" for c in scene.components)
        }

    except Exception as e:
        logger.error(f"❌ Quiz submission failed: {e}")
        raise HTTPException(status_code=500, detail=f"Quiz submission failed: {str(e)}")


@router.post("/celebrate/{session_id}")
async def trigger_celebration(
    session_id: str,
    achievement_type: str = "manual_trigger",
    points_earned: int = 10,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
    ws_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Trigger a celebration scene.
    Useful for external systems to reward users.
    """

    try:
        # Initialize lifecycle engine
        lifecycle_engine = SceneLifecycleEngine(db, ws_manager)

        # Trigger celebration
        scene = await lifecycle_engine.trigger_celebration(
            user_id=str(current_user.id),
            session_id=session_id,
            achievement_type=achievement_type,
            points_earned=points_earned
        )

        return {
            "success": True,
            "scene_id": scene.scene_id,
            "achievement_type": achievement_type,
            "points_earned": points_earned,
            "celebration_components": len([c for c in scene.components if c.type == "Celebration"])
        }

    except Exception as e:
        logger.error(f"❌ Celebration trigger failed: {e}")
        raise HTTPException(status_code=500, detail=f"Celebration failed: {str(e)}")


@router.get("/session/{session_id}/context")
async def get_session_context(
    session_id: str,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
    ws_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    Get current context snapshot for a session.
    Useful for debugging and analytics.
    """

    try:
        # Initialize lifecycle engine
        lifecycle_engine = SceneLifecycleEngine(db, ws_manager)

        # Get context
        context = lifecycle_engine.get_session_context(session_id)

        if not context:
            raise HTTPException(status_code=404, detail=f"No context found for session {session_id}")

        return {
            "session_id": session_id,
            "context": context.dict(),
            "summary": {
                "knowledge_concepts": len(context.knowledge_states),
                "frustration_level": context.frustration.frustration_score,
                "engagement_level": context.engagement_level,
                "session_duration_minutes": context.session_duration_minutes,
                "scenes_completed": context.scenes_completed
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Context retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Context retrieval failed: {str(e)}")


@router.get("/health")
async def websocket_health_check(
    ws_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """Health check for WebSocket service"""
    stats = ws_manager.get_connection_stats()

    is_healthy = (
        stats["active_connections"] >= 0 and  # Basic sanity check
        stats.get("average_latency_ms", 0) < 5000  # Reasonable latency
    )

    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": "websocket_classroom",
        "version": "1.0.0",
        "stats": stats,
        "timestamp": "now",
        "capabilities": [
            "real_time_scene_streaming",
            "progressive_component_rendering",
            "bidirectional_communication",
            "reliable_message_delivery",
            "adaptive_streaming_modes"
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 INTEGRATION UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════════

def get_websocket_router() -> APIRouter:
    """Get the WebSocket router for inclusion in main app"""
    return router


# Export for integration
__all__ = [
    "router",
    "get_websocket_router",
    "websocket_endpoint"
]