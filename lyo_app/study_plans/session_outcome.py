"""What a study session actually produced, decided by the server.

`POST /me/study_plans/sessions/{id}/complete` used to take
`performance_score` as a query parameter: the learner's device declared how
well the learner had done, the number was stored as their performance, and the
progress dashboard averaged those numbers into "mastery_by_topic". Anyone with
a token could post themselves to full marks on every topic of their exam.

That is the same rule broken for the third time on this codebase — after the
answer keys that travelled with the question and `POST /evolution/events`
accepting client-declared evidence rungs. A client may say what it did. It may
never say what that proved.

So the outcome is read back out of the evidence the server itself recorded
while the session was open. Where the server graded nothing, the session is
completed with **no score** rather than an invented one: a session spent
reading is a real session, and pretending to have measured it would be the
fabrication this whole workstream exists to remove.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.events.evidence import normalize_evidence_kind
from lyo_app.events.models import LearningEvent

#: How far before completion evidence may still count toward this session.
#: A session left open for a week must not sweep up the whole week's work on
#: that topic and report it as one sitting, so the window is the session's own
#: length with generous slack for overrun. See `window_start` for why it is
#: measured back from completion rather than anchored to the scheduled slot.
WINDOW_SLACK = 4
MINIMUM_WINDOW = timedelta(hours=2)

#: Evidence of instruction is not evidence of performance. A learner who was
#: taught something — or who dragged a point on a number line — has not
#: thereby demonstrated it. `measurable_outcome` is what separates the two:
#: the graded result, 1.0 correct, 0.0 wrong, and None when nothing was ever
#: asked. A wrong answer and a lesson delivered both sit on the `exposure`
#: rung at zero confidence, so the rung alone cannot tell them apart, and
#: reading only the rung would let an explorable click score as a failure.
#:
#: This is `project_event_to_mastery_state`'s test, deliberately the same one:
#: two places deciding "was this a demonstration" by different rules is how
#: the surfaces drifted apart in the first place.
def was_graded(measurable_outcome) -> bool:
    return measurable_outcome is not None


@dataclass(frozen=True)
class SessionOutcome:
    """What the server can honestly say about one completed session."""

    #: None when nothing gradeable happened. Not zero — that would claim the
    #: learner was measured and failed.
    score: Optional[float]
    #: How many graded demonstrations went into `score`.
    graded: int
    #: Rows where the concept was delivered but nothing was asked.
    seen: int

    @property
    def measured(self) -> bool:
        return self.score is not None


def window_start(duration_minutes: Optional[int], now: datetime) -> datetime:
    """The earliest moment whose evidence belongs to this session.

    Measured back from completion, and **not** anchored to `scheduled_at`.
    An earlier version floored the window at the scheduled slot, on the
    reasoning that work done before a session began is not that session's.
    Both ordinary cases break under it:

    * A learner who studies *ahead* of schedule — the session is at 4pm, they
      finish at 2pm — gets a window of `[4pm, 2pm]`. That is inverted, matches
      nothing by construction, and records someone who just demonstrated the
      topic as unmeasured.
    * A learner who does the work at 9am and only taps "done" that evening
      gets a window sitting entirely after the work, so the very evidence this
      endpoint exists to record is the evidence it cannot see.

    The slot bought nothing the cap does not already give. What the floor is
    actually for is stopping a session left open for a week from reporting the
    whole week as one sitting, and a span measured back from `now` does that
    on its own.

    The remaining imprecision is honest: recent work on this topic counts as
    this session's, because from the server's side that is what it is. Tap
    "done" long enough after the fact and the window finds nothing, and the
    session is recorded as unmeasured — which is true, rather than wrong.
    """
    # No clamp on `minutes`: the floor below already swallows every negative
    # or absent duration, so clamping first only looked like it was guarding
    # something. A missing, zero or nonsensical duration all land on
    # MINIMUM_WINDOW, which is the answer in each case.
    minutes = int(duration_minutes or 0)
    span = max(timedelta(minutes=minutes * WINDOW_SLACK), MINIMUM_WINDOW)
    return now - span


def outcome_from_evidence(rows: Sequence[tuple]) -> SessionOutcome:
    """Fold `(evidence_type, evidence_confidence, measurable_outcome)` rows.

    The score is the mean confidence across graded demonstrations. A wrong
    answer counts as a graded zero — the learner *was* measured there, and
    dropping it would let a session of nothing but wrong answers report the
    same score as a session of right ones. Instruction, and anything a client
    merely reported doing, is counted as seen and left out of the score.
    """
    confidences: List[float] = []
    seen = 0
    for kind, confidence, measurable_outcome in rows:
        if normalize_evidence_kind(kind) is None:
            # An evidence type this server does not recognise advances
            # nothing, here as everywhere else on the ladder.
            continue
        if not was_graded(measurable_outcome):
            seen += 1
            continue
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            # Graded, but the confidence is unreadable. The demonstration
            # happened; treat it as proving nothing rather than discarding it.
            value = 0.0
        confidences.append(max(0.0, min(1.0, value)))

    if not confidences:
        return SessionOutcome(score=None, graded=0, seen=seen)
    return SessionOutcome(
        score=sum(confidences) / len(confidences),
        graded=len(confidences),
        seen=seen,
    )


async def derive_session_outcome(
    db: AsyncSession,
    user_id: int,
    concept_id: str,
    duration_minutes: Optional[int],
    now: Optional[datetime] = None,
) -> SessionOutcome:
    """Read this session's outcome out of the learner's own event log."""
    now = now or datetime.utcnow()
    if not concept_id:
        return SessionOutcome(score=None, graded=0, seen=0)

    since = window_start(duration_minutes, now)
    result = await db.execute(
        select(
            LearningEvent.evidence_type,
            LearningEvent.evidence_confidence,
            LearningEvent.measurable_outcome,
        ).where(
            LearningEvent.user_id == user_id,
            LearningEvent.concept_id == concept_id,
            LearningEvent.evidence_type.isnot(None),
            LearningEvent.timestamp >= since,
            LearningEvent.timestamp <= now,
        )
    )
    return outcome_from_evidence(result.all())
