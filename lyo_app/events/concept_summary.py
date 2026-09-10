"""What the learner actually knows, counted from evidence.

WHY THIS EXISTS

Home leads with XP, level and streak. Those are real numbers, but they
describe attendance, not knowledge: a learner with a 30-day streak and 4,000
XP still cannot tell from that screen whether they understand anything.

The product specification asks the front page to lead with concepts learned,
mastered and retained instead. Those are claims about a learner, so they have
to be *earned* from evidence rather than derived from a score that happens to
be handy. `LearningEvent` now carries the rung each demonstration reached,
which is what makes this countable at all.

WHAT THE WORDS MEAN

Deliberately strict, because the whole point of the ladder is that mastery is
not granted cheaply, and a headline number that overstates is worse than no
headline number.

* **exploring** — met the concept, has not yet explained it. Recognition is a
  multiple-choice hit; it is not knowing something.
* **learned** — explained it acceptably in their own words, or better.
* **retained** — retrieved it correctly after a real interval. This is the
  one that separates learning from remembering.
* **mastered** — used it on a familiar problem, used it somewhere new, *and*
  still had it after a delay, each above the confidence floor.

The categories overlap on purpose: they are a funnel, not a partition. A
mastered concept is also learned and retained, and saying otherwise would
make the numbers move backwards as a learner improves.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .evidence import (
    MASTERY_CONFIDENCE_FLOOR,
    MASTERY_STATES,
    derive_mastery_state,
    normalize_evidence_kind,
)

logger = logging.getLogger(__name__)

#: Most recent events considered. A learner's whole history is not needed to
#: say what they know now, and an unbounded read on the front page is how a
#: home screen becomes the slowest request in the product.
EVENT_CAP = 2000

#: Reaching this rung is what "learned" means here.
LEARNED_FLOOR = "EXPLAINED"


class ConceptSummary(BaseModel):
    """Counts of concepts by how well the learner has shown they know them."""

    exploring: int = Field(0, ge=0)
    learned: int = Field(0, ge=0)
    retained: int = Field(0, ge=0)
    mastered: int = Field(0, ge=0)
    total: int = Field(0, ge=0)


def _rank(state: str) -> int:
    try:
        return MASTERY_STATES.index(state)
    except ValueError:
        return -1


def summarize_concepts(
    rows: Iterable[Any],
) -> ConceptSummary:
    """Fold evidence rows into counts.

    Each row is ``(concept_id, evidence_type, evidence_confidence)``. Rows
    naming no concept or no recognised rung are skipped rather than guessed
    at — the same rule the projection follows, so the two cannot disagree
    about what counts as evidence.
    """
    by_concept: Dict[str, List[Dict[str, Any]]] = {}
    retention: Dict[str, float] = {}

    for row in rows or []:
        concept_id, evidence_type, confidence = row[0], row[1], row[2]
        if not concept_id:
            continue
        kind = normalize_evidence_kind(evidence_type)
        if not kind:
            continue
        try:
            value = max(0.0, min(1.0, float(confidence or 0.0)))
        except (TypeError, ValueError):
            value = 0.0
        by_concept.setdefault(concept_id, []).append(
            {"kind": kind, "confidence": value}
        )
        if kind == "retention":
            retention[concept_id] = max(retention.get(concept_id, 0.0), value)

    summary = ConceptSummary()
    learned_floor = _rank(LEARNED_FLOOR)

    for concept_id, evidence in by_concept.items():
        state = derive_mastery_state(evidence)
        rank = _rank(state)
        if rank <= _rank("NOT_SEEN"):
            continue

        summary.total += 1
        if rank >= learned_floor:
            summary.learned += 1
        else:
            summary.exploring += 1
        # Retention is read from the evidence rather than from the derived
        # state: a concept can be MASTERED, whose state name no longer says
        # "RETAINED", and it would be perverse for the retained count to drop
        # at the moment the learner got better at it.
        if retention.get(concept_id, 0.0) >= MASTERY_CONFIDENCE_FLOOR:
            summary.retained += 1
        if state == "MASTERED":
            summary.mastered += 1

    return summary


async def concept_summary_for_user(
    db: AsyncSession, user_id: Any, limit: int = EVENT_CAP
) -> ConceptSummary:
    """Count what this learner knows, from their own evidence.

    Returns empty counts rather than raising. This feeds a home screen; a
    learner should never lose their front page because a summary query
    failed, and an honest zero is better than an error.
    """
    from .models import LearningEvent

    try:
        learner_id = int(user_id)
    except (TypeError, ValueError):
        return ConceptSummary()

    try:
        result = await db.execute(
            select(
                LearningEvent.concept_id,
                LearningEvent.evidence_type,
                LearningEvent.evidence_confidence,
            )
            .where(
                LearningEvent.user_id == learner_id,
                LearningEvent.concept_id.isnot(None),
                LearningEvent.evidence_type.isnot(None),
            )
            .order_by(LearningEvent.id.desc())
            .limit(limit)
        )
        return summarize_concepts(result.all())
    except Exception:
        logger.exception("Concept summary failed for user %s", user_id)
        return ConceptSummary()
