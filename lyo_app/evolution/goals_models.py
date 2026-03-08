"""
Database models for the Goals Layer (Trajectory Engine).
Allows mapping high-level user goals to specific nodes in the Skill Graph.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text, ForeignKey,
    Enum as SQLEnum, Float, UniqueConstraint
)
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base


class GoalStatus(str, Enum):
    """Current state of a user's goal."""
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    DROPPED = "dropped"


class UserGoal(Base):
    """
    A high-level objective set by a member.
    e.g., "I want to improve my analytical thinking."
    """
    
    __tablename__ = "user_goals"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    target = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(GoalStatus), nullable=False, default=GoalStatus.ACTIVE, index=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    target_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    skill_mappings = relationship("GoalSkillMapping", back_populates="goal", cascade="all, delete-orphan")
    progress_snapshots = relationship("GoalProgressSnapshot", back_populates="goal", cascade="all, delete-orphan")


class GoalSkillMapping(Base):
    """
    Maps a broad `UserGoal` to specific, concrete `Skill` nodes in the canonical graph.
    """
    
    __tablename__ = "goal_skill_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("user_goals.id"), nullable=False, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False, index=True)
    
    # Optional weighting for how important this skill is to the goal
    importance_weight = Column(Float, nullable=False, default=1.0)
    
    # Relationships
    goal = relationship("UserGoal", back_populates="skill_mappings")
    
    # Note: We don't necessarily need a strict bi-directional relationship on the Skill side 
    # to avoid cluttering the core canonical graph with user-specific mappings, 
    # but we enforce the foreign key.
    
    __table_args__ = (
        UniqueConstraint('goal_id', 'skill_id', name='uq_goal_skill_mapping'),
    )


class GoalProgressSnapshot(Base):
    """
    Time-series snapshot of a member's trajectory toward a goal.
    Calculated periodically or on event triggers.
    """
    
    __tablename__ = "goal_progress_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("user_goals.id"), nullable=False, index=True)
    
    # Overall progress percentage (0.0 to 100.0) based on mapped skills' mastery
    overall_completion_percentage = Column(Float, nullable=False, default=0.0)
    
    # Momentum indicator (e.g., rate of change over the last 7 days)
    momentum_score = Column(Float, nullable=False, default=0.0)
    
    # Record timestamp
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    goal = relationship("UserGoal", back_populates="progress_snapshots")
