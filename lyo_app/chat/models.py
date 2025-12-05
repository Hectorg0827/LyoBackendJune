"""
Chat Module Models

Data models for the chat system including courses, notes, and cache structures.
Implements stores for persistent data management.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, JSON,
    ForeignKey, Index, Float
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from lyo_app.core.database import Base


# =============================================================================
# ENUMS
# =============================================================================

class ChatMode(str, Enum):
    """Available chat modes for routing"""
    QUICK_EXPLAINER = "quick_explainer"
    COURSE_PLANNER = "course_planner"
    PRACTICE = "practice"
    NOTE_TAKER = "note_taker"
    GENERAL = "general"


class ChipAction(str, Enum):
    """Available chip actions for quick responses"""
    PRACTICE = "practice"
    TAKE_NOTE = "take_note"
    EXPLAIN_MORE = "explain_more"
    QUIZ_ME = "quiz_me"
    CREATE_COURSE = "create_course"
    SUMMARIZE = "summarize"


class CTAType(str, Enum):
    """Call-to-action types"""
    START_COURSE = "start_course"
    CONTINUE_LEARNING = "continue_learning"
    TAKE_QUIZ = "take_quiz"
    REVIEW_NOTES = "review_notes"
    PRACTICE_NOW = "practice_now"
    SHARE_PROGRESS = "share_progress"


# =============================================================================
# COURSE STORE MODEL
# =============================================================================

class ChatCourse(Base):
    """Stores generated/referenced courses from chat interactions"""
    
    __tablename__ = "chat_courses"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    
    # Course content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    topic: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    difficulty: Mapped[str] = mapped_column(String(50), default="intermediate")
    
    # Structured content (JSON)
    modules: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)  # List of modules with lessons
    learning_objectives: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    prerequisites: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    
    # Metadata
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    generated_by_mode: Mapped[str] = mapped_column(String(50), default=ChatMode.COURSE_PLANNER.value)
    source_conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Indexes
    __table_args__ = (
        Index('ix_chat_courses_user_topic', 'user_id', 'topic'),
        Index('ix_chat_courses_created', 'created_at'),
    )


# =============================================================================
# NOTES STORE MODEL
# =============================================================================

class ChatNote(Base):
    """Stores notes created during chat interactions"""
    
    __tablename__ = "chat_notes"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    
    # Note content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Context
    topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    tags: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    source_message_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    source_conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    related_course_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("chat_courses.id"), nullable=True
    )
    
    # Note metadata
    note_type: Mapped[str] = mapped_column(String(50), default="general")  # general, key_concept, example, question
    importance: Mapped[int] = mapped_column(Integer, default=0)  # 0-5 scale
    
    # Status
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Relationships
    related_course = relationship("ChatCourse", foreign_keys=[related_course_id])
    
    __table_args__ = (
        Index('ix_chat_notes_user_topic', 'user_id', 'topic'),
        Index('ix_chat_notes_created', 'created_at'),
    )


# =============================================================================
# CHAT CONVERSATION MODEL
# =============================================================================

class ChatConversation(Base):
    """Tracks chat conversations for context and analytics"""
    
    __tablename__ = "chat_conversations"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    
    # Conversation context
    initial_mode: Mapped[str] = mapped_column(String(50), default=ChatMode.GENERAL.value)
    current_mode: Mapped[str] = mapped_column(String(50), default=ChatMode.GENERAL.value)
    topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Message tracking
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Context data (for maintaining state)
    context_data: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Relationships
    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="conversation", cascade="all, delete-orphan"
    )


# =============================================================================
# CHAT MESSAGE MODEL
# =============================================================================

class ChatMessage(Base):
    """Individual chat messages within a conversation"""
    
    __tablename__ = "chat_messages"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_conversations.id"), nullable=False, index=True
    )
    
    # Message content
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Routing info
    mode_used: Mapped[str] = mapped_column(String(50), default=ChatMode.GENERAL.value)
    action_triggered: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # AI metadata
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # CTAs attached to this message
    ctas: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    chip_actions: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    
    # Cache info
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    
    # Relationships
    conversation: Mapped["ChatConversation"] = relationship(
        "ChatConversation", back_populates="messages"
    )
    
    __table_args__ = (
        Index('ix_chat_messages_conv_created', 'conversation_id', 'created_at'),
    )


# =============================================================================
# TELEMETRY MODEL
# =============================================================================

class ChatTelemetry(Base):
    """Telemetry events for chat interactions"""
    
    __tablename__ = "chat_telemetry"
    
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    
    # Event identification
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Event data
    mode_chosen: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    cta_clicked: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    chip_action_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Performance
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Additional data (using 'extra_data' since 'metadata' is reserved in SQLAlchemy)
    extra_data: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    
    __table_args__ = (
        Index('ix_chat_telemetry_event_time', 'event_type', 'created_at'),
    )
