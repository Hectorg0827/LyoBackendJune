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

FAILURE POSTURE

A projection failure must never fail the learner's turn, and must never
corrupt the caller's transaction. Two mechanisms:

* Everything runs inside a SAVEPOINT. If any part raises, only the savepoint
  unwinds; the surrounding session stays usable, so the processor can still
  record how the event was handled. Without this a failed flush would poison
  the AsyncSession and take the processor's own commit down with it.
* The outcome is returned rather than raised, and the processor records it
  distinctly (see `ProjectionOutcome`). An event whose projection failed is
  marked as such so it can be found and replayed later — this module does not
  claim recoverability it has not provided a marker for.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .evidence import (
    EVIDENCE_KINDS,
    MASTERY_CONFIDENCE_FLOOR,
    evidence_rank,
    normalize_evidence_kind,
)

logger = logging.getLogger(__name__)


class ProjectionOutcome(str, Enum):
    """What happened, so the caller can record it honestly."""

    #: Evidence was folded into MasteryState.
    PROJECTED = "projected"
    #: The event carried nothing to project — no concept, or no recognised
    #: rung. The normal case for reflections, voice turns, and any event
    #: predating the evidence columns. Not a failure.
    NOTHING_TO_PROJECT = "nothing_to_project"
    #: The projection was attempted and failed. The event is durable and the
    #: caller should mark it for replay rather than treating it as done.
    FAILED = "failed"


async def _load_or_create(db: AsyncSession, user_id: str, concept_id: str):
    """Fetch this learner's row for the concept, creating it if absent.

    `MasteryState` carries `uq_user_concept_mastery` on (user_id, concept_id),
    so two events for the same learner and concept processed concurrently can
    both see no row and both try to insert. The loser of that race gets an
    IntegrityError.

    The insert is therefore attempted inside its own SAVEPOINT: on conflict
    only that savepoint unwinds and we re-read the row the winner committed,
    which is the row we wanted anyway.
    """
    from lyo_app.ai_classroom.models import MasteryState

    stmt = select(MasteryState).where(
        MasteryState.user_id == user_id,
        MasteryState.concept_id == concept_id,
    )

    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    try:
        async with db.begin_nested():
            created = MasteryState(
                user_id=user_id,
                concept_id=concept_id,
                mastery_score=0.0,
                confidence=0.5,
            )
            db.add(created)
            await db.flush()
            return created
    except IntegrityError:
        # Someone else created it between our select and our insert. Their row
        # is as good as ours would have been.
        logger.debug(
            "MasteryState insert raced for user %s concept %s; using the existing row",
            user_id,
            concept_id,
        )
        return (await db.execute(stmt)).scalar_one()


def _fold_evidence(
    mastery,
    kind: str,
    confidence: float,
    misconception: Optional[str],
    attempted: bool,
) -> None:
    """Fold one piece of evidence into a MasteryState row, in place.

    `kind` says what sort of proof this is. `attempted` says whether the
    learner was actually asked to demonstrate anything — these are different
    questions and conflating them inverts the model.

    The ladder defines ``exposure`` as "instruction was delivered — proof of
    nothing on its own", while a graded wrong answer also lands on that rung
    (a learner who missed it has still been exposed to the idea). Treating
    every non-positive rung as a failed attempt would mean that *teaching*
    someone a concept increments their incorrect count, drags their score
    toward zero and marks them as declining. Being taught something must
    never make a learner look worse at it.

    So instruction-only evidence records that the learner has now seen the
    concept, and nothing else.
    """
    now = datetime.now(timezone.utc)
    mastery.last_seen = now

    if not attempted:
        # Delivered, not demonstrated. Nothing is proven either way, so no
        # counts move, the score is untouched, and the trend is unchanged.
        return

    succeeded = kind != "exposure" and confidence > 0.0

    mastery.attempts = (mastery.attempts or 0) + 1
    if succeeded:
        mastery.correct_count = (mastery.correct_count or 0) + 1
        mastery.last_correct = now
    else:
        mastery.incorrect_count = (mastery.incorrect_count or 0) + 1

    # The score moves toward the evidence rather than being overwritten by it:
    # one strong demonstration is not the whole story, and one slip does not
    # erase a history. Stronger rungs pull harder, so a transfer moves the
    # needle more than a recognition — which is the point of having a ladder.
    rung_weight = (evidence_rank(kind) + 1) / len(EVIDENCE_KINDS)
    target = confidence if succeeded else 0.0
    learning_rate = 0.35 * rung_weight
    previous = float(mastery.mastery_score or 0.0)
    mastery.mastery_score = max(0.0, min(1.0, previous + learning_rate * (target - previous)))

    # Confidence in our *estimate* grows with evidence whether or not the
    # learner got it right — a wrong answer is still information about them.
    mastery.confidence = max(0.0, min(1.0, float(mastery.confidence or 0.5) + 0.05))

    if misconception:
        mastery.error_pattern = misconception[:200]
        tags = list(mastery.misconception_tags or [])
        if misconception not in tags:
            tags.append(misconception)
        # Bounded: a live record should not grow without limit, and the most
        # recent errors are the ones remediation acts on.
        mastery.misconception_tags = tags[-10:]

    if succeeded and confidence >= MASTERY_CONFIDENCE_FLOOR:
        mastery.trend = "improving"
    elif not succeeded:
        mastery.trend = "declining"


async def project_event_to_mastery_state(db: AsyncSession, event) -> ProjectionOutcome:
    """Fold one event's evidence into the classroom's MasteryState row.

    Never raises. See the module's failure posture.
    """
    concept_id = getattr(event, "concept_id", None)
    kind = normalize_evidence_kind(getattr(event, "evidence_type", None))

    # No concept, or no recognised rung, means this event says nothing about
    # the learner's grasp of anything in particular. Log-only, not a failure.
    if not concept_id or not kind:
        return ProjectionOutcome.NOTHING_TO_PROJECT

    try:
        confidence = float(getattr(event, "evidence_confidence", None) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    # `measurable_outcome` is the graded result: 1.0 correct, 0.0 wrong, and
    # None when the learner was never asked. It is what separates "got this
    # wrong" from "was shown this", both of which sit on the exposure rung.
    attempted = getattr(event, "measurable_outcome", None) is not None

    try:
        # One savepoint around the whole projection, so that any failure —
        # a bad import, a constraint, a disconnect — unwinds only this work
        # and leaves the caller's transaction intact.
        async with db.begin_nested():
            mastery = await _load_or_create(db, str(event.user_id), concept_id)
            _fold_evidence(
                mastery,
                kind,
                confidence,
                getattr(event, "misconception", None),
                attempted=attempted,
            )
            # Flush inside the guard so a constraint or foreign-key violation
            # surfaces here, where it is caught and contained, rather than at
            # the processor's later commit — outside this handler, on a
            # session this function was supposed to protect.
            await db.flush()
        return ProjectionOutcome.PROJECTED

    except Exception:
        logger.exception(
            "MasteryState projection failed for event %s (user %s, concept %s)",
            getattr(event, "id", "?"),
            getattr(event, "user_id", "?"),
            concept_id,
        )
        return ProjectionOutcome.FAILED
