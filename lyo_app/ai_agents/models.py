"""
AI Agents Database Models

Defines the database schema for the AI system including:
- User engagement state tracking
- Mentor interaction history
- AI conversation logs
- Performance analytics
"""

import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text, Enum, Boolean, JSON
from sqlalchemy.orm import relationship
from lyo_app.core.database import Base


class UserEngagementStateEnum(str, enum.Enum):
    """User engagement states tracked by AI system."""
    ENGAGED = "engaged"
    STRUGGLING = "struggling"
    BORED = "bored"
    CURIOUS = "curious"
    IDLE = "idle"
    FRUSTRATED = "frustrated"
    CONFIDENT = "confident"


class AIModelTypeEnum(str, enum.Enum):
    """Types of AI models used."""
    GEMMA_ON_DEVICE = "gemma_on_device"
    CLOUD_LLM = "cloud_llm"
    HYBRID = "hybrid"


class UserEngagementState(Base):
    """Tracks user engagement state and sentiment analysis."""
    __tablename__ = 'user_engagement_states'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), unique=True, nullable=False, index=True)
    state = Column(Enum(UserEngagementStateEnum), default=UserEngagementStateEnum.IDLE, nullable=False)
    last_analyzed_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sentiment_score = Column(Float, default=0.0, comment="Sentiment score from -1.0 (negative) to 1.0 (positive)")
    confidence_score = Column(Float, default=0.0, comment="AI confidence in the assessment (0.0 to 1.0)")
    context = Column(String(500), nullable=True, comment="Context information e.g., 'lesson_id:5, quiz_id:12'")
    activity_count = Column(Integer, default=0, comment="Number of activities since last state change")
    consecutive_struggles = Column(Integer, default=0, comment="Number of consecutive struggling incidents")
    
    # Relationships
    user = relationship("lyo_app.auth.models.User", back_populates="engagement_state")
    
    def __repr__(self):
        return f"<UserEngagementState(user_id={self.user_id}, state={self.state}, score={self.sentiment_score})>"


class MentorInteraction(Base):
    """Stores AI mentor conversation history."""
    __tablename__ = 'mentor_interactions'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(100), nullable=True, comment="Groups related interactions")
    user_message = Column(Text, nullable=True, comment="User's message to the mentor")
    mentor_response = Column(Text, nullable=False, comment="AI mentor's response")
    interaction_type = Column(String(50), default="conversation", comment="Type: conversation, proactive_check_in, assistance")
    model_used = Column(Enum(AIModelTypeEnum), nullable=False, comment="Which AI model generated the response")
    response_time_ms = Column(Float, nullable=True, comment="Time taken to generate response in milliseconds")
    sentiment_detected = Column(Float, nullable=True, comment="Detected sentiment in user message")
    context_metadata = Column(JSON, nullable=True, comment="Additional context data")
    was_helpful = Column(Boolean, nullable=True, comment="User feedback on helpfulness")
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("lyo_app.auth.models.User", back_populates="mentor_interactions")
    
    def __repr__(self):
        return f"<MentorInteraction(user_id={self.user_id}, type={self.interaction_type}, model={self.model_used})>"


class AIConversationLog(Base):
    """Detailed logging of all AI interactions for analytics and debugging."""
    __tablename__ = 'ai_conversation_logs'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    agent_type = Column(String(50), nullable=False, comment="Type of AI agent: mentor, sentiment, curriculum, etc.")
    input_prompt = Column(Text, nullable=False, comment="Input sent to AI model")
    ai_response = Column(Text, nullable=False, comment="Raw AI model response")
    processed_response = Column(Text, nullable=True, comment="Post-processed response sent to user")
    model_used = Column(Enum(AIModelTypeEnum), nullable=False)
    tokens_used = Column(Integer, nullable=True, comment="Number of tokens consumed")
    cost_estimate = Column(Float, nullable=True, comment="Estimated cost in USD")
    processing_time_ms = Column(Float, nullable=False)
    error_occurred = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User")
    
    def __repr__(self):
        return f"<AIConversationLog(user_id={self.user_id}, agent={self.agent_type}, model={self.model_used})>"


class AIPerformanceMetrics(Base):
    """Tracks AI system performance and usage statistics."""
    __tablename__ = 'ai_performance_metrics'
    
    id = Column(Integer, primary_key=True, index=True)
    metric_date = Column(DateTime, default=datetime.utcnow, index=True)
    total_interactions = Column(Integer, default=0)
    successful_interactions = Column(Integer, default=0)
    failed_interactions = Column(Integer, default=0)
    average_response_time_ms = Column(Float, default=0.0)
    gemma_usage_count = Column(Integer, default=0)
    cloud_llm_usage_count = Column(Integer, default=0)
    total_tokens_consumed = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)
    user_satisfaction_score = Column(Float, nullable=True, comment="Average user feedback score")
    
    def __repr__(self):
        return f"<AIPerformanceMetrics(date={self.metric_date}, interactions={self.total_interactions})>"
