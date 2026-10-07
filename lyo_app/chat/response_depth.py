"""Learned response-depth preference for canonical Chat.

Explicit wording always wins. Repeated explicit requests teach Lyo the user's
default for future neutral turns without changing the requested interaction
mode.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.personalization.models import MemoryInsight
from lyo_app.teaching_runtime.interaction_contract import InteractionContract, ResponseDepth

_DEEP_RE = re.compile(
    r"\b(?:deep dive|go deeper|more detail|detailed|in depth|thorough|"
    r"explain deeply|profundiza|m[aá]s detalle)\b",
    re.IGNORECASE,
)
_CONCISE_RE = re.compile(
    r"\b(?:brief|briefly|short answer|concise|quickly|in one sentence|"
    r"tldr|tl;dr|resumen corto|breve)\b",
    re.IGNORECASE,
)


def explicit_depth_preference(text: str) -> Optional[ResponseDepth]:
    value = text or ""
    if _DEEP_RE.search(value):
        return ResponseDepth.DEEP
    if _CONCISE_RE.search(value):
        return ResponseDepth.CONCISE
    return None


async def learned_depth_for_user(
    db: AsyncSession,
    user_id: int,
) -> Optional[ResponseDepth]:
    """Read the latest explicitly learned response-depth preference."""
    result = await db.execute(
        select(MemoryInsight)
        .where(
            MemoryInsight.user_id == user_id,
            MemoryInsight.category == "response_depth",
            MemoryInsight.confidence >= 0.6,
        )
        .order_by(desc(MemoryInsight.created_at), desc(MemoryInsight.id))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    raw = str(row.insight_text or "").casefold()
    if "concise" in raw:
        return ResponseDepth.CONCISE
    if "deep" in raw:
        return ResponseDepth.DEEP
    if "standard" in raw:
        return ResponseDepth.STANDARD
    return None


async def record_explicit_depth_preference(
    db: AsyncSession,
    user_id: int,
    text: str,
    *,
    source_session_id: Optional[str] = None,
) -> Optional[ResponseDepth]:
    """Persist only learner-authored explicit preferences.

    We update the latest row rather than creating an unbounded preference log.
    Embeddings are unnecessary for this deterministic preference lane.
    """
    preference = explicit_depth_preference(text)
    if preference is None:
        return None

    result = await db.execute(
        select(MemoryInsight)
        .where(
            MemoryInsight.user_id == user_id,
            MemoryInsight.category == "response_depth",
        )
        .order_by(desc(MemoryInsight.created_at), desc(MemoryInsight.id))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    insight_text = f"Preferred response depth: {preference.value}"

    if row is None:
        db.add(
            MemoryInsight(
                user_id=user_id,
                category="response_depth",
                insight_text=insight_text,
                embedding=None,
                confidence=1.0,
                source_session_id=source_session_id,
            )
        )
    else:
        row.insight_text = insight_text
        row.confidence = 1.0
        if source_session_id:
            row.source_session_id = source_session_id

    await db.commit()
    return preference


def apply_learned_depth(
    contract: InteractionContract,
    *,
    user_text: str,
    learned: Optional[ResponseDepth],
) -> InteractionContract:
    """Apply learned depth only when this turn did not state a depth itself."""
    if explicit_depth_preference(user_text) is not None:
        return contract
    if contract.depth is not ResponseDepth.STANDARD or learned is None:
        return contract
    return replace(
        contract,
        depth=learned,
        directives=(
            *contract.directives,
            f"Use the learner's established {learned.value} response-depth preference for this turn.",
        ),
    )
