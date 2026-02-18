"""
Chat Module Schemas

Pydantic schemas for chat requests and responses.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict

from lyo_app.chat.models import ChatMode, ChipAction, CTAType
from lyo_app.core.lyo_protocol import LyoBlock


# =============================================================================
# REQUEST SCHEMAS
# =============================================================================

class ConversationHistoryItem(BaseModel):
    """Single message in conversation history"""
    role: str = Field(..., description="Message role: system, user, or assistant")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """
    Main chat request schema with mode_hint and action support.
    
    The mode_hint allows the client to suggest which agent path to use,
    while the action field enables chip actions like "practice" or "take_note".
    """
    message: str = Field(..., min_length=1, max_length=10000, description="User's message")
    
    # Mode and routing
    mode_hint: Optional[str] = Field(
        None,
        description="Suggested mode: quick_explainer, course_planner, practice, note_taker, general"
    )
    action: Optional[str] = Field(
        None,
        description="Chip action: practice, take_note, explain_more, quiz_me, create_course, summarize"
    )
    
    # Context
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID to continue")
    session_id: Optional[str] = Field(None, description="Client session ID for tracking")
    conversation_history: Optional[List[ConversationHistoryItem]] = Field(
        None, description="Previous messages for context"
    )
    context: Optional[str] = Field(None, description="Additional context (topic, course, etc.)")
    
    # Resource references
    resource_id: Optional[str] = Field(None, description="Related resource ID")
    course_id: Optional[str] = Field(None, description="Related course ID")
    note_id: Optional[str] = Field(None, description="Related note ID")
    
    # Options
    include_ctas: bool = Field(True, description="Include call-to-action suggestions")
    include_chips: bool = Field(True, description="Include chip action suggestions")
    max_tokens: Optional[int] = Field(None, ge=50, le=4000, description="Max response tokens")


class QuickExplainerRequest(BaseModel):
    """Request for quick explanations"""
    topic: str = Field(..., min_length=1, max_length=500, description="Topic to explain")
    depth: str = Field("brief", description="Explanation depth: brief, moderate, detailed")
    context: Optional[str] = Field(None, description="Additional context")
    conversation_history: Optional[List[ConversationHistoryItem]] = Field(None)


class CoursePlannerRequest(BaseModel):
    """Request for course planning"""
    topic: str = Field(..., min_length=1, max_length=500, description="Course topic")
    goal: Optional[str] = Field(None, description="Learning goal")
    time_available: Optional[str] = Field(None, description="Available time for learning")
    current_level: str = Field("beginner", description="Current knowledge level")
    preferences: Optional[Dict[str, Any]] = Field(None, description="Learning preferences")


class PracticeRequest(BaseModel):
    """Request for practice/quiz generation"""
    topic: str = Field(..., description="Topic to practice")
    difficulty: str = Field("intermediate", description="Difficulty level")
    question_count: int = Field(5, ge=1, le=20, description="Number of questions")
    question_types: Optional[List[str]] = Field(None, description="Types: multiple_choice, true_false, open_ended")
    focus_areas: Optional[List[str]] = Field(None, description="Specific areas to focus on")


class NoteRequest(BaseModel):
    """Request for note taking"""
    content: str = Field(..., description="Content to take note from")
    title: Optional[str] = Field(None, description="Note title")
    conversation_id: Optional[str] = Field(None, description="Source conversation")
    extract_key_points: bool = Field(True, description="Extract key points automatically")


class CTAClickRequest(BaseModel):
    """Record a CTA click event"""
    cta_id: str = Field(..., description="CTA identifier")
    cta_type: str = Field(..., description="CTA type")
    message_id: Optional[str] = Field(None)
    conversation_id: Optional[str] = Field(None)
    session_id: Optional[str] = Field(None)


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================

class CTAItem(BaseModel):
    """Call-to-action item in response"""
    id: str = Field(..., description="Unique CTA identifier")
    type: str = Field(..., description="CTA type")
    label: str = Field(..., description="Display label")
    action: str = Field(..., description="Action to perform")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional action data")
    priority: int = Field(0, ge=0, le=10, description="Display priority")


class ChipActionItem(BaseModel):
    """Chip action suggestion"""
    id: str = Field(..., description="Chip identifier")
    action: str = Field(..., description="Action key")
    label: str = Field(..., description="Display label")
    icon: Optional[str] = Field(None, description="Icon name")


class QuickExplainerData(BaseModel):
    """Quick explainer embedded data for iOS"""
    explanation: str = Field(..., description="The explanation")
    key_points: List[str] = Field(default_factory=list, description="Key takeaways")
    related_topics: List[str] = Field(default_factory=list, description="Related topics to explore")


class CourseProposalData(BaseModel):
    """Course proposal embedded data for iOS"""
    course_id: str = Field(..., description="Generated course ID")
    title: str = Field(..., description="Course title")
    description: str = Field(..., description="Course description")
    estimated_hours: float = Field(..., description="Estimated completion time")
    module_count: int = Field(..., description="Number of modules")
    learning_objectives: List[str] = Field(default_factory=list)


class StudySession(BaseModel):
    """A scheduled study session"""
    id: str
    title: str
    description: str
    topic: str
    start_time: Optional[datetime] = None
    duration_minutes: int
    activity_type: str = Field(..., description="study, review, quiz, practice")


class TestPrepData(BaseModel):
    """Test prep embedded data for iOS"""
    plan_id: str
    title: str
    sessions: List[StudySession]
    total_sessions: int
    test_date: Optional[datetime]


class StudyPlanResponse(BaseModel):
    """Response for test prep study plan"""
    plan_id: str
    title: str
    test_date: Optional[datetime] = None
    sessions: List[StudySession]
    ctas: List[CTAItem] = Field(default_factory=list)
# =============================================================================
# A2UI OPEN_CLASSROOM SCHEMAS
# =============================================================================

class OpenClassroomCourse(BaseModel):
    """Course data for OPEN_CLASSROOM A2UI payload"""
    id: Optional[str] = Field(None, description="Course ID")
    title: str = Field(..., description="Course title")
    topic: str = Field(..., description="Course topic")
    level: str = Field("intermediate", description="Difficulty level")
    duration: Optional[str] = Field("~45 min", description="Estimated duration")
    objectives: List[str] = Field(default_factory=list, description="Learning objectives")


class OpenClassroomPayload(BaseModel):
    """Payload for OPEN_CLASSROOM A2UI command - triggers classroom navigation in iOS"""
    course: OpenClassroomCourse


class ChatResponse(BaseModel):
    """Main chat response schema - iOS compatible"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,  # Allow both field name and alias
        serialize_by_alias=True  # Serialize using camelCase aliases for iOS
    )
    
    # Core response
    response: str = Field(..., description="AI response text")
    message_id: str = Field(..., serialization_alias="messageId", description="Message ID for tracking")
    conversation_id: str = Field(..., serialization_alias="conversationId", description="Conversation ID")
    
    # Mode info (iOS: responseMode)
    mode_used: str = Field(..., serialization_alias="responseMode", description="Agent mode that handled the request")
    mode_confidence: Optional[float] = Field(None, serialization_alias="modeConfidence", description="Confidence in mode selection")
    
    # Embedded payloads for iOS rendering
    quick_explainer: Optional[QuickExplainerData] = Field(
        None, serialization_alias="quickExplainer", description="Quick explainer data when mode is 'quick_explain'"
    )
    course_proposal: Optional[CourseProposalData] = Field(
        None, serialization_alias="courseProposal", description="Course proposal data when mode is 'course_plan'"
    )
    study_plan: Optional[TestPrepData] = Field(
        None, serialization_alias="studyPlan", description="Study plan data when mode is 'test_prep'"
    )
    content_types: Optional[List[Dict[str, Any]]] = Field(
        None, serialization_alias="contentTypes", description="A2UI content widgets"
    )
    
    # Lyo Protocol Support (The Future)
    lyo_blocks: Optional[List[LyoBlock]] = Field(
        None, serialization_alias="lyoBlocks", description="Lyo Protocol Blocks"
    )

    # Full A2UI Component Support
    ui_component: Optional[Dict[str, Any]] = Field(
        None, serialization_alias="uiComponent", description="Complete A2UI component tree"
    )

    # A2UI Command fields (for OPEN_CLASSROOM, etc.)
    type: Optional[str] = Field(None, description="A2UI action type (e.g., 'OPEN_CLASSROOM')")
    payload: Optional[OpenClassroomPayload] = Field(None, description="A2UI payload for classroom navigation")
    
    # Updated history
    conversation_history: List[ConversationHistoryItem] = Field(
        default_factory=list, serialization_alias="conversationHistory", description="Updated conversation history"
    )
    
    # CTAs and chips (iOS: chips for suggestion chips)
    ctas: List[CTAItem] = Field(default_factory=list, description="Call-to-action suggestions")
    chip_actions: List[ChipActionItem] = Field(default_factory=list, serialization_alias="chips", description="Quick action chips")
    
    # Metadata
    tokens_used: Optional[int] = Field(None, serialization_alias="tokensUsed", description="Tokens consumed")
    cache_hit: bool = Field(False, serialization_alias="cacheHit", description="Whether response was cached")
    latency_ms: Optional[int] = Field(None, serialization_alias="latencyMs", description="Response latency")
    
    # Generated content references
    generated_course_id: Optional[str] = Field(None, serialization_alias="generatedCourseId", description="ID of generated course, if any")
    generated_note_id: Optional[str] = Field(None, serialization_alias="generatedNoteId", description="ID of generated note, if any")


