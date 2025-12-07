"""
Mentor Chat Models for AI-powered mentorship features.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
import enum

from lyo_app.core.database import Base


class MentorConversation(Base):
    """Model for mentor conversation sessions."""
    
    __tablename__ = "mentor_conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Conversation info
    title = Column(String(255), nullable=True)
    topic = Column(String(100), nullable=True)
    
    # State
    is_active = Column(Boolean, default=True)
    context = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="mentor_conversations")
    messages = relationship("MentorMessage", back_populates="conversation", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<MentorConversation(id={self.id}, user_id={self.user_id}, topic={self.topic})>"


class MentorMessage(Base):
    """Model for individual mentor chat messages."""
    
    __tablename__ = "mentor_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("mentor_conversations.id"), nullable=False, index=True)
    
    # Message content
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    
    # Metadata
    metadata = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation = relationship("MentorConversation", back_populates="messages")
    
    def __repr__(self):
        return f"<MentorMessage(id={self.id}, role={self.role})>"


class MentorAction(Base):
    """Model for mentor-suggested actions."""
    
    __tablename__ = "mentor_actions"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("mentor_conversations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Action info
    action_type = Column(String(50), nullable=False)  # study, quiz, review, etc.
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # State
    status = Column(String(50), default="pending")  # pending, in_progress, completed, dismissed
    priority = Column(Integer, default=0)
    
    # Content reference
    content_id = Column(String(255), nullable=True)
    content_type = Column(String(50), nullable=True)
    
    # Metadata
    metadata = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", backref="mentor_actions")
    
    def __repr__(self):
        return f"<MentorAction(id={self.id}, action_type={self.action_type}, status={self.status})>"


class MentorSuggestion(Base):
    """Model for mentor suggestions/recommendations."""
    
    __tablename__ = "mentor_suggestions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Suggestion info
    suggestion_type = Column(String(50), nullable=False)  # topic, resource, practice, etc.
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    
    # State
    status = Column(String(50), default="active")  # active, accepted, dismissed, expired
    priority = Column(Integer, default=0)
    
    # Content reference
    content_id = Column(String(255), nullable=True)
    content_type = Column(String(50), nullable=True)
    
    # Metadata
    metadata = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    acted_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", backref="mentor_suggestions")
    
    def __repr__(self):
        return f"<MentorSuggestion(id={self.id}, suggestion_type={self.suggestion_type})>"
