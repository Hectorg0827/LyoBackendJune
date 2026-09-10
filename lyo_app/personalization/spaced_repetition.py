"""One SM-2, for every surface that schedules a review.

WHY THIS EXISTS

There were two spaced-repetition systems doing the same job:

* `personalization.SpacedRepetitionSchedule`, written whenever a learner
  answers a check, read by Chat's due-review nudge and by Home. This is where
  every real schedule lives.
* `ai_classroom.ReviewSchedule`, with its own SM-2 inside
  `playback_routes`. Its only two writers — `spaced_repetition_service` and
  `interaction_service` — have no callers, so nothing on any live path fills
  it. The classroom's `/review/today` endpoint has therefore been serving
  every learner an empty queue, and `/review/submit` answering 404, while the
  same learner had items genuinely due in the other table.

That is the same shape as the mastery split: a real, learner-visible failure
hiding behind two tables that were never reconciled. A learner is told they
have nothing to review by one surface and handed five items by another.

So the scheduling maths lives here, once, and the classroom's endpoints read
and write the table that actually has the learner's schedule in it.

ON THE ALGORITHM

This is canonical SM-2. The previous chat path used a simplified variant that
moved the easiness factor by a flat ±0.1/−0.2 rather than by SuperMemo's
quality-weighted formula. Converging on the canonical form changes one number
in production: after a wrong answer the easiness factor now drops by 0.32
instead of 0.2, so a missed item comes back somewhat sooner. That is a real
behaviour change, in the direction of the published algorithm, and it is
called out rather than slipped in.
"""

from __future__ import annotations

from dataclasses import dataclass

#: SuperMemo's floor. Below this an item's interval stops growing usefully and
#: the learner is trapped re-reading something the schedule has given up on.
MINIMUM_EASINESS = 1.3

#: Below this the recall counts as failed and the ladder restarts. SM-2 draws
#: the line here: 3 is "correct, with serious difficulty".
PASSING_QUALITY = 3

#: First two intervals are fixed by the algorithm rather than computed.
FIRST_INTERVAL_DAYS = 1
SECOND_INTERVAL_DAYS = 6


@dataclass(frozen=True)
class Schedule:
    """The three numbers SM-2 carries between reviews."""

    easiness_factor: float
    interval_days: int
    repetitions: int


def clamp_quality(quality) -> int:
    """Coerce a recall grade onto SM-2's 0..5 scale.

    Out-of-range and unparseable values are clamped rather than rejected: this
    runs on a learner's review submission, and a client sending a bad grade
    should not cost them the review they just did.
    """
    try:
        value = int(quality)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, value))


def next_schedule(current: Schedule, quality) -> Schedule:
    """Apply one graded recall.

    A failed recall resets the interval ladder to the beginning but keeps the
    easiness factor it has earned, minus the penalty. That is deliberate in
    SM-2: forgetting an item once says the spacing was too aggressive, not
    that the learner has to re-earn everything they knew about it.
    """
    q = clamp_quality(quality)

    easiness = current.easiness_factor
    if easiness is None or easiness != easiness:  # None or NaN
        easiness = 2.5
    easiness = max(
        MINIMUM_EASINESS,
        easiness + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)),
    )

    if q < PASSING_QUALITY:
        return Schedule(easiness_factor=easiness, interval_days=FIRST_INTERVAL_DAYS, repetitions=0)

    repetitions = max(0, int(current.repetitions or 0)) + 1
    if repetitions == 1:
        interval = FIRST_INTERVAL_DAYS
    elif repetitions == 2:
        interval = SECOND_INTERVAL_DAYS
    else:
        interval = int(max(1, int(current.interval_days or 1)) * easiness)

    return Schedule(
        easiness_factor=easiness,
        interval_days=max(1, interval),
        repetitions=repetitions,
    )


#: How a pass/fail answer maps onto the grading scale.
#:
#: These are chosen to preserve what the chat path already does in production,
#: not as a claim about how well the learner recalled anything. A boolean
#: cannot tell a confident answer from a lucky one, and re-tuning every
#: existing learner's intervals is not part of folding two schedulers into
#: one.
#:
#: 5 reproduces the old correct-answer step exactly (+0.1 easiness, same
#: interval ladder). 2 reproduces the old failure structure — interval and
#: repetitions reset — and is the only place the numbers move at all: the
#: easiness penalty becomes SM-2's 0.32 rather than the previous flat 0.2, so
#: a missed item comes back somewhat sooner.
#:
#: The honest grade is recoverable later: `hints_used` and the hint rung
#: already say how much help an answer needed, which is most of what
#: separates a 5 from a 3.
QUALITY_FOR_CORRECT = 5
QUALITY_FOR_INCORRECT = 2
