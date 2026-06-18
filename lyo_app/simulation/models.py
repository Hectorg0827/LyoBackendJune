"""Adaptive simulation models (#5).

A simulation is a living scenario the learner steers turn-by-turn. The world has
real state (``world_state`` JSON) that evolves deterministically in response to
the learner's decisions; difficulty is set from the learner's mastery and then
adapts *within* the run based on how they're tracking against the objective.

Two additive tables (no existing-schema changes):
- ``Simulation`` — the run: scenario, world state, objective, difficulty, status.
- ``SimulationTurn`` — one decision + its computed outcome + narration.
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON,
)
from sqlalchemy import Enum as SQLEnum

from lyo_app.core.database import Base


class SimStatus(str, Enum):
    ACTIVE = "active"
    WON = "won"
    LOST = "lost"
    ABANDONED = "abandoned"


class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    scenario = Column(String(64), nullable=False)       # e.g. "coffee_shop"
    skill_id = Column(String(255), nullable=True)        # for mastery scaffolding
    difficulty = Column(String(16), nullable=False, default="medium")  # easy/medium/hard

    world_state = Column(JSON, nullable=False, default=dict)
    objective = Column(JSON, nullable=False, default=dict)  # {target_cash, max_days, ...}

    turn = Column(Integer, nullable=False, default=0)
    status = Column(SQLEnum(SimStatus), nullable=False,
                    default=SimStatus.ACTIVE, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class SimulationTurn(Base):
    __tablename__ = "simulation_turns"

    id = Column(Integer, primary_key=True, index=True)
    simulation_id = Column(Integer, ForeignKey("simulations.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    turn_index = Column(Integer, nullable=False)

    decision = Column(JSON, nullable=False, default=dict)   # learner's inputs
    outcome = Column(JSON, nullable=False, default=dict)     # computed deltas + metrics
    narration = Column(Text, nullable=True)                  # what happened, in prose
    degraded = Column(Boolean, nullable=False, default=False)  # narrated w/o LLM

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
