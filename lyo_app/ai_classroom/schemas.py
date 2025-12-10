"""
AI Classroom Schemas - Pydantic Models for API Validation

These schemas define the API contracts for the Interactive Cinema + Adaptive Tutor system.
They ensure type safety and validation at the API boundary.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator


# =============================================================================
# ENUMS (Mirror of SQLAlchemy enums for API)
# =============================================================================

class NodeTypeEnum(str, Enum):
    NARRATIVE = "narrative"
    INTERACTION = "interaction"
    REMEDIATION = "remediation"
    SUMMARY = "summary"
    REVIEW = "review"
    HOOK = "hook"
    TRANSITION = "transition"


class EdgeConditionEnum(str, Enum):
    ALWAYS = "always"
    PASS = "pass"
    FAIL = "fail"
    MASTERY_LOW = "mastery_low"
    MASTERY_HIGH = "mastery_high"
    OPTIONAL = "optional"


class InteractionTypeEnum(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SLIDER = "slider"
    DRAG_MATCH = "drag_match"
    SHORT_ANSWER = "short_answer"
    PREDICTION = "prediction"


class AssetTierEnum(str, Enum):
    HERO = "hero"
    STOCK = "stock"
    ABSTRACT = "abstract"


# =============================================================================
# SCENE CONTENT SCHEMAS (The "Script" structure)
# =============================================================================

class NarrativeContent(BaseModel):
    """Content payload for narrative nodes (the cinema part)"""
    narration: str = Field(..., description="The spoken script (TTS input)")
    visual_prompt: str = Field(..., description="DALL-E/Stable Diffusion prompt")
    keywords: List[str] = Field(default_factory=list, description="Key terms to highlight")
    audio_mood: str = Field(default="calm", description="Background audio mood")
    duration_hint: float = Field(default=10.0, description="Estimated seconds")


class InteractionOption(BaseModel):
    """A single option in an interaction"""
    id: str = Field(..., description="Unique option ID")
    label: str = Field(..., description="Display text")
    is_correct: bool = Field(..., description="Whether this is the correct answer")
    feedback: str = Field(..., description="Feedback shown when selected")
    misconception_tag: Optional[str] = Field(None, description="Tag if this reveals a misconception")


class InteractionContent(BaseModel):
    """Content payload for interaction nodes (knowledge checks)"""
    prompt: str = Field(..., description="The question/challenge")
    interaction_type: InteractionTypeEnum = Field(..., description="UI type to render")
    options: List[InteractionOption] = Field(..., description="Answer options")
    explanation: Optional[str] = Field(None, description="Explanation shown after answering")
    visual_prompt: Optional[str] = Field(None, description="Optional background image prompt")
    time_limit_seconds: Optional[int] = Field(None, description="Optional time limit")


class RemediationContent(BaseModel):
    """Content payload for remediation nodes"""
    original_concept: str = Field(..., description="What the user struggled with")
    new_analogy: str = Field(..., description="A different way to explain it")
    narration: str = Field(..., description="The spoken remediation script")
    visual_prompt: str = Field(..., description="Visual for the new analogy")
    follow_up_check: Optional[InteractionContent] = Field(None, description="Quick re-check after remediation")


# =============================================================================
# NODE SCHEMAS
# =============================================================================

class LearningNodeBase(BaseModel):
    """Base schema for learning nodes"""
    node_type: NodeTypeEnum
    content: Dict[str, Any] = Field(..., description="Type-specific content payload")
    objective_id: Optional[str] = None
    concept_id: Optional[str] = None
    estimated_seconds: int = Field(default=15)
    asset_tier: AssetTierEnum = Field(default=AssetTierEnum.ABSTRACT)
    sequence_order: int = Field(default=0)


class LearningNodeCreate(LearningNodeBase):
    """Schema for creating a learning node"""
    course_id: str
    prerequisites: List[str] = Field(default_factory=list)
    interaction_type: Optional[InteractionTypeEnum] = None
    skill_type: Optional[str] = None
    misconception_tags: List[str] = Field(default_factory=list)


class LearningNodeRead(LearningNodeBase):
    """Schema for reading a learning node"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    course_id: str
    generated_asset_url: Optional[str] = None
    generated_audio_url: Optional[str] = None
    created_at: datetime


