"""
Pydantic Schemas for AI Study Mode API
Request and response models for study sessions and quiz generation
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum

from .models import StudySessionStatus, MessageRole, QuizType


# ============================================================================
# STUDY SESSION SCHEMAS
# ============================================================================

class StudySessionRequest(BaseModel):
    """Request to start a new study session"""
    resource_id: str = Field(..., description="ID of the learning material")
    resource_title: Optional[str] = Field(None, description="Title of the resource")
    resource_type: Optional[str] = Field(None, description="Type of resource (video, article, etc.)")
    tutor_personality: str = Field("socratic", description="AI tutor personality")
    difficulty_level: Optional[str] = Field(None, description="Difficulty level of the material")
    learning_objectives: Optional[List[str]] = Field(None, description="Specific learning goals")

    @field_validator('tutor_personality')
    def validate_personality(cls, v):
        allowed = ['socratic', 'encouraging', 'challenging', 'patient', 'direct']
        if v not in allowed:
            raise ValueError(f'Tutor personality must be one of: {", ".join(allowed)}')
        return v


class StudySessionCreateRequest(BaseModel):
    """Enhanced request to create a new AI-powered study session"""
    resource_id: str = Field(..., description="ID of the learning material")
    resource_type: str = Field(default="lesson", description="Type of resource (course, lesson, topic)")
    tutoring_style: str = Field(default="socratic", description="Tutoring approach (socratic, collaborative, explanatory, practical)")
    
    @field_validator('tutoring_style')
    def validate_tutoring_style(cls, v):
        valid_styles = ["socratic", "collaborative", "explanatory", "practical"]
        if v not in valid_styles:
            raise ValueError(f"tutoring_style must be one of: {valid_styles}")
        return v


class StudySessionCreateResponse(BaseModel):
    """Enhanced response from creating an AI study session"""
    session_id: int
    resource_title: str
    welcome_message: str
    conversation_history: List[Dict[str, Any]]
    tutoring_style: str
    difficulty_level: str
    subject_area: str


class ConversationMessage(BaseModel):
    """A single message in the conversation history"""
    role: MessageRole = Field(..., description="Role of the message sender")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = Field(None, description="When the message was sent")
    token_count: Optional[int] = Field(None, description="Number of tokens in the message")


class StudySessionContinueRequest(BaseModel):
    """Enhanced request to continue an AI study session"""
    user_input: str = Field(..., description="The user's latest message")
    conversation_history: Optional[List[ConversationMessage]] = Field(
        None, 
        description="The entire chat history (optional, will use cached if not provided)"
    )


class StudySessionContinueResponse(BaseModel):
    """Enhanced response from continuing an AI study session"""
    response: str = Field(..., description="The AI's guided response")
    updated_conversation_history: List[Dict[str, Any]] = Field(..., description="Complete updated conversation history")
    session_metadata: Dict[str, Any] = Field(..., description="Session analytics and metadata")
    tutoring_insights: Dict[str, Any] = Field(..., description="AI insights about the learning interaction")
    suggested_next_steps: List[str] = Field(..., description="Suggested next actions for the learner")





class StudyConversationRequest(BaseModel):
    """Request for AI study conversation"""
    resource_id: str = Field(..., description="ID of the learning material")
    conversation_history: List[ConversationMessage] = Field(
        default_factory=list, 
        description="The entire chat history"
    )
    user_input: str = Field(..., description="The user's latest message")
    session_id: Optional[str] = Field(None, description="Existing session ID (if continuing)")
    user_typing_time_ms: Optional[int] = Field(None, description="Time user spent typing")
    request_help: bool = Field(False, description="Whether user is requesting help")

    @field_validator('user_input')
    def validate_user_input(cls, v):
        if not v or not v.strip():
            raise ValueError('User input cannot be empty')
        if len(v) > 5000:
            raise ValueError('User input too long (max 5000 characters)')
        return v.strip()

    @field_validator('conversation_history')
    def validate_conversation_history(cls, v):
        if len(v) > 100:  # Reasonable limit for conversation length
            raise ValueError('Conversation history too long (max 100 messages)')
        return v


class StudyConversationResponse(BaseModel):
    """Response from AI study conversation"""
    session_id: str = Field(..., description="Study session ID")
    response: str = Field(..., description="The AI's guided response")
    updated_conversation_history: List[ConversationMessage] = Field(
        ..., description="The full history including the AI's new response"
    )
    ai_model_used: str = Field(..., description="AI model that generated the response")
    response_time_ms: int = Field(..., description="Time taken to generate response")
    token_count: int = Field(..., description="Number of tokens in the AI response")
    engagement_score: Optional[float] = Field(None, description="Estimated user engagement (0-1)")
    suggested_actions: Optional[List[str]] = Field(None, description="Suggested next actions")
    confidence_score: Optional[float] = Field(None, description="AI confidence in response (0-1)")


# ============================================================================
# QUIZ GENERATION SCHEMAS
# ============================================================================

class QuizGenerationRequest(BaseModel):
    """Request to generate a quiz"""
    resource_id: str = Field(..., description="ID of the learning material")
    quiz_type: QuizType = Field(default=QuizType.MULTIPLE_CHOICE, description="Type of quiz to generate")
    question_count: int = Field(default=5, description="Number of questions to generate")
    difficulty_level: Optional[str] = Field(None, description="Difficulty level (beginner, intermediate, advanced)")
    focus_topics: Optional[List[str]] = Field(None, description="Specific topics to focus on")
    exclude_topics: Optional[List[str]] = Field(None, description="Topics to avoid")
    session_id: Optional[str] = Field(None, description="Associated study session ID")

    @field_validator('question_count')
    def validate_question_count(cls, v):
        if v < 1 or v > 20:
            raise ValueError('Question count must be between 1 and 20')
        return v


class QuizQuestion(BaseModel):
    """A single quiz question"""
    id: Optional[str] = Field(None, description="Question ID")
    question: str = Field(..., description="The question text")
    question_type: str = Field(..., description="Type of question")
    options: Optional[List[str]] = Field(None, description="Answer options (for multiple choice)")
    correct_answer: Union[str, int, List[str]] = Field(..., description="The correct answer")
    explanation: Optional[str] = Field(None, description="Explanation of the correct answer")
    difficulty: Optional[str] = Field(None, description="Question difficulty level")
    topic: Optional[str] = Field(None, description="Topic/subject area")
    points: int = Field(default=1, description="Points awarded for correct answer")
    time_limit_seconds: Optional[int] = Field(None, description="Time limit for this question")

    @field_validator('question')
    def validate_question(cls, v):
        if not v or not v.strip():
            raise ValueError('Question cannot be empty')
        if len(v) > 1000:
            raise ValueError('Question too long (max 1000 characters)')
        return v.strip()


class QuizGenerationResponse(BaseModel):
    """Response from quiz generation"""
    quiz_id: str = Field(..., description="Generated quiz ID")
    title: str = Field(..., description="Quiz title")
    description: Optional[str] = Field(None, description="Quiz description")
    quiz_type: QuizType = Field(..., description="Type of quiz")
    question_count: int = Field(..., description="Number of questions")
    estimated_duration_minutes: int = Field(..., description="Estimated time to complete")
    difficulty_level: str = Field(..., description="Overall difficulty level")
    questions: List[QuizQuestion] = Field(..., description="Array of quiz questions")
    generation_metadata: Dict[str, Any] = Field(..., description="Metadata about quiz generation")


# ============================================================================
# QUIZ ATTEMPT SCHEMAS
# ============================================================================

class QuizAnswerSubmission(BaseModel):
    """A single answer submission"""
    question_id: str = Field(..., description="Question ID")
    user_answer: Union[str, int, List[str]] = Field(..., description="User's answer")
    time_taken_seconds: Optional[int] = Field(None, description="Time taken to answer")
    confidence_level: Optional[int] = Field(None, description="User confidence (1-5)")


class QuizAttemptRequest(BaseModel):
    """Request to start or submit a quiz attempt"""
    quiz_id: str = Field(..., description="Quiz ID")
    answers: List[QuizAnswerSubmission] = Field(..., description="User's answers")
    total_time_minutes: Optional[float] = Field(None, description="Total time taken")
    feedback: Optional[str] = Field(None, description="User feedback on the quiz")
    difficulty_rating: Optional[int] = Field(None, description="Difficulty rating (1-5)")
    enjoyment_rating: Optional[int] = Field(None, description="Enjoyment rating (1-5)")

    @field_validator('difficulty_rating', 'enjoyment_rating')
    def validate_ratings(cls, v):
        if v is not None and (v < 1 or v > 5):
            raise ValueError('Ratings must be between 1 and 5')
        return v


class QuizResultDetail(BaseModel):
    """Detailed result for a single question"""
    question_id: str = Field(..., description="Question ID")
    question: str = Field(..., description="The question text")
    user_answer: Union[str, int, List[str]] = Field(..., description="User's answer")
    correct_answer: Union[str, int, List[str]] = Field(..., description="Correct answer")
    is_correct: bool = Field(..., description="Whether the answer was correct")
    points_earned: int = Field(..., description="Points earned for this question")
    explanation: Optional[str] = Field(None, description="Explanation of the correct answer")
    time_taken_seconds: Optional[int] = Field(None, description="Time taken to answer")


class QuizAttemptResponse(BaseModel):
    """Response from quiz attempt submission"""
    attempt_id: str = Field(..., description="Quiz attempt ID")
    quiz_id: str = Field(..., description="Quiz ID")
    score: float = Field(..., description="Overall score (0-100)")
    correct_answers: int = Field(..., description="Number of correct answers")
    total_questions: int = Field(..., description="Total number of questions")
    percentage: float = Field(..., description="Percentage score")
    grade: str = Field(..., description="Letter grade or performance level")
    time_taken_minutes: float = Field(..., description="Total time taken")
    detailed_results: List[QuizResultDetail] = Field(..., description="Detailed results per question")
    performance_insights: Dict[str, Any] = Field(..., description="Performance analysis")
    recommended_actions: List[str] = Field(..., description="Recommended next steps")


# ============================================================================
# SESSION MANAGEMENT SCHEMAS
# ============================================================================

class StudySessionUpdate(BaseModel):
    """Update an existing study session"""
    status: Optional[StudySessionStatus] = Field(None, description="Session status")
    learning_objectives: Optional[List[str]] = Field(None, description="Updated learning objectives")
    user_feedback: Optional[str] = Field(None, description="User feedback on the session")


class StudySessionResponse(BaseModel):
    """Study session details response"""
    id: str = Field(..., description="Session ID")
    user_id: int = Field(..., description="User ID")
    resource_id: str = Field(..., description="Resource ID")
    resource_title: Optional[str] = Field(None, description="Resource title")
    resource_type: Optional[str] = Field(None, description="Resource type")
    status: StudySessionStatus = Field(..., description="Session status")
    started_at: datetime = Field(..., description="Session start time")
    last_activity_at: datetime = Field(..., description="Last activity time")
    completed_at: Optional[datetime] = Field(None, description="Session completion time")
    total_duration_minutes: int = Field(..., description="Total session duration")
    tutor_personality: str = Field(..., description="AI tutor personality")
    difficulty_level: Optional[str] = Field(None, description="Difficulty level")
    learning_objectives: Optional[List[str]] = Field(None, description="Learning objectives")
    message_count: int = Field(..., description="Number of messages exchanged")
    ai_response_count: int = Field(..., description="Number of AI responses")
    average_response_time: float = Field(..., description="Average AI response time")
    user_engagement_score: float = Field(..., description="User engagement score (0-1)")


# ============================================================================
# ANALYTICS SCHEMAS
# ============================================================================

class StudyAnalyticsResponse(BaseModel):
    """Study analytics summary"""
    user_id: int = Field(..., description="User ID")
    total_study_time_minutes: int = Field(..., description="Total study time")
    sessions_completed: int = Field(..., description="Sessions completed")
    average_engagement_score: float = Field(..., description="Average engagement score")
    topics_studied: List[str] = Field(..., description="Topics studied")
    learning_streak_days: int = Field(..., description="Current learning streak")
    quizzes_taken: int = Field(..., description="Number of quizzes taken")
    average_quiz_score: float = Field(..., description="Average quiz score")
    improvement_areas: List[str] = Field(..., description="Areas for improvement")
    achievements: List[str] = Field(..., description="Recent achievements")


# ============================================================================
# ERROR RESPONSE SCHEMAS
# ============================================================================

class StudyModeError(BaseModel):
    """Error response for study mode operations"""
    error_code: str = Field(..., description="Error code")
    error_message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    suggested_action: Optional[str] = Field(None, description="Suggested action to resolve the error")


# ============================================================================
# HEALTH CHECK SCHEMAS
# ============================================================================

class StudyModeHealthResponse(BaseModel):
    """Health check response for study mode services"""
    status: str = Field(..., description="Service status")
    ai_models_available: List[str] = Field(..., description="Available AI models")
    database_status: str = Field(..., description="Database connection status")
    active_sessions: int = Field(..., description="Number of active study sessions")
    total_sessions_today: int = Field(..., description="Total sessions created today")
    avg_response_time_ms: float = Field(..., description="Average AI response time")
    service_uptime_seconds: int = Field(..., description="Service uptime in seconds")


# ============================================================================
# ANSWER ANALYSIS SCHEMAS
# ============================================================================

class AnswerAnalysisRequest(BaseModel):
    """Request for answer analysis"""
    question: str = Field(..., description="The quiz question")
    correct_answer: str = Field(..., description="The correct answer")
    user_answer: str = Field(..., description="User's answer")


class AnswerAnalysisResponse(BaseModel):
    """Response for answer analysis"""
    feedback: str = Field(..., description="AI feedback")
    is_correct: bool = Field(..., description="Whether the answer is correct")
    partial_credit: Optional[float] = Field(None, description="Partial credit score (0-1)")
    suggestions: List[str] = Field(default_factory=list, description="Suggestions for improvement")
    related_concepts: List[str] = Field(default_factory=list, description="Related concepts to review")
