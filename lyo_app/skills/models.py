"""
Database models for the Canonical Skill Graph.
Defines skills, their domains, and prerequisite relationships.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text, ForeignKey,
    Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base


class SkillDomain(str, Enum):
    """Broad domains categorizing skills."""
    ACADEMIC = "academic"       # Traditional subjects (Math, Biology, History)
    CAPABILITY = "capability"   # Meta-skills (Problem Solving, Systems Thinking, Focus)
    LIFE = "life"             # Practical skills (Decision Making, Emotional Regulation, Health Literacy)


class Skill(Base):
    """
    Core skill node in the Canonical Skill Graph.
    Everything the user learns maps to a skill.
    """
    
    __tablename__ = "skills"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    domain = Column(SQLEnum(SkillDomain), nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Metadata
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tags = relationship("SkillTag", back_populates="skill", cascade="all, delete-orphan")
    
    # Dependencies where this skill is the target (it depends on prerequisite_skill)
    prerequisites = relationship(
        "SkillEdge",
        foreign_keys="SkillEdge.skill_id",
        back_populates="skill",
        cascade="all, delete-orphan"
    )
    
    # Dependencies where this skill is the required prerequisite for another skill
    unlocks = relationship(
        "SkillEdge",
        foreign_keys="SkillEdge.prerequisite_skill_id",
        back_populates="prerequisite",
        cascade="all, delete-orphan"
    )


class SkillEdge(Base):
    """
    Defines prerequisite relationships between skills (Directed Acyclic Graph).
    """
    
    __tablename__ = "skill_edges"
    
    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False, index=True)
    prerequisite_skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False, index=True)
    
    # Optional weighting/strength of prerequisite (e.g., 1.0 = mandatory, 0.5 = helpful)
    weight = Column(Integer, nullable=False, default=1)
    
    # Relationships
    skill = relationship("Skill", foreign_keys=[skill_id], back_populates="prerequisites")
    prerequisite = relationship("Skill", foreign_keys=[prerequisite_skill_id], back_populates="unlocks")
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('skill_id', 'prerequisite_skill_id', name='uq_skill_edge'),
    )


class SkillTag(Base):
    """
    Tags for semantic grouping and filtering of skills.
    e.g., skill: "Python", tags: ["programming", "backend", "data-science"]
    """
    
    __tablename__ = "skill_tags"
    
    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False, index=True)
    tag = Column(String(100), nullable=False, index=True)
    
    # Relationships
    skill = relationship("Skill", back_populates="tags")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('skill_id', 'tag', name='uq_skill_tag'),
    )
