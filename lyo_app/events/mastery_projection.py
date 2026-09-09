"""
Project a LearningEvent's evidence into `ai_classroom.MasteryState`.

WHY THIS EXISTS

`ai_classroom.MasteryState` is read by the live classroom's scene engine to
decide how to teach — it looks up the learner's score and trend before
choosing a move. But on the live path nothing writes it: `graph_service` only
fires from the playback routes, and `interaction_service` has no callers at
all. Meanwhile every chat check writes `personalization.LearnerMastery`.

So the Classroom has been adapting its teaching from a table that Chat never
fills. A learner who demonstrated a concept in Chat arrives at the Classroom
as a stranger.

This module closes that gap without moving a single row. The event processor
already updates the DKT mastery that Chat depends on; it now *also* projects
the same evidence here, so the table the Classroom reads finally reflects what
the learner actually did. Both tables become views of one event stream rather
than two disagreeing sources of truth.

Deliberately defensive: a projection failure must never fail the learner's
turn. The evidence is already durably logged on the event, so a failed
projection can be replayed later — losing the learner's answer because a
secondary table was unavailable would be a far worse outcome than a stale
mastery row.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .evidence import (
    MASTERY_CONFIDENCE_FLOOR,
    evidence_rank,
    normalize_evidence_kind,
)

logger = logging.getLogger(__name__)


async def project_event_to_mastery_state(db: AsyncSession, event) -> bool:
    """Fold one event's evidence into the classroom's MasteryState row.

    Returns True when a row was written, False when the event carried nothing
    to project (which is the normal case for reflections, voice turns and any
    event predating the evidence columns).

    Never raises: see the module docstring.
    """
    concept_id = getattr(event, "concept_id", None)
    kind = normalize_evidence_kind(getattr(event, "evidence_type", None))

    # No concept or no recognised rung means there is nothing to say about
    # this learner's grasp of anything in particular. Log-only.
    if not concept_id or not kind:
        return False

    try:
        from lyo_app.ai_classroom.models import MasteryState

        confidence = float(getattr(event, "evidence_confidence", None) or 0.0)
        is_positive = kind != "exposure" and confidence > 0.0

        result = await db.execute(
            select(MasteryState).where(
                MasteryState.user_id == str(event.user_id),
                MasteryState.concept_id == concept_id,
            )
        )
        mastery: Optional[object] = result.scalar_one_or_none()

        if mastery is None:
            mastery = MasteryState(
                user_id=str(event.user_id),
                concept_id=concept_id,
                mastery_score=0.0,
                confidence=0.5,
            )
            db.add(mastery)

        mastery.attempts = (mastery.attempts or 0) + 1
        if is_positive:
            mastery.correct_count = (mastery.correct_count or 0) + 1
        else:
            mastery.incorrect_count = (mastery.incorrect_count or 0) + 1

        now = datetime.now(timezone.utc)
        mastery.last_seen = now
        if is_positive:
            mastery.last_correct = now

        # The score moves toward the evidence rather than being overwritten by
        # it: one strong demonstration is not the whole story, and one slip
        # does not erase a history. Stronger rungs pull harder, so a transfer
        # moves the needle more than a recognition — which is the whole point
        # of having a ladder.
        rung_weight = (evidence_rank(kind) + 1) / len(
            ("exposure", "recognition", "explanation", "application", "transfer", "retention")
        )
        target = confidence if is_positive else 0.0
        learning_rate = 0.35 * rung_weight
        previous = float(mastery.mastery_score or 0.0)
        mastery.mastery_score = max(0.0, min(1.0, previous + learning_rate * (target - previous)))

        # Confidence in our *estimate* grows with evidence regardless of
        # whether the learner got it right — a wrong answer is still
        # information about them.
        mastery.confidence = max(0.0, min(1.0, float(mastery.confidence or 0.5) + 0.05))

        misconception = getattr(event, "misconception", None)
        if misconception:
            mastery.error_pattern = misconception[:200]
            tags = list(mastery.misconception_tags or [])
            if misconception not in tags:
                tags.append(misconception)
            # Bounded: a learner's live record should not grow without limit,
            # and the most recent errors are the ones remediation acts on.
            mastery.misconception_tags = tags[-10:]

        if is_positive and confidence >= MASTERY_CONFIDENCE_FLOOR:
            mastery.trend = "improving"
        elif not is_positive:
            mastery.trend = "declining"

        return True

    except Exception:
        # Swallowed by design. The evidence is already on the event row, so
        # this is recoverable by replay; failing the learner's turn is not.
        logger.exception(
            "MasteryState projection failed for event %s (user %s, concept %s)",
            getattr(event, "id", "?"),
            getattr(event, "user_id", "?"),
            concept_id,
        )
        return False
