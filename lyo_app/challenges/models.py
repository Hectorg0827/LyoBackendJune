"""
Challenge models — a shareable quiz duel between friends.

A challenge is created from a lesson's quiz questions, shared by code
(lyoapp://challenge/<code>), and anyone who opens it can submit an attempt.
The scoreboard ranks attempts by score, then time.
"""

import secrets
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String

from lyo_app.core.database import Base


def _generate_code() -> str:
    """Short, human-shareable, unambiguous code (no 0/O/1/I)."""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(6))


class Challenge(Base):
    """A quiz duel created by a learner from lesson content."""

    __tablename__ = "challenges"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(12), unique=True, index=True, default=_generate_code)
    creator_id = Column(Integer, ForeignKey("users.id"), index=True)
    creator_name = Column(String(100), nullable=True)
    topic = Column(String(200))
    # [{"question": str, "options": [str], "answer_index": int}, ...]
    questions = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChallengeAttempt(Base):
    """One user's run at a challenge."""

    __tablename__ = "challenge_attempts"

    id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    user_name = Column(String(100), nullable=True)
    score = Column(Integer, default=0)
    total = Column(Integer, default=0)
    seconds_taken = Column(Float, nullable=True)
    completed_at = Column(DateTime, default=datetime.utcnow)
