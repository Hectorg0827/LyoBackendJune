"""
Challenge API — create a quiz duel, fetch it by code, submit an attempt,
read the scoreboard.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user
from lyo_app.core.database import get_db
from lyo_app.models.enhanced import User

from .models import Challenge, ChallengeAttempt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/challenges", tags=["Challenges"])


# --- Schemas -----------------------------------------------------------------

class ChallengeQuestion(BaseModel):
    question: str
    options: List[str] = Field(min_length=2, max_length=6)
    answer_index: int = 0


class ChallengeCreate(BaseModel):
    topic: str
    questions: List[ChallengeQuestion] = Field(min_length=1, max_length=10)


class AttemptCreate(BaseModel):
    score: int
    total: int
    seconds_taken: Optional[float] = None


class AttemptOut(BaseModel):
    user_id: int
    user_name: Optional[str]
    score: int
    total: int
    seconds_taken: Optional[float]
    completed_at: datetime


class ChallengeOut(BaseModel):
    code: str
    topic: str
    creator_name: Optional[str]
    questions: List[ChallengeQuestion]
    created_at: datetime


class ScoreboardOut(BaseModel):
    code: str
    topic: str
    creator_name: Optional[str]
    attempts: List[AttemptOut]


# --- Routes ------------------------------------------------------------------

@router.post("", response_model=ChallengeOut, status_code=201)
async def create_challenge(
    payload: ChallengeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChallengeOut:
    """Create a challenge from lesson quiz content; returns the share code."""
    display_name = (
        getattr(current_user, "first_name", None)
        or getattr(current_user, "username", None)
    )
    challenge = Challenge(
        creator_id=current_user.id,
        creator_name=display_name,
        topic=payload.topic[:200],
        questions=[q.model_dump() for q in payload.questions],
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    logger.info(f"Challenge {challenge.code} created by user {current_user.id}")
    return ChallengeOut(
        code=challenge.code,
        topic=challenge.topic,
        creator_name=challenge.creator_name,
        questions=[ChallengeQuestion(**q) for q in challenge.questions],
        created_at=challenge.created_at,
    )


async def _get_by_code(db: AsyncSession, code: str) -> Challenge:
    result = await db.execute(
        select(Challenge).where(Challenge.code == code.upper())
    )
    challenge = result.scalar_one_or_none()
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


@router.get("/{code}", response_model=ChallengeOut)
async def get_challenge(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChallengeOut:
    challenge = await _get_by_code(db, code)
    return ChallengeOut(
        code=challenge.code,
        topic=challenge.topic,
        creator_name=challenge.creator_name,
        questions=[ChallengeQuestion(**q) for q in challenge.questions],
        created_at=challenge.created_at,
    )


@router.post("/{code}/attempts", response_model=ScoreboardOut)
async def submit_attempt(
    code: str,
    payload: AttemptCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreboardOut:
    """Record an attempt (latest per user wins) and return the scoreboard."""
    challenge = await _get_by_code(db, code)

    if payload.total <= 0 or payload.score < 0 or payload.score > payload.total:
        raise HTTPException(status_code=422, detail="Invalid score")

    # One row per user: update if they retake.
    result = await db.execute(
        select(ChallengeAttempt).where(
            ChallengeAttempt.challenge_id == challenge.id,
            ChallengeAttempt.user_id == current_user.id,
        )
    )
    attempt = result.scalar_one_or_none()
    display_name = (
        getattr(current_user, "first_name", None)
        or getattr(current_user, "username", None)
    )
    if attempt is None:
        attempt = ChallengeAttempt(
            challenge_id=challenge.id,
            user_id=current_user.id,
            user_name=display_name,
            score=payload.score,
            total=payload.total,
            seconds_taken=payload.seconds_taken,
        )
        db.add(attempt)
    else:
        attempt.score = payload.score
        attempt.total = payload.total
        attempt.seconds_taken = payload.seconds_taken
        attempt.completed_at = datetime.utcnow()

    await db.commit()
    return await _scoreboard(db, challenge)


@router.get("/{code}/scoreboard", response_model=ScoreboardOut)
async def get_scoreboard(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreboardOut:
    challenge = await _get_by_code(db, code)
    return await _scoreboard(db, challenge)


async def _scoreboard(db: AsyncSession, challenge: Challenge) -> ScoreboardOut:
    result = await db.execute(
        select(ChallengeAttempt)
        .where(ChallengeAttempt.challenge_id == challenge.id)
        .order_by(
            ChallengeAttempt.score.desc(),
            ChallengeAttempt.seconds_taken.asc().nullslast(),
        )
        .limit(50)
    )
    attempts = result.scalars().all()
    return ScoreboardOut(
        code=challenge.code,
        topic=challenge.topic,
        creator_name=challenge.creator_name,
        attempts=[
            AttemptOut(
                user_id=a.user_id,
                user_name=a.user_name,
                score=a.score,
                total=a.total,
                seconds_taken=a.seconds_taken,
                completed_at=a.completed_at,
            )
            for a in attempts
        ],
    )
