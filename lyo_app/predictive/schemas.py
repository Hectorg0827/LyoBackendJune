"""
Pydantic schemas for Predictive Intelligence API
"""

from datetime import datetime, time
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ContentMetadata(BaseModel):
    """Metadata about content for struggle prediction"""
    content_id: str
    type: str = Field(..., description="'lesson', 'problem', 'quiz'")
    difficulty_rating: float = Field(0.5, ge=0.0, le=1.0)
    prerequisites: List[str] = Field(default_factory=list)
    similar_topics: List[str] = Field(default_factory=list)


class StrugglePredictionRequest(BaseModel):
    """Request to predict if user will struggle with content"""
    content_metadata: ContentMetadata


class StrugglePredictionResponse(BaseModel):
    """Struggle prediction result"""
    struggle_probability: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    should_offer_help: bool
    help_message: Optional[str] = None
    features: Dict[str, float]
    prediction_id: int


class DropoutRiskResponse(BaseModel):
    """Dropout risk assessment for user"""
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str = Field(..., description="'low', 'medium', 'high', 'critical'")
    risk_factors: List[str]

    # Contributing metrics
    session_frequency_trend: Optional[float] = None
    avg_days_between_sessions: Optional[float] = None
    sentiment_trend_7d: Optional[float] = None
    days_since_last_completion: Optional[int] = None
    performance_trend: Optional[float] = None
    longest_streak: Optional[int] = None
    current_streak: Optional[int] = None

    # Re-engagement strategy
    reengagement_strategy: Optional[Dict[str, Any]] = None
    calculated_at: datetime


class TimingProfileResponse(BaseModel):
    """User's optimal learning time profile"""
    user_id: int

    # Peak learning times
    peak_hours: List[int] = Field(default_factory=list, description="Hours when user performs best (0-23)")
    optimal_study_time: Optional[time] = None

    # Day preferences
    best_days: List[str] = Field(default_factory=list, description="Best days for learning")

    # Session patterns
    avg_session_duration_minutes: Optional[float] = None
    preferred_session_length: Optional[int] = None

    # Performance data
    performance_by_hour: Dict[str, float] = Field(default_factory=dict)

    # Activity patterns
    most_active_hour: Optional[int] = None
    least_active_hour: Optional[int] = None
    typical_study_days: List[int] = Field(default_factory=list)

    # Confidence metrics
    sessions_analyzed: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    updated_at: datetime


class RecommendedTimeResponse(BaseModel):
    """Recommended intervention time for user"""
    recommended_time: time
    reasoning: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class CheckTimingRequest(BaseModel):
    """Request to check if now is a good time for intervention"""
    current_time: Optional[datetime] = None


class CheckTimingResponse(BaseModel):
    """Response indicating if now is a good time"""
    is_good_time: bool
    reasoning: str
    alternative_time: Optional[time] = None


class RecordOutcomeRequest(BaseModel):
    """Record actual outcome of predicted struggle"""
    content_id: str
    struggled: bool = Field(..., description="Did the user actually struggle?")
    completion_time_seconds: Optional[int] = None
    gave_up: bool = False


class RecordOutcomeResponse(BaseModel):
    """Confirmation of recorded outcome"""
    success: bool
    prediction_accuracy: Optional[bool] = None
    message: str


class LearningPlateauResponse(BaseModel):
    """Detected learning plateau"""
    plateau_id: int
    topic: str
    skill_id: str
    days_on_topic: int
    attempts: int
    mastery_level: float
    mastery_improvement: float
    is_active: bool
    intervention_suggested: Optional[str] = None
    detected_at: datetime


class SkillRegressionResponse(BaseModel):
    """Detected skill regression"""
    regression_id: int
    skill_id: str
    skill_name: str
    peak_mastery: float
    current_mastery: float
    regression_amount: float
    days_since_practice: int
    last_practiced_at: datetime
    urgency: str = Field(..., description="'low', 'medium', 'high', 'critical'")
    reminder_sent: bool
    detected_at: datetime


class PredictiveInsightsResponse(BaseModel):
    """Comprehensive predictive insights for user"""
    user_id: int

    # Current risk assessments
    dropout_risk: Optional[DropoutRiskResponse] = None
    active_plateaus: List[LearningPlateauResponse] = Field(default_factory=list)
    skill_regressions: List[SkillRegressionResponse] = Field(default_factory=list)

    # Timing insights
    timing_profile: Optional[TimingProfileResponse] = None
    is_good_time_now: bool

    # Summary
    total_insights: int
    priority_actions: List[Dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime
