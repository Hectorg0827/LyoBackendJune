"""
What one learner has actually shown, concept by concept.

WHY THIS EXISTS

`concept_summary.py` answers "how many things does this learner know?" — four
counts for a front page. It cannot answer the question a learner asks about
their own work: *what did I show, on what, and what is left?*

Everything needed to answer that has been recorded on `LearningEvent` since
the evidence ladder landed: the rung each demonstration reached, the
confidence after damping for help used, how much help that was, and the
misconception the grader named. Nothing read it back.

The rule this module exists to keep is the one that makes the answer worth
showing at all: **it reports rungs the learner reached, never a score
reinterpreted as a rung.** *Recognised* is not *applied*. A concept the
learner has only ever picked out of four options is reported as recognised,
however many times they have done it and however high their mastery score
climbed.

`derive_mastery_state` is imported rather than reimplemented, so this view and
the projection that writes mastery cannot come to different conclusions about
the same evidence.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .evidence import (
    EVIDENCE_KINDS,
    derive_mastery_state,
    evidence_rank,
    normalize_evidence_kind,
)

logger = logging.getLogger(__name__)

#: How many concepts a learner's record returns at most. Chosen by recency,
#: so the cap drops the least recently touched rather than an arbitrary slice.
RECORD_CAP = 100


class RungRecord(BaseModel):
    """One rung of one concept, as the learner actually demonstrated it."""

    kind: str
    #: Best demonstration of this rung, already damped for help used.
    confidence: float = Field(ge=0.0, le=1.0)
    #: True when at least one demonstration of this rung needed no hints.
    #: False means every time the learner reached this rung, they were helped
    #: there — which is a real difference and the product should say so.
    unaided: bool


class ConceptRecord(BaseModel):
    """Everything this learner has shown about one concept."""

    concept_id: str
    #: NOT_SEEN | EXPOSED | RECOGNIZED | EXPLAINED | APPLIED | TRANSFERRED |
    #: RETAINED | MASTERED — from `derive_mastery_state`, the same function the
    #: mastery projection uses.
    state: str
    #: Every rung reached, weakest first. A rung absent here was never shown.
    rungs: List[RungRecord] = Field(default_factory=list)
    #: The strongest rung reached, or None when nothing was.
    best_rung: Optional[str] = None
    #: The most recent error the grader named, if any. Survives a later
    #: correct answer, because the misconception is what remediation targets.
    misconception: Optional[str] = None
    #: The next rung worth attempting. None when the learner has shown the
    #: strongest thing the ladder describes.
    next_rung: Optional[str] = None
    last_seen: Optional[str] = None


class LearnerRecord(BaseModel):
    """A learner's own record, most recently worked on first."""

    concepts: List[ConceptRecord] = Field(default_factory=list)
    #: True when the learner has evidence but this view could not be built.
    #: Distinct from an empty record, which means they have not shown anything
    #: yet — a learner must never be told they have done nothing because a
    #: query failed.
    unavailable: bool = False


def next_rung_after(best: Optional[str]) -> Optional[str]:
    """The rung worth attempting next.

    `exposure` is skipped as a target: being shown something again is not a
    demonstration to aim for. From nothing, the first real target is
    recognition; from the top of the ladder there is nothing further.
    """
    if best is None:
        return "recognition"
    rank = evidence_rank(best)
    if rank < 0:
        return "recognition"
    if rank + 1 >= len(EVIDENCE_KINDS):
        return None
    following = EVIDENCE_KINDS[rank + 1]
    return following


