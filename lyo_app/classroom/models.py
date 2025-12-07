"""
Classroom Models for AI-powered classroom features.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base


class ClassroomSession(Base):
    """Model for AI Classroom sessions."""
    
    __tablename__ = "classroom_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Session info
    title = Column(String(255), nullable=True)
    subject = Column(String(100), nullable=True)
    session_type = Column(String(50), default="chat")  # chat, course, quiz, etc.
    
    # Session state
    is_active = Column(Boolean, default=True)
    
    # Content
    messages = Column(JSON, default=list)
    context = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", backref="classroom_sessions")
    
    def __repr__(self):
        return f"<ClassroomSession(id={self.id}, user_id={self.user_id}, subject={self.subject})>"
