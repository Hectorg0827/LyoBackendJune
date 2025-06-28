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
from lyo_app.auth.dependencies import get_current_user
from lyo_app.auth.models import User
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
from .orchestrator import ai_orchestrator
from .websocket_manager import connection_manager, websocket_connection
from .curriculum_agent import curriculum_design_agent
from .curation_agent import content_curation_agent
from lyo_app.core.celery_tasks.ai_tasks import (
    generate_course_outline_task, generate_lesson_content_task,
    evaluate_content_quality_task, tag_content_task, identify_content_gaps_task
)

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
        
        return {
            "task_id": task.id,
            "status": "processing",
            "user_id": current_user.id,
            "timestamp": datetime.utcnow()
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
        
        return {
            "task_id": task.id,
            "status": "processing",
            "course_id": request.course_id,
            "lesson_title": request.lesson_title,
            "user_id": current_user.id,
            "timestamp": datetime.utcnow()
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
    Comprehensive health check of the AI system.
    
    Tests all AI models and components, returns detailed status.
    """
    try:
        health_status = await ai_orchestrator.health_check()
        return AIHealthCheckResponse(**health_status)
        
    except Exception as e:
        logger.error(f"Error in AI health check: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")


@router.get("/performance", response_model=AIPerformanceStatsResponse)
async def get_performance_stats(
    current_user: User = Depends(get_current_user)
):
    """
    Get AI system performance statistics.
    
    Requires admin role for access to performance metrics.
    """
    if not current_user.has_role("admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        stats = ai_orchestrator.get_performance_stats()
        return AIPerformanceStatsResponse(**stats)
        
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get performance statistics")


# ============================================================================
# CONTENT GENERATION ENDPOINTS (Future Expansion)
# ============================================================================

@router.post("/content/generate", response_model=GeneratedContentResponse)
async def generate_educational_content(
    request: ContentGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate educational content using AI.
    
    Creates personalized lessons, quizzes, and explanations
    based on the specified topic and difficulty level.
    """
    try:
        # This would be implemented when content generation is ready
        # For now, return a placeholder response
        
        return GeneratedContentResponse(
            content=f"AI-generated content for '{request.topic}' at {request.difficulty_level} level would appear here.",
            content_type=request.content_type,
            difficulty_level=request.difficulty_level,
            estimated_duration_minutes=30,
            learning_objectives=request.learning_objectives,
            additional_resources=[],
            generation_metadata={
                "model_used": "placeholder",
                "generation_time_ms": 0,
                "user_id": current_user.id
            }
        )
        
    except Exception as e:
        logger.error(f"Error generating content: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate content")


# ============================================================================
# ANALYTICS AND INSIGHTS ENDPOINTS
# ============================================================================

@router.post("/insights/learning", response_model=LearningInsightsResponse)
async def get_learning_insights(
    request: LearningInsightsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive learning analytics insights.
    
    Provides detailed analysis of learning patterns, progress,
    and personalized recommendations.
    """
    try:
        # Verify authorization
        if request.user_id != current_user.id and not current_user.has_role("admin"):
            raise HTTPException(status_code=403, detail="Not authorized to view this user's insights")
        
        # This would be implemented when analytics system is ready
        # For now, return a placeholder response
        
        return LearningInsightsResponse(
            user_id=request.user_id,
            time_period_days=request.time_period_days,
            engagement_summary={"average_engagement": "high", "trend": "improving"},
            learning_progress={"completion_rate": 85, "average_score": 0.78},
            behavioral_patterns=["consistent_daily_learning", "strong_morning_performance"],
            strengths=["problem_solving", "conceptual_understanding"],
            areas_for_improvement=["time_management", "quiz_preparation"],
            personalized_recommendations=[
                "Focus on spaced repetition for better retention",
                "Consider shorter study sessions to maintain engagement"
            ],
            predictions={"likely_completion_date": "2024-08-15"} if request.include_predictions else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting learning insights: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate learning insights")


# ============================================================================
# BATCH PROCESSING ENDPOINTS
# ============================================================================

@router.post("/batch/analyze", response_model=BatchAnalysisResponse)
async def batch_analyze_users(
    request: BatchAnalysisRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Perform batch analysis on multiple users.
    
    Requires admin role. Useful for system-wide analytics
    and bulk engagement analysis.
    """
    if not current_user.has_role("admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        start_time = datetime.utcnow()
        
        # For now, return a placeholder response
        # In production, this would queue background tasks
        
        background_tasks.add_task(
            _process_batch_analysis,
            request.user_ids,
            request.analysis_type,
            request.parameters
        )
        
        return BatchAnalysisResponse(
            total_users=len(request.user_ids),
            successful_analyses=0,
            failed_analyses=0,
            results=[],
            errors=[],
            processing_time_seconds=0,
            started_at=start_time,
            completed_at=start_time  # Would be updated when complete
        )
        
    except Exception as e:
        logger.error(f"Error starting batch analysis: {e}")
        raise HTTPException(status_code=500, detail="Failed to start batch analysis")


async def _process_batch_analysis(user_ids: List[int], analysis_type: str, parameters: Optional[Dict]):
    """Background task for processing batch analysis."""
    logger.info(f"Starting batch analysis for {len(user_ids)} users: {analysis_type}")
    
    # Implementation would go here
    # This is where the actual batch processing would happen
    
    logger.info(f"Completed batch analysis for {len(user_ids)} users")


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
# ERROR HANDLERS
# ============================================================================

@router.exception_handler(Exception)
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
