"""
Stack Models for learning stack and progress tracking.
"""

from datetime import datetime
from typing import Optional
from enum import Enum
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base


class StackItemType(str, Enum):
    """Types of stack items."""
    TOPIC = "topic"
    COURSE = "course"
    SKILL = "skill"
    QUESTION = "question"
    EVENT = "event"
    VIDEO = "video"
    ARTICLE = "article"


class StackItemStatus(str, Enum):
    """Status of stack items."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"


class StackItem(Base):
    """Model for learning stack items."""
    
    __tablename__ = "stack_items"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Item info
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    item_type = Column(String(50), default="topic")  # topic, course, skill, etc.
    
    # Learning state
    status = Column(String(50), default="not_started")  # not_started, in_progress, completed
    progress = Column(Float, default=0.0)  # 0.0 to 1.0
    priority = Column(Integer, default=0)
    
    # Content reference
    content_id = Column(String(255), nullable=True)
    content_type = Column(String(50), nullable=True)
    
    # Extra data (renamed from 'metadata' which is reserved in SQLAlchemy)
    extra_data = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", backref="stack_items")
    
    def __repr__(self):
        return f"<StackItem(id={self.id}, title={self.title}, status={self.status})>"
