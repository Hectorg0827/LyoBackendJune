"""
Clip model for educational video clips.
Clips are short user-created videos that can be used for AI course generation.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base


class Clip(Base):
    """
    Educational video clip created by users.
    Contains metadata for AI course generation.
    """
    __tablename__ = "clips"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Basic info
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Media URLs
    video_url = Column(String(500), nullable=False)
    thumbnail_url = Column(String(500), nullable=True)
    
    # Video metadata
    duration_seconds = Column(Float, default=0)
    
    # Learning context for AI course generation
    subject = Column(String(100), nullable=True)  # e.g., "Mathematics"
    topic = Column(String(100), nullable=True)    # e.g., "Algebra"
    level = Column(String(50), default="beginner")  # beginner, intermediate, advanced
    key_points = Column(JSON, default=list)  # List of key learning points
    transcript = Column(Text, nullable=True)  # Auto-generated transcript
    tags = Column(JSON, default=list)  # Searchable tags
    enable_course_generation = Column(Boolean, default=True)  # Allow AI to create courses
    
    # Social stats
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    
    # Visibility
    is_public = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="clips")
    likes = relationship("ClipLike", back_populates="clip", cascade="all, delete-orphan")
    
    def to_dict(self) -> dict:
        """Convert clip to dictionary for API responses."""
        # Handle unloaded user relationship
        author_name = None
        author_avatar = None
        try:
            if self.user:
                author_name = getattr(self.user, 'full_name', None) or getattr(self.user, 'username', 'Unknown')
                author_avatar = getattr(self.user, 'avatar_url', None)
        except Exception:
            pass  # User relationship not loaded
        
        return {
            "id": str(self.id),
            "userId": self.user_id,
            "title": self.title,
            "description": self.description,
            "videoURL": self.video_url,
            "thumbnailURL": self.thumbnail_url,
            "durationSeconds": self.duration_seconds,
            "metadata": {
                "subject": self.subject,
                "topic": self.topic,
                "level": self.level,
                "keyPoints": self.key_points or [],
                "transcript": self.transcript,
                "tags": self.tags or [],
                "enableCourseGeneration": self.enable_course_generation
            },
            "viewCount": self.view_count,
            "likeCount": self.like_count,
            "shareCount": self.share_count,
            "isLiked": False,  # Will be set by the API based on current user
            "isSaved": False,  # Will be set by the API
            "authorName": author_name,
            "authorAvatarURL": author_avatar,
            "isPublic": self.is_public,
            "createdAt": self.created_at.isoformat() if self.created_at else None
        }


class ClipLike(Base):
    """Track which users liked which clips."""
    __tablename__ = "clip_likes"
    
    id = Column(Integer, primary_key=True, index=True)
    clip_id = Column(Integer, ForeignKey("clips.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    clip = relationship("Clip", back_populates="likes")
    user = relationship("User")


class ClipView(Base):
    """Track clip views for analytics."""
    __tablename__ = "clip_views"
    
    id = Column(Integer, primary_key=True, index=True)
    clip_id = Column(Integer, ForeignKey("clips.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    viewed_at = Column(DateTime, default=datetime.utcnow)
    watch_duration_seconds = Column(Float, nullable=True)
