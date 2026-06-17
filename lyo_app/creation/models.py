"""Teaching-through-creation models (#4 — "build-with-me").

The pedagogy: people retain far more by *making and explaining* than by being
quizzed (constructionism / the protégé effect). A creation project is a thing
the learner builds, decomposed into steps the tutor scaffolds at the learner's
mastery level; the learner submits an artifact per step and the tutor reviews
it, advancing only when the work holds up.

Two additive tables (no changes to existing schema):
- ``CreationProject`` — the build, its mastery-scaffolded step plan, and status.
- ``CreationArtifact`` — each piece of work the learner submits + the review.
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON,
)
from sqlalchemy import Enum as SQLEnum

from lyo_app.core.database import Base


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ScaffoldLevel(str, Enum):
    """How much the tutor holds the learner's hand — derived from mastery."""
    HIGH = "high"      # low mastery: detailed guidance, worked sub-steps
    MEDIUM = "medium"  # mid mastery: hints + checkpoints
    LOW = "low"        # high mastery: prompts for autonomy, stretch goals


class CreationProject(Base):
    __tablename__ = "creation_projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    title = Column(String(300), nullable=False)
    goal = Column(Text, nullable=False)          # what the learner wants to build
    skill_id = Column(String(255), nullable=True)  # for mastery scaffolding
    scaffold_level = Column(SQLEnum(ScaffoldLevel), nullable=False,
                            default=ScaffoldLevel.MEDIUM)

    # steps: [{"index": int, "title": str, "description": str,
    #          "status": "pending"|"active"|"done"}]
    steps = Column(JSON, nullable=False, default=list)
    current_step = Column(Integer, nullable=False, default=0)

    status = Column(SQLEnum(ProjectStatus), nullable=False,
                    default=ProjectStatus.ACTIVE, index=True)
    degraded = Column(Boolean, nullable=False, default=False)  # planned without LLM

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class CreationArtifact(Base):
    __tablename__ = "creation_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("creation_projects.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    step_index = Column(Integer, nullable=False)

    content = Column(Text, nullable=False)       # the learner's submitted work
    feedback = Column(Text, nullable=True)        # the tutor's review
    accepted = Column(Boolean, nullable=False, default=False)
    degraded = Column(Boolean, nullable=False, default=False)  # reviewed w/o LLM

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
