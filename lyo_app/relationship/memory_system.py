"""
Relationship Memory System — Episodic long-term memory for the learner-Lyo bond.
Part of the Persistent Relationship System (Pillar 4).

Complements the Memory Synthesis service (factual learning memory) with
relationship-centric memories: breakthroughs, inside jokes, emotional landmarks.
"""

import logging
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import RelationshipMemory

logger = logging.getLogger(__name__)


async def store_memory(
    db: AsyncSession,
    user_id: int,
    category: str,
    content: str,
    importance: float = 0.5,
    source: str = "system",
    metadata: Optional[dict] = None,
) -> RelationshipMemory:
    """Store a new relationship memory."""
    mem = RelationshipMemory(
        user_id=user_id,
        category=category,
        content=content,
        importance=importance,
        source=source,
        metadata_json=metadata,
    )
    db.add(mem)
    await db.commit()
    await db.refresh(mem)
    logger.info(f"💾 Stored relationship memory for user {user_id}: [{category}] {content[:60]}")
    return mem


async def get_memories(
    db: AsyncSession,
    user_id: int,
    category: Optional[str] = None,
    limit: int = 20,
) -> List[RelationshipMemory]:
    """Retrieve relationship memories, optionally filtered by category."""
    query = (
        select(RelationshipMemory)
        .where(RelationshipMemory.user_id == user_id)
        .order_by(RelationshipMemory.importance.desc(), RelationshipMemory.created_at.desc())
        .limit(limit)
    )
    if category:
        query = query.where(RelationshipMemory.category == category)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_memories_for_context(
    db: AsyncSession, user_id: int, max_tokens_est: int = 500
) -> str:
    """
    Build a compact text block of relationship memories
    suitable for injection into an AI system prompt.
    """
    memories = await get_memories(db, user_id, limit=10)
    if not memories:
        return ""

    lines = ["## Relationship Memories (Lyo ↔ Learner)"]
    char_budget = max_tokens_est * 4  # rough token→char
    used = 0
    for m in memories:
        line = f"- [{m.category}] {m.content}"
        if used + len(line) > char_budget:
            break
        lines.append(line)
        used += len(line)

    return "\n".join(lines)


async def count_memories(db: AsyncSession, user_id: int) -> int:
    """Count total relationship memories for a user."""
    result = await db.execute(
        select(func.count(RelationshipMemory.id)).where(
            RelationshipMemory.user_id == user_id
        )
    )
    return result.scalar() or 0