class LearningNodeWithAssets(LearningNodeRead):
    """Node with hydrated assets for playback"""
    image_url: Optional[str] = None  # Resolved from generated_asset_url or visual_prompt
    audio_url: Optional[str] = None  # TTS audio URL
    is_asset_ready: bool = False


# =============================================================================
# EDGE SCHEMAS
# =============================================================================

class LearningEdgeBase(BaseModel):
    """Base schema for learning edges"""
    from_node_id: str
    to_node_id: str
    condition: EdgeConditionEnum = Field(default=EdgeConditionEnum.ALWAYS)
    mastery_threshold: Optional[float] = None
    weight: float = Field(default=1.0)


class LearningEdgeCreate(LearningEdgeBase):
    """Schema for creating an edge"""
    course_id: str


class LearningEdgeRead(LearningEdgeBase):
    """Schema for reading an edge"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    course_id: str


# =============================================================================
# COURSE SCHEMAS
# =============================================================================

class CourseBase(BaseModel):
    """Base course schema"""
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    subject: str = Field(..., max_length=100)
    grade_band: Optional[str] = None
    visual_theme: str = Field(default="modern")
    audio_mood: str = Field(default="calm")
    estimated_minutes: int = Field(default=30)
    difficulty: str = Field(default="intermediate")
    learning_objectives: List[str] = Field(default_factory=list)


class CourseCreate(CourseBase):
    """Schema for creating a course"""
    source_intent: Optional[str] = None
    source_conversation_id: Optional[str] = None


class CourseRead(CourseBase):
    """Schema for reading a course"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    entry_node_id: Optional[str] = None
    is_published: bool
    is_template: bool
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CourseWithGraph(CourseRead):
    """Course with full graph structure"""
    nodes: List[LearningNodeRead] = Field(default_factory=list)
    edges: List[LearningEdgeRead] = Field(default_factory=list)


# =============================================================================
# GENERATION SCHEMAS (Planner → Producer Pipeline)
# =============================================================================

class CourseGenerationRequest(BaseModel):
    """Request to generate a new course"""
    topic: str = Field(..., min_length=3, max_length=500)
    user_intent: str = Field(..., min_length=10, max_length=2000)
    difficulty: str = Field(default="intermediate")
    target_minutes: int = Field(default=30, ge=5, le=120)
    visual_theme: Optional[str] = None
    include_interactions: bool = Field(default=True)
    interaction_frequency: int = Field(default=3, ge=1, le=10, description="Scenes between interactions")


class PlannerOutput(BaseModel):
    """Output from the Planner agent"""
    title: str
    description: str
    visual_theme: str
    audio_mood: str
    estimated_minutes: int
    modules: List[Dict[str, Any]]  # High-level module outlines
    learning_objectives: List[str]
    interaction_strategy: str  # How often to quiz


class ProducerOutput(BaseModel):
    """Output from the Producer agent"""
    nodes: List[LearningNodeCreate]
    edges: List[LearningEdgeCreate]
    entry_node_id: str


class GenerationProgress(BaseModel):
    """Progress update during course generation"""
    stage: str  # planning, producing_module_1, generating_assets, etc.
    progress_percent: float
    current_step: str
    estimated_seconds_remaining: Optional[float] = None


# =============================================================================
# PLAYBACK SCHEMAS (Interactive Cinema Player)
# =============================================================================

class PlaybackState(BaseModel):
    """Current playback state for a user in a course"""
    course_id: str
    current_node_id: str
    current_node: LearningNodeWithAssets
    next_nodes: List[LearningNodeRead] = Field(default_factory=list, description="Upcoming nodes for pre-loading")
    completed_nodes: List[str] = Field(default_factory=list)
    progress_percent: float
    total_time_seconds: int
    can_go_back: bool
    is_at_interaction: bool


