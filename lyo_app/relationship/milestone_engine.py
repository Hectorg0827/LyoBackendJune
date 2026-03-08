"""
Milestone Engine — Detects, records and celebrates milestones in the learner's journey.
Part of the Persistent Relationship System (Pillar 4).
"""

import logging
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Milestone, MilestoneType

logger = logging.getLogger(__name__)


async def record_milestone(
    db: AsyncSession,
    user_id: int,
    milestone_type: MilestoneType,
    title: str,
    description: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Milestone:
    """Record a new milestone for a user (idempotent for non-CUSTOM types)."""
    # Prevent duplicates for typed milestones
    if milestone_type != MilestoneType.CUSTOM:
        existing = await db.execute(
            select(Milestone).where(
                and_(
                    Milestone.user_id == user_id,
                    Milestone.milestone_type == milestone_type.value,
                )
            )
        )
        if existing.scalar_one_or_none():
            logger.debug(f"Milestone {milestone_type.value} already exists for user {user_id}")
            return existing.scalar_one_or_none()

    ms = Milestone(
        user_id=user_id,
        milestone_type=milestone_type.value,
        title=title,
        description=description,
        metadata_json=metadata,
    )
    db.add(ms)
    await db.commit()
    await db.refresh(ms)
    logger.info(f"🏅 Milestone recorded for user {user_id}: {title}")
    return ms


async def get_milestones(
    db: AsyncSession, user_id: int, limit: int = 50
) -> List[Milestone]:
    """Retrieve milestones for a user, newest first."""
    result = await db.execute(
        select(Milestone)
        .where(Milestone.user_id == user_id)
        .order_by(Milestone.achieved_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_uncelebrated(db: AsyncSession, user_id: int) -> List[Milestone]:
    """Retrieve milestones that haven't been shown to the user yet."""
    result = await db.execute(
        select(Milestone).where(
            and_(
                Milestone.user_id == user_id,
                Milestone.celebrated == False,  # noqa: E712
            )
        )
    )
    return list(result.scalars().all())


async def mark_celebrated(db: AsyncSession, milestone_id: int) -> None:
    """Mark a milestone as celebrated (shown to the user)."""
    result = await db.execute(
        select(Milestone).where(Milestone.id == milestone_id)
    )
    ms = result.scalar_one_or_none()
    if ms:
        ms.celebrated = True
        await db.commit()


async def count_milestones(db: AsyncSession, user_id: int) -> int:
    """Count total milestones for a user."""
    result = await db.execute(
        select(func.count(Milestone.id)).where(Milestone.user_id == user_id)
    )
    return result.scalar() or 0