def build_records(
    rung_rows: Iterable[Any],
    misconception_rows: Iterable[Any] = (),
) -> List[ConceptRecord]:
    """Fold raw rows into one record per concept.

    `rung_rows` are ``(concept_id, evidence_type, max_confidence, min_hints,
    last_seen)``. `misconception_rows` are ``(concept_id, misconception,
    timestamp)``, most recent first.

    Rows naming no concept or no recognised rung are skipped rather than
    guessed at — the same rule the projection and the summary follow, so the
    three cannot disagree about what counts as evidence.
    """
    by_concept: Dict[str, Dict[str, Any]] = {}

    for row in rung_rows or []:
        concept_id, evidence_type = row[0], row[1]
        if not concept_id:
            continue
        kind = normalize_evidence_kind(evidence_type)
        if not kind:
            continue
        try:
            confidence = max(0.0, min(1.0, float(row[2] or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            hints = int(row[3] or 0)
        except (TypeError, ValueError):
            hints = 0
        last_seen = row[4] if len(row) > 4 else None

        entry = by_concept.setdefault(
            concept_id, {"rungs": {}, "last_seen": None}
        )
        existing = entry["rungs"].get(kind)
        if existing is None:
            entry["rungs"][kind] = {"confidence": confidence, "unaided": hints <= 0}
        else:
            # Best demonstration wins on confidence, but `unaided` is sticky:
            # having once reached this rung without help is the claim it
            # makes, and a later hinted attempt does not retract it. Taking
            # the newer row's flag wholesale would.
            existing["confidence"] = max(existing["confidence"], confidence)
            existing["unaided"] = existing["unaided"] or hints <= 0
        if last_seen is not None and (
            entry["last_seen"] is None or last_seen > entry["last_seen"]
        ):
            entry["last_seen"] = last_seen

    latest_misconception: Dict[str, str] = {}
    for row in misconception_rows or []:
        concept_id, misconception = row[0], row[1]
        if not concept_id or not misconception:
            continue
        # Rows arrive most recent first; the first one seen for a concept wins.
        latest_misconception.setdefault(concept_id, str(misconception))

    records: List[ConceptRecord] = []
    for concept_id, entry in by_concept.items():
        rungs = entry["rungs"]
        if not rungs:
            continue
        ordered = sorted(rungs.items(), key=lambda pair: evidence_rank(pair[0]))
        best_rung = ordered[-1][0] if ordered else None
        state = derive_mastery_state(
            [{"kind": kind, "confidence": data["confidence"]} for kind, data in ordered]
        )
        last_seen = entry["last_seen"]
        records.append(
            ConceptRecord(
                concept_id=concept_id,
                state=state,
                rungs=[
                    RungRecord(kind=kind, confidence=data["confidence"], unaided=data["unaided"])
                    for kind, data in ordered
                ],
                best_rung=best_rung,
                misconception=latest_misconception.get(concept_id),
                next_rung=next_rung_after(best_rung),
                last_seen=last_seen.isoformat() if hasattr(last_seen, "isoformat") else None,
            )
        )

    # Most recently worked on first. Concepts with no usable timestamp sort
    # last rather than being dropped.
    records.sort(key=lambda record: (record.last_seen or "", record.concept_id), reverse=True)
    return records


async def learner_record(
    db: AsyncSession, user_id: Any, limit: int = RECORD_CAP
) -> LearnerRecord:
    """Read one learner's own evidence back to them.

    Never raises. A failure is reported as `unavailable`, not as an empty
    record: telling a learner they have demonstrated nothing because a query
    failed is the one error this view must not make.
    """
    from .models import LearningEvent

    try:
        learner_id = int(user_id)
    except (TypeError, ValueError):
        return LearnerRecord()

    capped = max(1, min(int(limit or RECORD_CAP), RECORD_CAP))

    try:
        has_evidence = (
            LearningEvent.user_id == learner_id,
            LearningEvent.concept_id.isnot(None),
            LearningEvent.evidence_type.isnot(None),
        )

        # Choose the concepts first, by recency, so the cap can only cut
        # between concepts and never through the middle of one — a record
        # missing some of its own rungs would understate what the learner did.
        capped_concepts = (
            select(LearningEvent.concept_id)
            .where(*has_evidence)
            .group_by(LearningEvent.concept_id)
            .order_by(func.max(LearningEvent.timestamp).desc())
            .limit(capped)
            .scalar_subquery()
        )

        rung_rows = (
            await db.execute(
                select(
                    LearningEvent.concept_id,
                    LearningEvent.evidence_type,
                    func.max(LearningEvent.evidence_confidence),
                    func.min(LearningEvent.hints_used),
                    func.max(LearningEvent.timestamp),
                )
                .where(*has_evidence, LearningEvent.concept_id.in_(capped_concepts))
                .group_by(LearningEvent.concept_id, LearningEvent.evidence_type)
            )
        ).all()

        misconception_rows = (
            await db.execute(
                select(
                    LearningEvent.concept_id,
                    LearningEvent.misconception,
                    LearningEvent.timestamp,
                )
                .where(
                    LearningEvent.user_id == learner_id,
                    LearningEvent.concept_id.in_(capped_concepts),
                    LearningEvent.misconception.isnot(None),
                )
                .order_by(LearningEvent.timestamp.desc())
                .limit(capped * 4)
            )
        ).all()

        return LearnerRecord(concepts=build_records(rung_rows, misconception_rows))
    except Exception:
        logger.exception("Learner record failed for user %s", user_id)
        return LearnerRecord(unavailable=True)
