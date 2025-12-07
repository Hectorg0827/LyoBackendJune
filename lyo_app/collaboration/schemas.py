"""
Pydantic schemas for Collaborative Learning Phase 2
Request and response models for peer learning and study groups
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum

# ========================================
# ENUMS FOR TYPE SAFETY
# ========================================

class CollaborationType(str, Enum):
    STUDY_GROUP = "study_group"
    PEER_TUTORING = "peer_tutoring"
    PROJECT_BASED = "project_based"
    DISCUSSION_FORUM = "discussion_forum"
    PEER_REVIEW = "peer_review"

class InteractionType(str, Enum):
    QUESTION = "question"
    ANSWER = "answer"
    EXPLANATION = "explanation"
    HINT = "hint"
    RESOURCE_SHARING = "resource_sharing"
    ENCOURAGEMENT = "encouragement"
    FEEDBACK = "feedback"
    CLARIFICATION = "clarification"

class SessionType(str, Enum):
    STUDY_SESSION = "study_session"
    PROBLEM_SOLVING = "problem_solving"
    PEER_TEACHING = "peer_teaching"
    GROUP_PROJECT = "group_project"
    REVIEW_SESSION = "review_session"
    BRAINSTORMING = "brainstorming"

class MentorshipStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"

class UserRole(str, Enum):
    PARTICIPANT = "participant"
    FACILITATOR = "facilitator"
    ADMIN = "admin"
    MENTOR = "mentor"
    MENTEE = "mentee"

# ========================================
# STUDY GROUP SCHEMAS
# ========================================

class StudyGroupCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    subject_area: str = Field(..., min_length=2, max_length=100)
    max_members: int = Field(8, ge=2, le=50)
    skill_level_range: Dict[str, Any] = Field(default_factory=dict)
    collaboration_type: CollaborationType
    target_skills: List[str] = Field(default_factory=list)
    learning_objectives: List[str] = Field(default_factory=list)
    study_schedule: Dict[str, Any] = Field(default_factory=dict)
    matching_criteria: Dict[str, Any] = Field(default_factory=dict)
    interaction_rules: Dict[str, Any] = Field(default_factory=dict)
    assessment_method: str = Field("peer_feedback", max_length=50)
    is_public: bool = Field(True)
    requires_approval: bool = Field(False)

class StudyGroupUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    max_members: Optional[int] = Field(None, ge=2, le=50)
    study_schedule: Optional[Dict[str, Any]] = None
    interaction_rules: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    requires_approval: Optional[bool] = None

class StudyGroupResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    subject_area: str
    max_members: int
    current_member_count: int
    skill_level_range: Dict[str, Any]
    collaboration_type: CollaborationType
    target_skills: List[str]
    learning_objectives: List[str]
    study_schedule: Dict[str, Any]
    is_active: bool
    is_public: bool
    requires_approval: bool
    activity_score: float
    learning_effectiveness: Optional[float]
    member_satisfaction: Optional[float]
    created_at: datetime
    created_by: int
    
    model_config = {
        "from_attributes": True
    }

class StudyGroupMemberResponse(BaseModel):
    id: int
    user_id: int
    username: str
    role: UserRole
    joined_at: datetime
    participation_score: float
    contributions_count: int
    help_provided_count: int
    help_received_count: int
    skill_improvement: Dict[str, Any]
    is_active: bool
    
    model_config = {
        "from_attributes": True
    }

# ========================================
# GROUP MATCHING SCHEMAS
# ========================================

class GroupMatchingRequest(BaseModel):
    subject_areas: List[str] = Field(..., min_items=1)
    skill_levels: Dict[str, float] = Field(default_factory=dict)
    learning_goals: List[str] = Field(default_factory=list)
    collaboration_preferences: Dict[str, Any] = Field(default_factory=dict)
    schedule_preferences: Dict[str, Any] = Field(default_factory=dict)
    max_group_size: int = Field(8, ge=2, le=20)
    preferred_collaboration_type: Optional[CollaborationType] = None
    include_mentorship: bool = Field(False)

class GroupRecommendationResponse(BaseModel):
    group_id: int
    group_title: str
    match_score: float
    compatibility_reasons: List[str]
    estimated_learning_benefit: float
    member_count: int
    activity_level: str
    learning_effectiveness: Optional[float]
    
    model_config = {
        "from_attributes": True
    }

# ========================================
# PEER INTERACTION SCHEMAS
# ========================================

class PeerInteractionCreate(BaseModel):
    recipient_id: Optional[int] = None  # None for broadcast to group
    group_id: Optional[int] = None
    interaction_type: InteractionType
    content: str = Field(..., min_length=10, max_length=5000)
    context_skill_id: Optional[str] = None
    parent_interaction_id: Optional[int] = None  # For threaded responses
    
    @field_validator('content')
    def validate_content_length(cls, v, values):
        interaction_type = values.get('interaction_type')
        if interaction_type in [InteractionType.HINT, InteractionType.ENCOURAGEMENT]:
            return v  # No specific validation for these
        if len(v.strip()) < 10:
            raise ValueError('Content must be at least 10 characters for this interaction type')
        return v

class PeerInteractionResponse(BaseModel):
    id: int
    initiator_id: int
    initiator_username: str
    recipient_id: Optional[int]
    recipient_username: Optional[str]
    group_id: Optional[int]
    interaction_type: InteractionType
    content: str
    context_skill_id: Optional[str]
    helpfulness_rating: Optional[float]
    accuracy_rating: Optional[float]
    learning_impact: Optional[float]
    response_time_minutes: Optional[float]
    follow_up_questions: int
    thumbs_up_count: int
    created_at: datetime
    resolved_at: Optional[datetime]
    parent_interaction_id: Optional[int]
    responses: List['PeerInteractionResponse'] = Field(default_factory=list)
    
    model_config = {
        "from_attributes": True
    }

# ========================================
# COLLABORATIVE LEARNING SESSION SCHEMAS
# ========================================

class CollaborativeLearningSessionCreate(BaseModel):
    group_id: int
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    session_type: SessionType
    target_skills: List[str] = Field(default_factory=list)
    learning_objectives: List[str] = Field(default_factory=list)
    max_participants: int = Field(20, ge=2, le=100)
    scheduled_start: datetime
    scheduled_end: datetime
    agenda: Dict[str, Any] = Field(default_factory=dict)
    resources: Dict[str, Any] = Field(default_factory=dict)
    is_recurring: bool = Field(False)
    recurrence_pattern: Optional[Dict[str, Any]] = None
    
    @field_validator('scheduled_end')
    def validate_end_after_start(cls, v, values):
        start = values.get('scheduled_start')
        if start and v <= start:
            raise ValueError('Session end time must be after start time')
        return v

class CollaborativeLearningSessionResponse(BaseModel):
    id: int
    group_id: int
    title: str
    description: Optional[str]
    session_type: SessionType
    target_skills: List[str]
    learning_objectives: List[str]
    facilitator_id: Optional[int]
    facilitator_username: Optional[str]
    max_participants: int
    scheduled_start: datetime
    scheduled_end: datetime
    actual_start: Optional[datetime]
    actual_end: Optional[datetime]
    agenda: Dict[str, Any]
    resources: Dict[str, Any]
    attendance_count: int
    completion_rate: Optional[float]
    learning_effectiveness: Optional[float]
    participant_satisfaction: Optional[float]
    status: str
    is_recurring: bool
    created_at: datetime
    
        model_config = {
            "from_attributes": True
        }

# ========================================
# PEER MENTORSHIP SCHEMAS
# ========================================

class PeerMentorshipCreate(BaseModel):
    mentor_id: int
    skill_focus: List[str] = Field(..., min_items=1)
    learning_goals: List[str] = Field(default_factory=list)
    mentorship_plan: Dict[str, Any] = Field(default_factory=dict)
    target_duration_weeks: int = Field(8, ge=1, le=52)

class PeerMentorshipResponse(BaseModel):
    id: int
    mentor_id: int
    mentor_username: str
    mentee_id: int
    mentee_username: str
    skill_focus: List[str]
    learning_goals: List[str]
    mentorship_plan: Dict[str, Any]
    matching_score: Optional[float]
    sessions_completed: int
    progress_milestones: Dict[str, Any]
    skill_improvement: Dict[str, Any]
    mentorship_effectiveness: Optional[float]
    mentor_rating: Optional[float]
    mentee_engagement: Optional[float]
    status: MentorshipStatus
    started_at: datetime
    last_interaction: Optional[datetime]
    ended_at: Optional[datetime]
    target_duration_weeks: int
    
    model_config = {
        "from_attributes": True
    }

# ========================================
# PEER ASSESSMENT SCHEMAS
# ========================================

class PeerAssessmentCreate(BaseModel):
    assessee_id: int
    skill_id: str = Field(..., min_length=1)
    assessment_context: str = Field(..., max_length=500)
    skill_demonstration: str = Field(..., max_length=2000)
    mastery_rating: float = Field(..., ge=0.0, le=1.0)
    confidence_rating: float = Field(..., ge=0.0, le=1.0)
    assessment_criteria: Dict[str, Any] = Field(default_factory=dict)
    feedback_text: Optional[str] = Field(None, max_length=1000)
    suggestions: Optional[str] = Field(None, max_length=1000)

class PeerAssessmentResponse(BaseModel):
    id: int
    assessor_id: int
    assessor_username: str
    assessee_id: int
    assessee_username: str
    skill_id: str
    assessment_context: str
    skill_demonstration: str
    mastery_rating: float
    confidence_rating: float
    assessment_criteria: Dict[str, Any]
    feedback_text: Optional[str]
    suggestions: Optional[str]
    validity_score: Optional[float]
    agreement_with_self_assessment: Optional[float]
    learning_impact: Optional[float]
    created_at: datetime
    
    model_config = {
        "from_attributes": True
    }

# ========================================
# ANALYTICS SCHEMAS
# ========================================

class CollaborationMetrics(BaseModel):
    total_interactions: int = 0
    questions_asked: int = 0
    answers_provided: int = 0
    help_requests_fulfilled: int = 0
    average_response_time_minutes: float = 0.0
    peer_satisfaction_rating: float = 0.0
    learning_impact_score: float = 0.0
    knowledge_sharing_score: float = 0.0
    mentorship_effectiveness: float = 0.0

class LearningNetworkStats(BaseModel):
    total_connections: int = 0
    active_study_groups: int = 0
    mentorship_relationships: int = 0
    skill_areas_collaborated_on: List[str] = Field(default_factory=list)
    collaboration_diversity_score: float = 0.0
    influence_score: float = 0.0
    reputation_score: float = 0.0

class CollaborationAnalyticsResponse(BaseModel):
    user_id: int
    timeframe_days: int
    collaboration_metrics: CollaborationMetrics
    learning_network_stats: LearningNetworkStats
    skill_improvement_through_collaboration: Dict[str, float]
    top_collaboration_partners: List[Dict[str, Any]]
    learning_achievements: List[Dict[str, Any]]
    recommendations: List[str]
    
    model_config = {
        "from_attributes": True
    }

# ========================================
# SPECIAL PURPOSE SCHEMAS
# ========================================

class KnowledgeExchangeItem(BaseModel):
    """Schema for knowledge exchange tracking"""
    skill_id: str
    knowledge_shared: str
    knowledge_received: str
    exchange_effectiveness: float
    mutual_benefit_score: float
    created_at: datetime

class PeerLearningInsight(BaseModel):
    """Schema for AI-generated learning insights"""
    insight_type: str
    insight_text: str
    confidence_score: float
    actionable_recommendations: List[str]
    evidence: Dict[str, Any]
    generated_at: datetime

class StudyGroupRecommendation(BaseModel):
    """Enhanced recommendation with learning path integration"""
    group_id: int
    compatibility_score: float
    learning_synergy_potential: float
    skill_complementarity: Dict[str, float]
    estimated_outcomes: Dict[str, Any]
    success_probability: float
    
# Enable forward references for recursive models
PeerInteractionResponse.model_rebuild()