class QuickExplainerResponse(BaseModel):
    """Response for quick explanations"""
    explanation: str = Field(..., description="The explanation")
    key_points: List[str] = Field(default_factory=list, description="Key takeaways")
    related_topics: List[str] = Field(default_factory=list, description="Related topics to explore")
    ctas: List[CTAItem] = Field(default_factory=list)
    chip_actions: List[ChipActionItem] = Field(default_factory=list)


class CourseModule(BaseModel):
    """Course module structure"""
    id: str
    title: str
    description: str
    lessons: List[Dict[str, Any]]
    estimated_minutes: int


class CoursePlannerResponse(BaseModel):
    """Response for course planning"""
    course_id: str = Field(..., description="Generated course ID")
    title: str = Field(..., description="Course title")
    description: str = Field(..., description="Course description")
    modules: List[CourseModule] = Field(..., description="Course modules")
    estimated_hours: float = Field(..., description="Estimated completion time")
    learning_objectives: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    ctas: List[CTAItem] = Field(default_factory=list)


class PracticeQuestion(BaseModel):
    """Practice question"""
    id: str
    question: str
    question_type: str
    options: Optional[List[str]] = None
    correct_answer: str
    explanation: str
    difficulty: str


class PracticeResponse(BaseModel):
    """Response for practice requests"""
    quiz_id: str = Field(..., description="Quiz ID")
    topic: str = Field(..., description="Quiz topic")
    questions: List[PracticeQuestion] = Field(..., description="Practice questions")
    total_questions: int
    estimated_time_minutes: int
    ctas: List[CTAItem] = Field(default_factory=list)


