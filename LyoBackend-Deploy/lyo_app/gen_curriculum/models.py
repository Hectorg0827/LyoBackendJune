"""
Generative Curriculum models
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from lyo_app.core.database import Base

class CoursePlan(Base):
    """Versioned course plans"""
    __tablename__ = "course_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(String, unique=True, index=True)  # e.g., "P-202"
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Plan details
    title = Column(String, nullable=False)
    learning_goal = Column(Text)
    version = Column(String, default="1.0")
    
    # Structure
    outline = Column(JSON)  # Full course structure
    estimated_duration_days = Column(Integer)
    difficulty_level = Column(String)
    
    # Metrics
    quality_score = Column(Float, default=0.0)
    completion_rate = Column(Float, default=0.0)
    user_rating = Column(Float, nullable=True)
    
    # Status
    status = Column(String, default="draft")  # draft/active/deprecated
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    
    # Relationships
    modules = relationship("Module", back_populates="course_plan", cascade="all, delete-orphan")
    evaluations = relationship("ContentEvaluation", back_populates="course_plan")

class Module(Base):
    """Course modules within plans"""
    __tablename__ = "modules"
    
    id = Column(Integer, primary_key=True, index=True)
    course_plan_id = Column(Integer, ForeignKey("course_plans.id"), index=True)
    
    # Module details
    title = Column(String, nullable=False)
    description = Column(Text)
    order_index = Column(Integer)
    
    # Learning objectives
    objectives = Column(JSON)  # List of learning objectives
    prerequisites = Column(JSON)  # Required prior knowledge
    
    # Estimated time
    estimated_minutes = Column(Integer)
    
    # Relationships
    course_plan = relationship("CoursePlan", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete-orphan")

class Lesson(Base):
    """Individual lessons within modules"""
    __tablename__ = "lessons"
    
    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"), index=True)
    
    # Lesson details
    title = Column(String, nullable=False)
    content = Column(Text)
    lesson_type = Column(String)  # reading/video/practice/quiz
    
    # Structure
    order_index = Column(Integer)
    estimated_minutes = Column(Integer)
    difficulty_level = Column(String)
    
    # Content
    resources = Column(JSON)  # Associated resources
    practice_items = Column(JSON)  # Practice questions/activities
    
    # Performance tracking
    avg_completion_time = Column(Float, nullable=True)
    success_rate = Column(Float, nullable=True)
    hint_usage_rate = Column(Float, nullable=True)
    
    # Flags for improvement
    needs_revision = Column(Boolean, default=False)
    confusion_points = Column(JSON)  # Common confusion areas
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    module = relationship("Module", back_populates="lessons")

class ContentEvaluation(Base):
    """A/B testing and evaluation results"""
    __tablename__ = "content_evaluations"
    
    id = Column(Integer, primary_key=True, index=True)
    course_plan_id = Column(Integer, ForeignKey("course_plans.id"), index=True)
    
    # Evaluation details
    evaluation_type = Column(String)  # ab_test/quality_review/user_feedback
    version_a = Column(String)
    version_b = Column(String, nullable=True)
    
    # Metrics
    sample_size = Column(Integer)
    completion_rate_a = Column(Float)
    completion_rate_b = Column(Float, nullable=True)
    user_satisfaction_a = Column(Float)
    user_satisfaction_b = Column(Float, nullable=True)
    
    # Results
    winner = Column(String, nullable=True)  # version_a/version_b/inconclusive
    confidence_level = Column(Float)
    statistical_significance = Column(Boolean, default=False)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    # Relationships
    course_plan = relationship("CoursePlan", back_populates="evaluations")
