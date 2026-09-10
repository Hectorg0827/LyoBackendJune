"""
Canonical evidence ladder — the server's definition of what counts as proof
that a learner knows something.

WHY THIS EXISTS

Mastery is currently decided in two unrelated places that never see each
other's work:

  * `personalization.PersonalizationEngine` — written by every chat check,
    read by chat's spaced-repetition nudge. This is where real learner data
    actually accumulates today.
  * `ai_classroom.MasteryState` — read by the live classroom's scene engine to
    adapt its teaching, but written only by `graph_service` (playback routes)
    and `interaction_service` (which has no callers at all).

The consequence is concrete: the Classroom adapts its teaching from a table
that nothing on the live path fills, so it cannot see what Chat already
taught the same learner. A learner who nailed a concept in Chat is taught it
from scratch in the Classroom.

`LearningEvent` is the fix. Both surfaces log evidence here, and the processor
projects that evidence into *both* mastery tables. Nothing is migrated and
nothing is dropped; the two tables become views of one event stream, which is
what lets them finally agree.

This module is the server twin of `web/src/lib/learner-model.mjs` in the
client repo. The two must define the same ladder, the same wire mapping and
the same mastery rule — a learner's progress cannot mean one thing to the
server and another to the screen. `tests/test_evidence_ladder.py` pins the
parts that would silently diverge.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

# ─── The ladder ──────────────────────────────────────────────────────────────

#: Weakest first. Order is meaning, not presentation: `evidence_rank` compares
#: by index, so reordering this changes what the product treats as stronger
#: proof.
EVIDENCE_KINDS: Tuple[str, ...] = (
    "exposure",      # instruction was delivered — proof of nothing on its own
    "recognition",   # picked the right answer in context
    "explanation",   # explained it acceptably
    "application",   # used it on a familiar problem
    "transfer",      # used it in a novel context
    "retention",     # retrieved it after a real interval
)

#: What the classroom actually puts on the wire.
#:
#: `InputField.evidence_type` in `ai_classroom/sdui_models.py` is
#: `Literal["explanation", "application", "transfer", "retrieval"]` — narrower
#: than the ladder, and it says "retrieval" where the ladder says "retention".
#: Adapting here rather than renaming either side keeps both honest: the
#: classroom keeps emitting the vocabulary it already emits, and the ladder
#: keeps the word that describes what was actually demonstrated.
WIRE_EVIDENCE_TO_KIND: Dict[str, str] = {
    "explanation": "explanation",
    "application": "application",
    "transfer": "transfer",
    "retrieval": "retention",
}

#: Where a piece of evidence came from. Recorded so a learner's history can be
#: read back per surface without guessing from event shape.
SOURCE_SURFACES: Tuple[str, ...] = ("chat", "classroom", "test_prep", "course")


def evidence_rank(kind: Optional[str]) -> int:
    """Strength of an evidence kind; -1 for anything unrecognised."""
    try:
        return EVIDENCE_KINDS.index(kind)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return -1


def normalize_evidence_kind(value: Optional[str]) -> Optional[str]:
    """Map a wire value onto the ladder.

    Returns ``None`` for anything unrecognised, deliberately. A new
    server-side evidence type must not be silently scored as ``exposure`` — and
    certainly not as ``transfer``. Callers record the event and leave mastery
    alone.
    """
    if value in EVIDENCE_KINDS:
        return value
    return WIRE_EVIDENCE_TO_KIND.get(value or "")


def is_stronger_evidence(a: Optional[str], b: Optional[str]) -> bool:
    """Is `a` stronger proof than `b`?"""
    return evidence_rank(normalize_evidence_kind(a)) > evidence_rank(
        normalize_evidence_kind(b)
    )


# ─── Mastery ─────────────────────────────────────────────────────────────────

MASTERY_STATES: Tuple[str, ...] = (
    "NOT_SEEN",
    "EXPOSED",
    "RECOGNIZED",
    "EXPLAINED",
    "APPLIED",
    "TRANSFERRED",
    "RETAINED",
    "MASTERED",
)

#: The state each kind of evidence, on its own, can justify.
STATE_FOR_EVIDENCE: Dict[str, str] = {
    "exposure": "EXPOSED",
    "recognition": "RECOGNIZED",
    "explanation": "EXPLAINED",
    "application": "APPLIED",
    "transfer": "TRANSFERRED",
    "retention": "RETAINED",
}

#: MASTERED is not a high score on one thing. It requires that the learner used
#: the concept on a familiar problem, used it somewhere new, and still had it
#: after a delay.
MASTERY_REQUIRES: Tuple[str, ...] = ("application", "transfer", "retention")

#: Below this, evidence still records the rung it reached but cannot count
#: toward MASTERED. A barely-scraped transfer is a transfer, not proof of
#: durable mastery.
MASTERY_CONFIDENCE_FLOOR: float = 0.7


# ─── Assistance ──────────────────────────────────────────────────────────────

#: How much support the learner needed, as a damping factor on confidence.
#: Keyed by the hint ladder in the shared classroom contract.
#:
#: Asking for help is never failure and never demotes the rung. It means the
#: demonstration proves less about unaided ability, so the confidence attached
#: to it is lower.
HINT_DAMPING: Dict[str, float] = {
    "nudge": 0.9,
    "principle": 0.75,
    "worked_step": 0.55,
    "full_example": 0.35,
    "prerequisite": 0.3,
}


def strongest_hint_level(*levels: Optional[str]) -> Optional[str]:
    """The most help among these, or None if none is recognised.

    "Most help" is the lowest damping factor, not the last one asked for. A
    learner who took a nudge and then a full worked example was walked through
    it; scoring that demonstration as if the nudge were the whole story would
    overstate what they showed unaided.

    Unknown names are ignored rather than ranked, so a new client-side rung
    cannot silently register as the weakest kind of help.
    """
    best: Optional[str] = None
    for level in levels:
        if level not in HINT_DAMPING:
            continue
        if best is None or HINT_DAMPING[level] < HINT_DAMPING[best]:
            best = level
    return best


def confidence_after_hints(
    base_confidence: float,
    hint_level: Optional[str] = None,
    hints_used: int = 0,
) -> float:
    """Damp a confidence score by how much help the learner needed.

    `hint_level` is the named rung when the surface knows it. `hints_used` is
    the fallback for surfaces that only count hints (chat's check does), and
    damps geometrically so three nudges never read as an unaided answer.
    """
    try:
        base = max(0.0, min(1.0, float(base_confidence)))
    except (TypeError, ValueError):
        return 0.0

    if hint_level:
        return base * HINT_DAMPING.get(hint_level, 1.0)

    if hints_used and hints_used > 0:
        return base * (HINT_DAMPING["nudge"] ** min(hints_used, 5))

    return base


# ─── Deriving state ──────────────────────────────────────────────────────────

def derive_mastery_state(evidence: Iterable[Dict]) -> str:
    """Derive a mastery state from the evidence collected for one concept.

    `evidence` is an iterable of ``{"kind": str, "confidence": float}``.

    Advisory, not authoritative: the numeric ``mastery_score`` still comes from
    the DKT engine. This exists so every surface can say *why* it shows what it
    shows, in words that mean the same thing everywhere.
    """
    seen: Dict[str, float] = {}

    for entry in evidence or []:
        kind = normalize_evidence_kind((entry or {}).get("kind"))
        # Unrecognised evidence is logged by the caller but advances no rung.
        if not kind:
            continue
        try:
            confidence = max(0.0, min(1.0, float((entry or {}).get("confidence") or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        # Keep the best demonstration of each kind.
        seen[kind] = max(seen.get(kind, 0.0), confidence)

    if not seen:
        return "NOT_SEEN"

    if all(seen.get(kind, 0.0) >= MASTERY_CONFIDENCE_FLOOR for kind in MASTERY_REQUIRES):
        return "MASTERED"

    best_state = "NOT_SEEN"
    best_rank = -1
    for kind in seen:
        rank = evidence_rank(kind)
        if rank > best_rank:
            best_rank = rank
            best_state = STATE_FOR_EVIDENCE[kind]
    return best_state


# ─── Reading a graded answer as evidence ─────────────────────────────────────

def evidence_from_graded_answer(
    *,
    correct: bool,
    bailed_out: bool = False,
    misconception: Optional[str] = None,
    hints_used: int = 0,
    hint_level: Optional[str] = None,
    evidence_type: Optional[str] = None,
) -> Optional[Dict]:
    """Turn a server-graded answer into one piece of evidence.

    Three rules the product depends on, enforced in one place:

    * A skipped question is neutral. ``bailed_out`` yields ``None`` — no
      evidence at all, rather than evidence of failure. Not answering is not
      getting it wrong.
    * Correctness is the server's verdict, passed in. This function reads a
      verdict; it never reaches one.
    * A wrong answer still produced exposure and still carries its
      misconception forward, so remediation can target the actual error rather
      than just re-teaching.

    `hint_level` names the rung of help the learner took, and takes precedence
    over the bare `hints_used` count: one full worked example proves far less
    about unaided ability than three nudges do, and counting alone cannot tell
    them apart. Surfaces that only count hints keep passing `hints_used`.
    """
    if bailed_out:
        return None

    if not correct:
        return {
            "kind": "exposure",
            "confidence": 0.0,
            "misconception": misconception,
        }

    # A correct answer is worth the rung the question actually asked for.
    # Absent a declared type it is recognition — the weakest positive rung —
    # because a multiple-choice hit is not application and is certainly not
    # mastery, however confident the score attached to it looks.
    kind = normalize_evidence_kind(evidence_type) or "recognition"
    return {
        "kind": kind,
        "confidence": confidence_after_hints(
            1.0, hint_level=hint_level, hints_used=hints_used
        ),
        "misconception": misconception,
    }


# ─── What a client is allowed to assert ──────────────────────────────────────

def sanitize_client_event(event):
    """Strip anything a learner's device must not be trusted to decide.

    `POST /api/v1/evolution/events` accepts a `LearningEventCreate` straight
    from an authenticated client. That schema carries `evidence_type`,
    `evidence_confidence`, `measurable_outcome` and `skill_ids_json` — so a
    client could post itself a transfer demonstration at full confidence, or
    ask the processor to run a DKT update on a skill it names, and the learner
    model would believe it. Correctness is the server's to decide; that is the
    whole reason the check endpoint grades from a stored block rather than
    from what the client says happened.

    A client may still say *what it did*. It may not say *what that proved*.
    So an event from a client is recorded as `exposure` with no graded
    outcome, which the projection treats as instruction: the learner has met
    this concept, no counts move, no score changes, nothing is claimed. A
    surface that wants a demonstration to count has to be graded by the
    server, which every real one already is.

    `hints_used` and `misconception` are left alone. Neither can flatter a
    learner — one only ever damps confidence, and the other is a note about an
    error.
    """
    event.evidence_type = "exposure" if event.concept_id else None
    event.evidence_confidence = 0.0 if event.concept_id else None
    event.measurable_outcome = None
    event.skill_ids_json = None
    if event.source_surface not in SOURCE_SURFACES:
        event.source_surface = None
    return event
