"""
Pydantic schemas for AI Agents API

Defines request/response models for all AI agent endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum
from lyo_app.learning.models import DifficultyLevel, ContentType


class UserEngagementStateEnum(str, Enum):
    """User engagement states."""
    ENGAGED = "engaged"
    STRUGGLING = "struggling"
    BORED = "bored"
    CURIOUS = "curious"
    IDLE = "idle"
    FRUSTRATED = "frustrated"
    CONFIDENT = "confident"


class AIModelTypeEnum(str, Enum):
    """AI model types."""
    GEMMA_ON_DEVICE = "gemma_on_device"
    CLOUD_LLM = "cloud_llm"
    HYBRID = "hybrid"


class ResponseModeEnum(str, Enum):
    """Chat response modes."""
    CHAT = "chat"
    COURSE = "course"
    EXPLAINER = "explainer"


class QuickExplainerData(BaseModel):
    """Data for quick explainer mode."""
    concept: str = Field(..., description="Concept name")
    explanation: str = Field(..., description="Short explanation")
    chips: List[str] = Field(..., description="Action chips")


class CourseProposalData(BaseModel):
    """Data for course proposal mode."""
    title: str = Field(..., description="Course title")
    subtext: str = Field(..., description="Course subtext/topics")
    summary: str = Field(..., description="Course summary")
    modules: List[str] = Field(..., description="List of modules")
    button_text: str = Field("Start Learning", description="CTA button text")


# Mentor Conversation Schemas
class MentorMessageRequest(BaseModel):
    """Request to send message to AI mentor."""
    message: str = Field(..., min_length=1, max_length=2000, description="Message to send to mentor")
    context: Optional[Dict[str, Any]] = Field(None, description="Optional context information")
    
    @validator('message')
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()


class MentorMessageResponse(BaseModel):
    """Response from AI mentor."""
    response: str = Field(..., description="Mentor's response")
    interaction_id: int = Field(..., description="Database ID of the interaction")
    model_used: AIModelTypeEnum = Field(..., description="AI model that generated the response")
    response_time_ms: float = Field(..., description="Response generation time in milliseconds")
    strategy_used: str = Field(..., description="Response strategy employed")
    conversation_id: str = Field(..., description="Conversation session ID")
    engagement_state: UserEngagementStateEnum = Field(..., description="User's current engagement state")
    timestamp: datetime = Field(..., description="Timestamp of the response")
    
    # Enhanced UI Modes
    response_mode: ResponseModeEnum = Field(ResponseModeEnum.CHAT, description="Display mode: chat, course, or explainer")
    quick_explainer: Optional[QuickExplainerData] = Field(None, description="Data for quick explainer mode")
    course_proposal: Optional[CourseProposalData] = Field(None, description="Data for course proposal mode")


class ConversationHistoryResponse(BaseModel):
    """Response containing conversation history."""
    user_id: int = Field(..., description="User identifier")
    total_interactions: int = Field(..., description="Total number of interactions")
    conversations: List[Dict[str, Any]] = Field(..., description="List of conversation interactions")


class InteractionRatingRequest(BaseModel):
    """Request to rate an interaction."""
    interaction_id: int = Field(..., description="ID of the interaction to rate")
    was_helpful: bool = Field(..., description="Whether the interaction was helpful")


# Engagement Analysis Schemas
class UserActionRequest(BaseModel):
    """Request to analyze user action."""
    user_id: int = Field(..., description="User identifier")
    action: str = Field(..., description="Type of action performed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Action metadata")
    user_message: Optional[str] = Field(None, description="Optional user message to analyze")


class SentimentAnalysisResult(BaseModel):
    """Result of sentiment analysis."""
    sentiment_score: float = Field(..., ge=-1.0, le=1.0, description="Sentiment score from -1 to 1")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the analysis")
    primary_emotion: str = Field(..., description="Primary detected emotion")
    emotions: Dict[str, float] = Field(default_factory=dict, description="Detected emotions with intensities")
    educational_context: Dict[str, str] = Field(default_factory=dict, description="Educational context detected")
    insights: List[str] = Field(default_factory=list, description="Analysis insights")


class EngagementAnalysisResult(BaseModel):
    """Result of engagement pattern analysis."""
    engagement_level: UserEngagementStateEnum = Field(..., description="Detected engagement level")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the analysis")
    indicators: Dict[str, float] = Field(default_factory=dict, description="Engagement indicators")
    recommended_actions: List[str] = Field(default_factory=list, description="Recommended interventions")
    risk_factors: List[str] = Field(default_factory=list, description="Identified risk factors")
    positive_indicators: List[str] = Field(default_factory=list, description="Positive engagement indicators")


class UserActionAnalysisResponse(BaseModel):
    """Response from user action analysis."""
    user_id: int = Field(..., description="User identifier")
    action: str = Field(..., description="Action that was analyzed")
    previous_state: UserEngagementStateEnum = Field(..., description="Previous engagement state")
    new_state: UserEngagementStateEnum = Field(..., description="New engagement state")
    sentiment_analysis: Optional[SentimentAnalysisResult] = Field(None, description="Sentiment analysis results")
    engagement_analysis: EngagementAnalysisResult = Field(..., description="Engagement analysis results")
    intervention_triggered: bool = Field(..., description="Whether intervention was triggered")
    recommendations: List[str] = Field(default_factory=list, description="Actionable recommendations")
    timestamp: datetime = Field(..., description="Analysis timestamp")


class EngagementSummaryResponse(BaseModel):
    """Response containing user engagement summary."""
    user_id: int = Field(..., description="User identifier")
    current_state: UserEngagementStateEnum = Field(..., description="Current engagement state")
    sentiment_score: float = Field(..., description="Latest sentiment score")
    confidence_score: float = Field(..., description="Confidence in current assessment")
    consecutive_struggles: int = Field(..., description="Number of consecutive struggle incidents")
    activity_count: int = Field(..., description="Total activity count")
    last_analyzed: datetime = Field(..., description="Last analysis timestamp")
    trends: Dict[str, Any] = Field(default_factory=dict, description="Engagement trends")
    recent_activities_count: int = Field(..., description="Number of recent activities")
    recommendations: List[str] = Field(default_factory=list, description="Current recommendations")


# AI Orchestrator Schemas
class AIHealthCheckResponse(BaseModel):
    """Response from AI system health check."""
    status: str = Field(..., description="Overall health status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    models: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Individual model health status")
    cost_status: Dict[str, Any] = Field(default_factory=dict, description="Cost tracking status")
    overall_performance: Dict[str, Any] = Field(default_factory=dict, description="Overall performance metrics")


class AIPerformanceStatsResponse(BaseModel):
    """Response containing AI performance statistics."""
    daily_cost: Dict[str, float] = Field(default_factory=dict, description="Daily cost information")
    gemma_stats: Dict[str, Any] = Field(default_factory=dict, description="Gemma client statistics")
    models: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Per-model performance stats")
    system_performance: Dict[str, Any] = Field(default_factory=dict, description="Overall system performance")


# WebSocket Message Schemas
class WebSocketMessage(BaseModel):
    """Base WebSocket message format."""
    type: str = Field(..., description="Message type")
    content: str = Field(..., description="Message content")
    from_: str = Field(..., alias="from", description="Message sender")
    timestamp: datetime = Field(..., description="Message timestamp")


class WebSocketResponse(BaseModel):
    """WebSocket connection response."""
    connection_id: str = Field(..., description="WebSocket connection ID")
    status: str = Field(..., description="Connection status")
    message: str = Field(..., description="Status message")


# Error Response Schema
class AIErrorResponse(BaseModel):
    """Error response from AI system."""
    error: bool = Field(True, description="Indicates this is an error response")
    message: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Specific error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    correlation_id: Optional[str] = Field(None, description="Request correlation ID")


# Curriculum and Content Generation Schemas (for future use)
class ContentGenerationRequest(BaseModel):
    """Request for AI-generated educational content."""
    topic: str = Field(..., min_length=1, max_length=200, description="Topic to generate content for")
    difficulty_level: str = Field(..., description="Difficulty level (beginner, intermediate, advanced)")
    content_type: str = Field(..., description="Type of content (lesson, quiz, exercise, explanation)")
    learning_objectives: List[str] = Field(default_factory=list, description="Specific learning objectives")
    user_context: Optional[Dict[str, Any]] = Field(None, description="User context for personalization")


class GeneratedContentResponse(BaseModel):
    """Response containing AI-generated content."""
    content: str = Field(..., description="Generated educational content")
    content_type: str = Field(..., description="Type of generated content")
    difficulty_level: str = Field(..., description="Content difficulty level")
    estimated_duration_minutes: int = Field(..., description="Estimated time to complete")
    learning_objectives: List[str] = Field(default_factory=list, description="Covered learning objectives")
    additional_resources: List[str] = Field(default_factory=list, description="Additional recommended resources")
    generation_metadata: Dict[str, Any] = Field(default_factory=dict, description="Generation metadata")


# Analytics and Insights Schemas
class LearningInsightsRequest(BaseModel):
    """Request for learning analytics insights."""
    user_id: int = Field(..., description="User identifier")
    time_period_days: int = Field(30, ge=1, le=365, description="Time period for analysis")
    include_predictions: bool = Field(False, description="Whether to include predictive insights")


class LearningInsightsResponse(BaseModel):
    """Response containing learning analytics insights."""
    user_id: int = Field(..., description="User identifier")
    time_period_days: int = Field(..., description="Analysis time period")
    engagement_summary: Dict[str, Any] = Field(default_factory=dict, description="Engagement summary")
    learning_progress: Dict[str, Any] = Field(default_factory=dict, description="Learning progress metrics")
    behavioral_patterns: List[str] = Field(default_factory=list, description="Identified behavioral patterns")
    strengths: List[str] = Field(default_factory=list, description="Identified learning strengths")
    areas_for_improvement: List[str] = Field(default_factory=list, description="Areas needing improvement")
    personalized_recommendations: List[str] = Field(default_factory=list, description="Personalized recommendations")
    predictions: Optional[Dict[str, Any]] = Field(None, description="Predictive insights")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Report generation timestamp")


# Batch Processing Schemas
class BatchAnalysisRequest(BaseModel):
    """Request for batch analysis of multiple users."""
    user_ids: List[int] = Field(..., min_items=1, max_items=100, description="List of user IDs to analyze")
    analysis_type: str = Field(..., description="Type of batch analysis")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Analysis parameters")


class BatchAnalysisResponse(BaseModel):
    """Response from batch analysis."""
    total_users: int = Field(..., description="Total number of users analyzed")
    successful_analyses: int = Field(..., description="Number of successful analyses")
    failed_analyses: int = Field(..., description="Number of failed analyses")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="Analysis results per user")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Errors encountered")
    processing_time_seconds: float = Field(..., description="Total processing time")
    started_at: datetime = Field(..., description="Batch processing start time")
    completed_at: datetime = Field(..., description="Batch processing completion time")


# ============================================================================
# CURRICULUM AGENT SCHEMAS
# ============================================================================

class CourseOutlineRequest(BaseModel):
    """Request to generate a course outline."""
    title: str = Field(..., min_length=3, max_length=200, description="Course title")
    description: str = Field(..., min_length=20, max_length=2000, description="Course description")
    target_audience: str = Field(..., min_length=5, max_length=500, description="Target audience description")
    learning_objectives: List[str] = Field(..., min_items=1, max_items=10, description="Learning objectives")
    difficulty_level: str = Field(..., description="Course difficulty level")
    estimated_duration_hours: int = Field(..., ge=1, le=500, description="Estimated course duration in hours")


class CourseOutlineResponse(BaseModel):
    """Response with course outline generation task status."""
    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Task status")
    user_id: int = Field(..., description="User ID")
    timestamp: datetime = Field(..., description="Timestamp")
    # UX enhancements for loading phase
    estimated_seconds: Optional[int] = Field(None, description="Estimated time until result is ready")
    ad: Optional[dict] = Field(None, description="Optional ad card to show during waiting")
    skip_available_after: Optional[int] = Field(None, description="Seconds after which user can skip the ad")


class LessonContentRequest(BaseModel):
    """Request to generate lesson content."""
    course_id: int = Field(..., description="Parent course ID")
    lesson_title: str = Field(..., min_length=3, max_length=200, description="Lesson title")
    lesson_description: str = Field(..., min_length=20, max_length=1000, description="Lesson description")
    learning_objectives: List[str] = Field(..., min_items=1, max_items=5, description="Learning objectives")
    content_type: str = Field(..., description="Type of lesson content")
    difficulty_level: str = Field(..., description="Lesson difficulty level")


class LessonContentResponse(BaseModel):
    """Response with lesson content generation task status."""
    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Task status")
    course_id: int = Field(..., description="Course ID")
    lesson_title: str = Field(..., description="Lesson title")
    user_id: int = Field(..., description="User ID")
    timestamp: datetime = Field(..., description="Timestamp")
    # UX enhancements for loading phase
    estimated_seconds: Optional[int] = Field(None, description="Estimated time until result is ready")
    ad: Optional[dict] = Field(None, description="Optional ad card to show during waiting")
    skip_available_after: Optional[int] = Field(None, description="Seconds after which user can skip the ad")


# ============================================================================
# CURATION AGENT SCHEMAS
# ============================================================================

class ContentEvaluationRequest(BaseModel):
    """Request to evaluate content quality."""
    content_text: str = Field(..., min_length=50, description="Content to evaluate")
    content_type: str = Field(..., description="Type of content")
    topic: str = Field(..., min_length=3, max_length=100, description="Content topic")
    target_audience: Optional[str] = Field(None, description="Target audience description")
    difficulty_level: Optional[str] = Field(None, description="Content difficulty level")


class ContentEvaluationResponse(BaseModel):
    """Response with content evaluation task status."""
    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Task status")
    topic: str = Field(..., description="Content topic")
    content_type: str = Field(..., description="Content type")
    user_id: int = Field(..., description="User ID")
    timestamp: datetime = Field(..., description="Timestamp")


class ContentTaggingRequest(BaseModel):
    """Request to tag and categorize content."""
    content_text: str = Field(..., min_length=50, description="Content to tag")
    content_type: str = Field(..., description="Type of content")
    content_title: Optional[str] = Field(None, description="Content title")


class ContentTaggingResponse(BaseModel):
    """Response with content tagging task status."""
    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Task status")
    content_title: Optional[str] = Field(None, description="Content title")
    content_type: str = Field(..., description="Content type")
    user_id: int = Field(..., description="User ID")
    timestamp: datetime = Field(..., description="Timestamp")


class ContentGapsRequest(BaseModel):
    """Request to identify content gaps in a course."""
    course_id: int = Field(..., description="Course ID")


class ContentGapsResponse(BaseModel):
    """Response with content gaps analysis task status."""
    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Task status")
    course_id: int = Field(..., description="Course ID")
    user_id: int = Field(..., description="User ID")
    timestamp: datetime = Field(..., description="Timestamp")
