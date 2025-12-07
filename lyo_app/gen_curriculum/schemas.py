"""
Generative Curriculum Phase 2 Schemas for advanced content generation
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class ContentType(str, Enum):
    """Types of generated content"""
    PROBLEM = "problem"
    EXPLANATION = "explanation" 
    HINT = "hint"
    EXAMPLE = "example"
    ASSESSMENT = "assessment"
    LESSON = "lesson"
    QUIZ = "quiz"
    PROJECT = "project"
    SIMULATION = "simulation"
    GAME = "game"


class DifficultyLevel(str, Enum):
    """Content difficulty levels"""
    BEGINNER = "beginner"
    NOVICE = "novice" 
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class GenerationStatus(str, Enum):
    """Content generation status"""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"


class LearningObjective(BaseModel):
    """Individual learning objective"""
    id: str
    description: str
    skill_id: str
    mastery_threshold: float = Field(ge=0.0, le=1.0)
    assessment_method: str = "practice"
    prerequisites: List[str] = []


class ContentGenerationRequest(BaseModel):
    """Request to generate new content"""
    content_type: ContentType
    skill_id: str
    topic: str
    difficulty_level: float = Field(ge=0.0, le=1.0, description="Continuous difficulty scale")
    
    # Personalization context
    user_id: Optional[int] = None
    current_mastery: Optional[float] = None
    learning_style: Optional[str] = None
    affect_state: Optional[str] = None
    
    # Content specifications  
    learning_objectives: List[LearningObjective] = []
    target_duration_minutes: Optional[int] = None
    include_hints: bool = True
    include_explanations: bool = True
    
    # Generation parameters
    creativity_level: float = Field(default=0.7, ge=0.0, le=1.0)
    model_preference: Optional[str] = None
    quality_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    
    @field_validator('difficulty_level')
    def validate_difficulty(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError('Difficulty level must be between 0.0 and 1.0')
        return v


class GeneratedContentResponse(BaseModel):
    """Response with generated content"""
    id: int
    content_type: ContentType
    title: str
    description: Optional[str] = None
    
    # Generation metadata
    skill_id: str
    topic: str
    difficulty_level: float
    target_mastery: Optional[float] = None
    
    # Content data
    content_data: Dict[str, Any]
    metadata: Dict[str, Any]
    
    # Quality metrics
    quality_score: Optional[float] = None
    coherence_score: Optional[float] = None
    relevance_score: Optional[float] = None
    difficulty_accuracy: Optional[float] = None
    
    # Status
    status: GenerationStatus
    generation_time: Optional[float] = None
    
    # Usage stats
    usage_count: int = 0
    success_rate: Optional[float] = None
    feedback_score: Optional[float] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class LearningPathRequest(BaseModel):
    """Request to generate personalized learning path"""
    user_id: int
    learning_goals: List[str]
    target_skills: List[str]
    
    # Time constraints
    target_completion_days: Optional[int] = None
    daily_time_budget_minutes: Optional[int] = None
    
    # Personalization preferences
    preferred_content_types: List[ContentType] = []
    difficulty_preference: str = "adaptive"  # adaptive, gradual, challenging
    pacing_preference: str = "adaptive"  # adaptive, self_paced, scheduled
    
    # Learning style
    visual_preference: Optional[bool] = None
    audio_preference: Optional[bool] = None
    hands_on_preference: Optional[bool] = None
    
    # Existing knowledge
    existing_skills: Dict[str, float] = {}  # skill_id -> mastery_level
    skip_known_content: bool = True


class LearningActivity(BaseModel):
    """Individual activity within a learning path"""
    id: str
    title: str
    description: str
    activity_type: str
    content_id: Optional[int] = None
    
    # Requirements
    prerequisites: List[str] = []
    min_mastery_required: float = 0.0
    
    # Timing
    estimated_duration_minutes: int
    max_attempts: int = 3
    time_limit_minutes: Optional[int] = None
    
    # Success criteria
    success_criteria: Dict[str, Any]
    mastery_threshold: float = 0.8
    
    # Adaptation
    hint_availability: Dict[str, Any] = {}
    failure_strategies: List[str] = []
    
    # Tracking
    is_optional: bool = False
    is_checkpoint: bool = False


class LearningPathResponse(BaseModel):
    """Generated learning path"""
    id: int
    title: str
    description: str
    
    # Path configuration
    user_id: int
    target_skills: List[str]
    learning_objectives: List[LearningObjective]
    estimated_duration_hours: float
    
    # Path structure
    activities: List[LearningActivity]
    checkpoints: List[Dict[str, Any]]
    branching_logic: Dict[str, Any]
    
    # Adaptation parameters
    adaptation_rules: Dict[str, Any]
    fallback_strategies: List[str]
    
    # Tracking
    current_position: int = 0
    completion_percentage: float = 0.0
    
    # Quality metrics
    effectiveness_score: Optional[float] = None
    customization_level: float
    
    # Status
    is_active: bool = True
    version: str = "1.0"
    
    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class ContentFeedbackRequest(BaseModel):
    """Learner feedback on content"""
    content_id: int
    user_id: int
    
    # Ratings (1-5 scale)
    overall_rating: int = Field(ge=1, le=5)
    difficulty_rating: int = Field(ge=1, le=5)
    clarity_rating: int = Field(ge=1, le=5) 
    usefulness_rating: int = Field(ge=1, le=5)
    engagement_rating: int = Field(ge=1, le=5)
    
    # Text feedback
    feedback_text: Optional[str] = None
    suggestions: Optional[str] = None
    
    # Interaction context
    time_spent_seconds: float
    attempts_made: int
    hints_used: int
    success: bool
    
    # Learning context
    mastery_before: Optional[float] = None
    mastery_after: Optional[float] = None
    affect_before: Optional[str] = None
    affect_after: Optional[str] = None


class PathAdaptationRequest(BaseModel):
    """Request to adapt learning path"""
    learning_path_id: int
    user_id: int
    
    # Trigger information
    trigger_reason: str
    trigger_data: Dict[str, Any]
    
    # Current context
    current_performance: Dict[str, Any]
    current_affect: Optional[str] = None
    current_mastery_levels: Dict[str, float]
    
    # Adaptation preferences
    adaptation_types: List[str] = ["difficulty", "pacing", "content_type"]
    preserve_learning_objectives: bool = True


class PathAdaptationResponse(BaseModel):
    """Response with path adaptation details"""
    adaptation_id: int
    learning_path_id: int
    adaptation_type: str
    
    # Changes made
    changes_made: Dict[str, Any]
    previous_state: Dict[str, Any]
    new_state: Dict[str, Any]
    
    # Reasoning
    trigger_reason: str
    adaptation_rationale: str
    
    # Expected impact
    expected_improvement: Dict[str, Any]
    success_probability: float
    
    # Timestamps
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class ContentQualityMetrics(BaseModel):
    """Content quality assessment metrics"""
    content_id: int
    
    # Automated scores (0.0-1.0)
    quality_score: float
    coherence_score: float
    relevance_score: float
    difficulty_accuracy: float
    engagement_score: float
    
    # Usage metrics
    usage_count: int
    success_rate: float
    average_time_spent: float
    completion_rate: float
    
    # Feedback metrics
    average_rating: Optional[float] = None
    feedback_count: int = 0
    positive_feedback_percentage: float = 0.0
    
    # Effectiveness metrics
    learning_gain_average: float = 0.0
    mastery_improvement_rate: float = 0.0
    retention_rate: Optional[float] = None
    
    # Last updated
    last_updated: datetime

    model_config = {
        "from_attributes": True
    }


class CurriculumGenerationRequest(BaseModel):
    """Request for full curriculum generation"""
    user_id: int
    learning_goal: str
    subject_area: str
    
    # Constraints
    target_completion_weeks: Optional[int] = None
    weekly_time_budget_hours: Optional[int] = None
    prerequisite_skills: List[str] = []
    
    # Personalization
    learning_style: Optional[str] = None
    difficulty_preference: str = "adaptive"
    content_type_preferences: List[ContentType] = []
    
    # Quality requirements
    quality_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    include_assessments: bool = True
    include_projects: bool = False
    
    # Advanced options
    enable_ai_tutor: bool = True
    enable_peer_collaboration: bool = False
    enable_gamification: bool = False


class CurriculumGenerationResponse(BaseModel):
    """Generated curriculum response"""
    id: int
    title: str
    description: str
    
    # Generation metadata
    user_id: int
    learning_goal: str
    generation_strategy: str
    customization_level: float
    
    # Curriculum structure
    modules: List[Dict[str, Any]]
    learning_paths: List[LearningPathResponse]
    assessments: List[Dict[str, Any]]
    
    # Quality metrics
    overall_quality_score: float
    estimated_effectiveness: float
    complexity_level: float
    
    # Status
    status: GenerationStatus
    version: str = "1.0"
    
    # Timestamps
    created_at: datetime
    generation_time_seconds: float

    model_config = {
        "from_attributes": True
    }
