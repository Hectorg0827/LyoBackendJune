"""
AI Agents API Routes

Comprehensive API endpoints for the AI system including:
- Mentor conversation endpoints
- Engagement analysis endpoints  
- WebSocket connections for real-time communication
- Performance monitoring and health checks
- Content generation and analytics
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.routes import get_current_user
from lyo_app.models.enhanced import User
from .schemas import (
    MentorMessageRequest, MentorMessageResponse, ConversationHistoryResponse,
    InteractionRatingRequest, UserActionRequest, UserActionAnalysisResponse,
    EngagementSummaryResponse, AIHealthCheckResponse, AIPerformanceStatsResponse,
    WebSocketResponse, AIErrorResponse, ContentGenerationRequest, GeneratedContentResponse,
    LearningInsightsRequest, LearningInsightsResponse, BatchAnalysisRequest, BatchAnalysisResponse,
    CourseOutlineRequest, CourseOutlineResponse, LessonContentRequest, LessonContentResponse,
    ContentEvaluationRequest, ContentEvaluationResponse, ContentTaggingRequest, ContentTaggingResponse,
    ContentGapsRequest, ContentGapsResponse
)
from .mentor_agent import ai_mentor
from .sentiment_agent import sentiment_engagement_agent
from .orchestrator import ai_orchestrator, ModelType
from .websocket_manager import connection_manager, websocket_connection
from .curriculum_agent import curriculum_design_agent
from .curation_agent import content_curation_agent
from lyo_app.core.celery_tasks.ai_tasks import (
    generate_course_outline_task, generate_lesson_content_task,
    evaluate_content_quality_task, tag_content_task, identify_content_gaps_task
)
from lyo_app.monetization.engine import get_ad_for_placement

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/ai", tags=["AI Agents"])


# ============================================================================
# MENTOR CONVERSATION ENDPOINTS
# ============================================================================

# ============================================================================
# CURRICULUM DESIGN ENDPOINTS
# ============================================================================

@router.post("/curriculum/course-outline", response_model=CourseOutlineResponse)
async def generate_course_outline(
    request: CourseOutlineRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a detailed course outline based on provided parameters.
    
    This endpoint uses AI to create a structured course outline with modules,
    learning objectives, and content recommendations. Processing happens
    asynchronously with results delivered via websocket.
    """
    try:
        logger.info(f"Course outline generation request from user {current_user.id}")
        
        # Start the Celery task
        task = generate_course_outline_task.delay(
            title=request.title,
            description=request.description,
            target_audience=request.target_audience,
            learning_objectives=request.learning_objectives,
            difficulty_level=request.difficulty_level,
            estimated_duration_hours=request.estimated_duration_hours,
            user_id=current_user.id
        )
        # Provide timer + optional ad metadata for UX while task runs
        # Estimate a conservative load time in seconds (simple heuristic)
        estimated_seconds = max(5, min(60, len(request.title) + len(request.description) // 20 + 10))
        ad = get_ad_for_placement("timer")
        skip_available_after = None
        if ad and ad.duration_seconds:
            # If ad is longer than estimated load, allow skip earlier than ad end
            skip_available_after = min(ad.skippable_after_seconds or 0, estimated_seconds)
        return {
            "task_id": task.id,
            "status": "processing",
            "user_id": current_user.id,
            "timestamp": datetime.utcnow(),
            "estimated_seconds": estimated_seconds,
            "ad": ad.model_dump() if ad else None,
            "skip_available_after": skip_available_after,
        }
    except Exception as e:
        logger.error(f"Error generating course outline for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate course outline")


@router.post("/curriculum/lesson-content", response_model=LessonContentResponse)
async def generate_lesson_content(
    request: LessonContentRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate detailed content for a lesson.
    
    This endpoint uses AI to create comprehensive lesson content based on
    learning objectives, content type, and difficulty level. Processing
    happens asynchronously with results delivered via websocket.
    """
    try:
        logger.info(f"Lesson content generation request from user {current_user.id}")
        
        # Start the Celery task
        task = generate_lesson_content_task.delay(
            course_id=request.course_id,
            lesson_title=request.lesson_title,
            lesson_description=request.lesson_description,
            learning_objectives=request.learning_objectives,
            content_type=request.content_type,
            difficulty_level=request.difficulty_level,
            user_id=current_user.id
        )
        
        estimated_seconds = max(5, min(60, len(request.lesson_title) + len(request.lesson_description) // 20 + 10))
        ad = get_ad_for_placement("timer")
        skip_available_after = None
        if ad and ad.duration_seconds:
            skip_available_after = min(ad.skippable_after_seconds or 0, estimated_seconds)
        return {
            "task_id": task.id,
            "status": "processing",
            "course_id": request.course_id,
            "lesson_title": request.lesson_title,
            "user_id": current_user.id,
            "timestamp": datetime.utcnow(),
            "estimated_seconds": estimated_seconds,
            "ad": ad.model_dump() if ad else None,
            "skip_available_after": skip_available_after,
        }
    except Exception as e:
        logger.error(f"Error generating lesson content for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate lesson content")


# ============================================================================
# CONTENT CURATION ENDPOINTS
# ============================================================================

@router.post("/curation/evaluate-content", response_model=ContentEvaluationResponse)
async def evaluate_content(
    request: ContentEvaluationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Evaluate the quality of educational content.
    
    This endpoint uses AI to assess content quality across multiple dimensions
    including accuracy, clarity, engagement, and relevance.
    """
    try:
        logger.info(f"Content evaluation request from user {current_user.id}")
        
        # Start the Celery task
        task = evaluate_content_quality_task.delay(
            content_text=request.content_text,
            content_type=request.content_type,
            topic=request.topic,
            target_audience=request.target_audience,
            difficulty_level=request.difficulty_level
        )
        
        return {
            "task_id": task.id,
            "status": "processing",
            "topic": request.topic,
            "content_type": request.content_type,
            "user_id": current_user.id,
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        logger.error(f"Error evaluating content for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to evaluate content")


@router.post("/curation/tag-content", response_model=ContentTaggingResponse)
async def tag_content(
    request: ContentTaggingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Automatically tag and categorize educational content.
    
    This endpoint uses AI to generate relevant tags, categories,
    and metadata for educational content.
    """
    try:
        logger.info(f"Content tagging request from user {current_user.id}")
        
        # Start the Celery task
        task = tag_content_task.delay(
            content_text=request.content_text,
            content_type=request.content_type,
            content_title=request.content_title
        )
        
        return {
            "task_id": task.id,
            "status": "processing",
            "content_title": request.content_title,
            "content_type": request.content_type,
            "user_id": current_user.id,
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        logger.error(f"Error tagging content for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to tag content")


@router.post("/curation/identify-gaps", response_model=ContentGapsResponse)
async def identify_content_gaps(
    request: ContentGapsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Identify content gaps in a course.
    
    This endpoint uses AI to analyze a course's structure and content,
    identifying areas where additional content or clarification is needed.
    """
    try:
        logger.info(f"Content gaps analysis request from user {current_user.id}")
        
        # Start the Celery task
        task = identify_content_gaps_task.delay(
            course_id=request.course_id
        )
        
        return {
            "task_id": task.id,
            "status": "processing",
            "course_id": request.course_id,
            "user_id": current_user.id,
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        logger.error(f"Error identifying content gaps for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to identify content gaps")


@router.post("/mentor/conversation", response_model=MentorMessageResponse)
async def send_message_to_mentor(
    request: MentorMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send a message to the AI mentor and get a response.
    
    The AI mentor provides contextual, personalized educational guidance
    based on the user's current engagement state and learning history.
    """
    try:
        logger.info(f"Mentor conversation request from user {current_user.id}")
        
        # Get response from mentor
        response_data = await ai_mentor.get_response(
            user_id=current_user.id,
            message=request.message,
            db=db,
            context=request.context
        )
        
        if "error" in response_data:
            raise HTTPException(status_code=500, detail=response_data["error"])
        
        return MentorMessageResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in mentor conversation for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process mentor conversation")


@router.get("/mentor/history", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get conversation history with the AI mentor.
    
    Returns the recent conversation history, useful for continuing 
    conversations or reviewing past interactions.
    """
    try:
        history = await ai_mentor.get_conversation_history(
            user_id=current_user.id,
            db=db,
            limit=limit
        )
        
        return ConversationHistoryResponse(
            user_id=current_user.id,
            total_interactions=len(history),
            conversations=history
        )
        
    except Exception as e:
        logger.error(f"Error getting conversation history for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation history")


@router.post("/mentor/rate")
async def rate_interaction(
    request: InteractionRatingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Rate a mentor interaction as helpful or not helpful.
    
    This feedback helps improve the AI mentor's responses and
    provides valuable data for system optimization.
    """
    try:
        success = await ai_mentor.rate_interaction(
            interaction_id=request.interaction_id,
            was_helpful=request.was_helpful,
            db=db
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Interaction not found")
        
        return {"message": "Rating recorded successfully", "interaction_id": request.interaction_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rating interaction {request.interaction_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to record rating")


# ============================================================================
# ENGAGEMENT ANALYSIS ENDPOINTS
# ============================================================================

@router.post("/engagement/analyze", response_model=UserActionAnalysisResponse)
async def analyze_user_action(
    request: UserActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Analyze a user action for sentiment and engagement patterns.
    
    This endpoint processes user actions (quiz attempts, lesson completions, etc.)
    to update engagement state and trigger interventions if needed.
    """
    try:
        # Verify user can analyze this user_id (admin can analyze any user)
        if request.user_id != current_user.id and not current_user.has_role("admin"):
            raise HTTPException(status_code=403, detail="Not authorized to analyze this user")
        
        analysis_result = await sentiment_engagement_agent.analyze_user_action(
            user_id=request.user_id,
            action=request.action,
            metadata=request.metadata,
            db=db,
            user_message=request.user_message
        )
        
        if "error" in analysis_result:
            raise HTTPException(status_code=500, detail=analysis_result["error"])
        
        return UserActionAnalysisResponse(**analysis_result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing user action: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze user action")


@router.get("/engagement/summary", response_model=EngagementSummaryResponse)
async def get_engagement_summary(
    user_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive engagement summary for a user.
    
    Returns current engagement state, trends, and recommendations.
    If no user_id provided, returns summary for current user.
    """
    try:
        target_user_id = user_id or current_user.id
        
        # Verify authorization
        if target_user_id != current_user.id and not current_user.has_role("admin"):
            raise HTTPException(status_code=403, detail="Not authorized to view this user's data")
        
        summary = await sentiment_engagement_agent.get_user_engagement_summary(
            user_id=target_user_id,
            db=db
        )
        
        if "error" in summary:
            raise HTTPException(status_code=404, detail=summary["error"])
        
        return EngagementSummaryResponse(**summary)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting engagement summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get engagement summary")


# ============================================================================
# WEBSOCKET ENDPOINTS
# ============================================================================

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """
    WebSocket endpoint for real-time AI communication.
    
    Enables real-time mentor responses, proactive check-ins,
    and instant feedback delivery.
    """
    client_info = {
        "ip": websocket.client.host if websocket.client else "unknown",
        "user_agent": websocket.headers.get("user-agent", "unknown")
    }
    
    async with websocket_connection(user_id, websocket, client_info) as manager:
        try:
            while True:
                # Receive messages from client
                data = await websocket.receive_text()
                
                try:
                    message_data = json.loads(data)
                    message_type = message_data.get("type", "unknown")
                    
                    # Handle different message types
                    if message_type == "ping":
                        # Respond to ping
                        await websocket.send_text(json.dumps({
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                    
                    elif message_type == "mentor_message":
                        # Handle mentor conversation via WebSocket
                        content = message_data.get("content", "")
                        if content:
                            # Process through mentor (this would need database session)
                            await manager.send_personal_message(
                                json.dumps({
                                    "type": "mentor_response",
                                    "content": "Message received! Please use the REST API for full mentor functionality.",
                                    "timestamp": datetime.utcnow().isoformat()
                                }),
                                user_id
                            )
                    
                    else:
                        # Unknown message type
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": f"Unknown message type: {message_type}",
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                        
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": datetime.utcnow().isoformat()
                    }))
                    
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for user {user_id}")
        except Exception as e:
            logger.error(f"WebSocket error for user {user_id}: {e}")


@router.get("/ws/stats", response_model=Dict[str, Any])
async def get_websocket_stats(
    current_user: User = Depends(get_current_user)
):
    """
    Get WebSocket connection statistics.
    
    Requires admin role for access to system-wide statistics.
    """
    if not current_user.has_role("admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        stats = connection_manager.get_connection_stats()
        return stats
        
    except Exception as e:
        logger.error(f"Error getting WebSocket stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get WebSocket statistics")


# ============================================================================
# SYSTEM HEALTH AND PERFORMANCE ENDPOINTS
# ============================================================================

@router.get("/health", response_model=AIHealthCheckResponse)
async def ai_health_check():
    """
    Comprehensive AI system health check.
    
    Returns detailed health status of all AI components including:
    - Gemma 4 on-device and cloud status
    - Cloud LLM providers (OpenAI, Anthropic)
    - Circuit breaker states
    - Performance metrics
    - Cost tracking
    """
    try:
        health_status = await ai_orchestrator.health_check()
        
        return AIHealthCheckResponse(
            status=health_status["status"],
            timestamp=health_status["timestamp"],
            models=health_status["models"],
            cost_status=health_status["cost_status"],
            overall_performance={
                "response_time_p95": health_status.get("p95_response_time", 0),
                "success_rate": health_status.get("success_rate", 0),
                "active_connections": len(connection_manager.active_connections)
            }
        )
        
    except Exception as e:
        logger.error(f"AI health check failed: {e}")
        return AIHealthCheckResponse(
            status="critical",
            timestamp=datetime.utcnow().isoformat(),
            models={},
            cost_status={"error": str(e)},
            overall_performance={}
        )


@router.get("/performance/stats", response_model=AIPerformanceStatsResponse)
async def get_ai_performance_stats(
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive AI system performance statistics.
    
    Returns detailed metrics including:
    - Model usage statistics
    - Response time percentiles
    - Error rates and circuit breaker status
    - Cost analysis
    - Cache performance
    """
    try:
        stats = ai_orchestrator.get_performance_stats()
        
        return AIPerformanceStatsResponse(
            daily_cost=stats["daily_cost"],
            gemma_stats=stats["gemma_stats"],
            models=stats["models"],
            system_performance={
                "active_connections": len(connection_manager.active_connections),
                "total_users_today": await _get_daily_active_users(),
                "avg_response_time": await _get_avg_response_time(),
                "system_uptime_hours": await _get_system_uptime()
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving AI performance stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve performance statistics")


@router.post("/analyze/model-recommendation")
async def get_model_recommendation(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    Get AI model recommendations for a given prompt.
    
    Analyzes the prompt and user context to recommend optimal model,
    estimate costs, and provide routing insights without executing.
    """
    try:
        prompt = request.get("prompt", "")
        user_context = request.get("user_context", {})
        
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")
        
        recommendations = await ai_orchestrator.get_model_recommendations(
            prompt=prompt,
            user_context=user_context
        )
        
        return {
            "recommendations": recommendations,
            "user_id": current_user.id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting model recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model recommendations")


@router.get("/metrics/real-time")
async def get_real_time_metrics(
    current_user: User = Depends(get_current_user)
):
    """
    Get real-time AI system metrics.
    
    Returns current system state including active connections,
    ongoing requests, circuit breaker status, and resource usage.
    """
    if not current_user.has_role("admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get real-time connection stats
        connection_stats = connection_manager.get_connection_stats()
        
        # Get current system metrics
        performance_stats = ai_orchestrator.get_performance_stats()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "active_connections": connection_stats,
            "current_load": {
                "requests_per_minute": await _get_current_rpm(),
                "avg_response_time_last_minute": await _get_recent_response_time(),
                "error_rate_last_hour": await _get_recent_error_rate()
            },
            "resource_usage": {
                "memory_usage_mb": await _get_memory_usage(),
                "cpu_usage_percent": await _get_cpu_usage(),
                "daily_cost_used": performance_stats["daily_cost"]["current"],
                "cache_hit_rate": performance_stats["gemma_stats"]["cache_hit_rate"]
            },
            "circuit_breakers": {
                model.value: performance_stats["models"][model.value]["circuit_breaker_open"] 
                for model in ModelType if model.value in performance_stats["models"]
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting real-time metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get real-time metrics")


@router.post("/admin/circuit-breaker/reset")
async def reset_circuit_breaker(
    request: Dict[str, str],
    current_user: User = Depends(get_current_user)
):
    """
    Reset circuit breaker for a specific model.
    
    Requires admin role. Manually resets circuit breaker state
    for debugging and recovery purposes.
    """
    if not current_user.has_role("admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        model_type = request.get("model_type")
        if not model_type:
            raise HTTPException(status_code=400, detail="model_type is required")
        
        # Reset circuit breaker for the specified model
        if model_type in ai_orchestrator.model_metrics:
            metrics = ai_orchestrator.model_metrics[ModelType(model_type)]
            metrics.circuit_breaker_open = False
            metrics.failure_streak = 0
            metrics.last_failure = None
            
            logger.info(f"Circuit breaker reset for {model_type} by admin {current_user.id}")
            
            return {
                "message": f"Circuit breaker reset successfully for {model_type}",
                "model_type": model_type,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=400, detail=f"Invalid model type: {model_type}")
            
    except Exception as e:
        logger.error(f"Error resetting circuit breaker: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset circuit breaker")


# Helper functions for metrics
async def _get_daily_active_users() -> int:
    """Get count of daily active users."""
    # This would query the database for unique users today
    return 0  # Placeholder

async def _get_avg_response_time() -> float:
    """Get average response time across all models."""
    # Calculate from orchestrator metrics
    return 0.0  # Placeholder

async def _get_system_uptime() -> float:
    """Get system uptime in hours."""
    # Calculate from application start time
    return 0.0  # Placeholder

async def _get_current_rpm() -> int:
    """Get current requests per minute."""
    return 0  # Placeholder

async def _get_recent_response_time() -> float:
    """Get average response time for last minute."""
    return 0.0  # Placeholder

async def _get_recent_error_rate() -> float:
    """Get error rate for last hour."""
    return 0.0  # Placeholder

async def _get_memory_usage() -> float:
    """Get current memory usage in MB."""
    return 0.0  # Placeholder

async def _get_cpu_usage() -> float:
    """Get current CPU usage percentage."""
    return 0.0  # Placeholder


# ============================================================================
# MAINTENANCE AND ADMIN ENDPOINTS
# ============================================================================

@router.post("/maintenance/cleanup")
async def cleanup_system(
    current_user: User = Depends(get_current_user)
):
    """
    Perform system cleanup and maintenance.
    
    Requires admin role. Cleans up inactive connections,
    old conversation contexts, and performs optimizations.
    """
    if not current_user.has_role("admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Cleanup inactive WebSocket connections
        await connection_manager.cleanup_stale_connections()
        
        # Cleanup inactive conversation contexts
        ai_mentor.cleanup_inactive_conversations()
        
        return {
            "message": "System cleanup completed successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error during system cleanup: {e}")
        raise HTTPException(status_code=500, detail="System cleanup failed")


# ============================================================================
# ERROR HANDLERS - These should be added to the main app, not the router
# ============================================================================

# Note: Exception handlers are defined here but should be registered with the main app
# Example usage in main.py:
# from lyo_app.ai_agents.routes import ai_exception_handler
# app.add_exception_handler(Exception, ai_exception_handler)

async def ai_exception_handler(request, exc):
    """Global exception handler for AI endpoints."""
    logger.error(f"Unhandled AI system error: {exc}")
    
    return JSONResponse(
        status_code=500,
        content=AIErrorResponse(
            message="An unexpected error occurred in the AI system",
            error_code="AI_SYSTEM_ERROR",
            details={"exception_type": type(exc).__name__}
        ).dict()
    )


# Import and include optimization routes
try:
    from .optimization.routes import setup_optimization_routes
    # Setup optimization routes
    setup_optimization_routes(router)
    logger.info("AI optimization routes loaded successfully")
except ImportError as e:
    logger.warning(f"AI optimization routes not available: {e}")