class NoteResponse(BaseModel):
    """Response for note creation"""
    note_id: str = Field(..., description="Created note ID")
    title: str = Field(..., description="Note title")
    content: str = Field(..., description="Note content")
    summary: Optional[str] = Field(None, description="AI-generated summary")
    key_points: List[str] = Field(default_factory=list, description="Extracted key points")
    tags: List[str] = Field(default_factory=list, description="Suggested tags")
    ctas: List[CTAItem] = Field(default_factory=list)


# =============================================================================
# TELEMETRY SCHEMAS
# =============================================================================

class TelemetryStatsResponse(BaseModel):
    """Telemetry statistics response"""
    by_mode: Dict[str, Dict[str, Any]] = Field(..., description="Stats grouped by mode")
    totals: Dict[str, Any] = Field(..., description="Aggregate totals")
    cta_clicks: Dict[str, int] = Field(default_factory=dict, description="CTA click counts")
    period_start: Optional[datetime] = Field(None)
    period_end: Optional[datetime] = Field(None)


# =============================================================================
# COURSE SCHEMAS
# =============================================================================

class ChatCourseRead(BaseModel):
    """Schema for reading chat course data"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    user_id: Optional[str]
    title: str
    description: Optional[str]
    topic: str
    difficulty: str
    modules: Optional[List[Dict]] = None
    learning_objectives: Optional[List[str]] = None
    prerequisites: Optional[List[str]] = None
    estimated_hours: Optional[float]
    is_published: bool
    created_at: datetime
    updated_at: datetime


class ChatCourseCreate(BaseModel):
    """Schema for creating a chat course"""
    title: str = Field(..., min_length=1, max_length=500)
    topic: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    difficulty: str = Field("intermediate")
    modules: Optional[List[Dict]] = None
    learning_objectives: Optional[List[str]] = None
    prerequisites: Optional[List[str]] = None
    estimated_hours: Optional[float] = None


# =============================================================================
# NOTE SCHEMAS
# =============================================================================

class ChatNoteRead(BaseModel):
    """Schema for reading chat note data"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    user_id: str
    title: str
    content: str
    summary: Optional[str]
    topic: Optional[str]
    tags: Optional[List[str]]
    note_type: str
    importance: int
    is_favorite: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ChatNoteCreate(BaseModel):
    """Schema for creating a chat note"""
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    topic: Optional[str] = None
    tags: Optional[List[str]] = None
    note_type: str = Field("general")
    importance: int = Field(0, ge=0, le=5)


class ChatNoteUpdate(BaseModel):
    """Schema for updating a chat note"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = Field(None, min_length=1)
    topic: Optional[str] = None
    tags: Optional[List[str]] = None
    note_type: Optional[str] = None
    importance: Optional[int] = Field(None, ge=0, le=5)
    is_favorite: Optional[bool] = None


class GreetingResponse(BaseModel):
    """Response for proactive greeting"""
    greeting: str = Field(..., description="The generated greeting message")
    context_used: bool = Field(False, description="Whether personalized context was used")
    suggestions: list[str] = Field(
        default=["Teach me something new", "Create a course", "Quiz me on a topic"],
        description="Suggestion chips to show after the greeting"
    )