class PlaybackAdvanceRequest(BaseModel):
    """Request to advance to the next node"""
    course_id: str
    current_node_id: str
    direction: str = Field(default="next", pattern="^(next|back)$")


class InteractionSubmitRequest(BaseModel):
    """Request to submit an interaction response"""
    course_id: str
    node_id: str
    answer_id: str
    time_taken_seconds: float


class InteractionSubmitResponse(BaseModel):
    """Response after submitting an interaction"""
    is_correct: bool
    feedback: str
    mastery_update: float  # Change in mastery score
    next_node_id: str  # Could be next in sequence, or remediation
    show_celebration: bool
    celebration_config: Optional[Dict[str, Any]] = None
    show_ad: bool
    ad_config: Optional[Dict[str, Any]] = None


# =============================================================================
# REMEDIATION SCHEMAS
# =============================================================================

class RemediationRequest(BaseModel):
    """Request for on-demand remediation"""
    course_id: str
    node_id: str  # The node the user struggled with
    user_complaint: Optional[str] = None  # "I don't understand"
    misconception_tag: Optional[str] = None


class RemediationResponse(BaseModel):
    """Response with generated remediation"""
    remediation_node: LearningNodeWithAssets
    remaining_budget: int  # How many more remediation attempts allowed
    original_node_id: str


# =============================================================================
# MASTERY SCHEMAS
# =============================================================================

class MasteryStateRead(BaseModel):
    """User's mastery of a concept"""
    model_config = ConfigDict(from_attributes=True)
    
    concept_id: Optional[str] = None
    objective_id: Optional[str] = None
    mastery_score: float
    confidence: float
    attempts: int
    correct_count: int
    trend: str
    last_seen: Optional[datetime] = None


class MasteryDashboard(BaseModel):
    """Overview of user's mastery across concepts"""
    user_id: str
    overall_mastery: float
    concepts: List[MasteryStateRead]
    weak_areas: List[str]
    strong_areas: List[str]
    next_review_count: int
    streak_days: int


# =============================================================================
# REVIEW SCHEMAS (Spaced Repetition)
# =============================================================================

class ReviewItem(BaseModel):
    """A single item in the review queue"""
    node_id: str
    concept_name: str
    last_reviewed_at: Optional[datetime]
    interval_days: int
    streak: int
    priority: float  # Higher = more urgent


class ReviewQueueResponse(BaseModel):
    """Today's review queue"""
    user_id: str
    total_items: int
    estimated_minutes: int
    items: List[ReviewItem]


class ReviewSubmitRequest(BaseModel):
    """Submit a review response"""
    node_id: str
    quality: int = Field(..., ge=0, le=5, description="0=complete blank, 5=perfect recall")
    time_taken_seconds: float


class ReviewSubmitResponse(BaseModel):
    """Response after submitting a review"""
    next_review_date: datetime
    new_interval_days: int
    streak: int
    show_celebration: bool


# =============================================================================
# CELEBRATION & MONETIZATION SCHEMAS
# =============================================================================

class CelebrationTrigger(BaseModel):
    """Configuration for when to show celebrations"""
    trigger_type: str
    avatar_url: str
    animation_type: str = "confetti"
    sound_effect: Optional[str] = None
    message: str


class AdSlot(BaseModel):
    """Configuration for an ad placement"""
    placement_type: str
    ad_unit_id: str
    ad_format: str
    should_show: bool
    reason: Optional[str] = None  # Why ad is/isn't shown


# =============================================================================
# ANALYTICS SCHEMAS
# =============================================================================

class CourseAnalytics(BaseModel):
    """Analytics for a course"""
    course_id: str
    total_users: int
    completion_rate: float
    avg_time_minutes: float
    first_pass_success_rate: float
    remediation_trigger_rate: float
    next_day_recall_rate: Optional[float] = None
    drop_off_nodes: List[Dict[str, Any]]


class UserLearningAnalytics(BaseModel):
    """Analytics for a user"""
    user_id: str
    total_courses_started: int
    total_courses_completed: int
    total_time_minutes: int
    avg_mastery_score: float
    concepts_mastered: int
    current_streak_days: int
    next_day_recall_accuracy: float
