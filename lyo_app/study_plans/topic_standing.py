"""Where a learner actually stands on the topics of one test.

A study plan names its topics as human text — "Quadratic equations", weighted
by how much of the exam they are. The learner's record names concepts by slug.
Nothing joined the two, so `get_plan_stats` computed its own "mastery" by
averaging the scores the *client* had reported for each session, and the plan
could tell a learner they had mastered a topic the evidence ladder said they
had only ever been exposed to.

This module is the join. It reads the same `MasteryState` rows the Classroom
teaches from, keyed the same way Chat keys them, so a plan's view of a learner
is the learner — not a second opinion assembled from self-report.

Since the Classroom began recording against persistent skill identities, that
join has two halves. Chat still writes a slug. The Classroom writes the id of
a `Concept` row, and the units it teaches are finer-grained than a plan topic
— "Divide by a two-digit number" under "Long division" — so no single row is
the topic. What they do share is a scope, derived from the topic's own name,
so a plan topic reaches its taught skills through `skill_identity.topic_scope`
and reads all of them. Both halves are read and folded together; neither is
guessed into the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.ai.lesson_composer import slugify_skill
from lyo_app.ai_classroom.models import Concept, MasteryState
from lyo_app.ai_classroom.skill_identity import topic_scope

#: A topic carries no weight of its own unless the intake gave it one. Equal
#: weighting is the honest default: it says "we were not told", not "this
#: topic does not matter".
DEFAULT_WEIGHT = 1.0

#: Guards a pathological profile — a thousand-topic list would otherwise turn
#: one dashboard request into a thousand-row IN clause.
TOPIC_CAP = 200


@dataclass(frozen=True)
class TopicStanding:
    """One topic of a test, and what the learner has actually shown on it."""

    topic: str
    concept_id: str
    weight: float
    #: None means never assessed. That is a different claim from 0.0, which
    #: means assessed and nothing demonstrated, and the two must not be
    #: rendered as the same number.
    mastery: Optional[float]
    attempts: int

    @property
    def assessed(self) -> bool:
        return self.mastery is not None


def topic_name(entry: Any) -> Optional[str]:
    """The topic's human name, however the intake happened to store it.

    Intake writes `{"name": ..., "weight": ..., "confidence": ...}`, but older
    profiles and hand-written ones carry bare strings. A profile that cannot be
    read is a profile whose plan silently loses topics, so accept both.
    """
    if isinstance(entry, str):
        name = entry.strip()
        return name or None
    if isinstance(entry, dict):
        raw = entry.get("name") or entry.get("topic") or entry.get("title")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def topic_weight(entry: Any) -> float:
    """How much of the test this topic is, defaulting to an equal share.

    Weights arrive as percentages, as 1-5 importance ratings, or not at all,
    and readiness divides by the total either way — so the scale does not
    matter as long as it is consistent within one profile. A negative or
    unparseable weight is treated as absent rather than allowed to subtract
    from a learner's readiness.
    """
    if not isinstance(entry, dict):
        return DEFAULT_WEIGHT
    try:
        weight = float(entry.get("weight", DEFAULT_WEIGHT))
    except (TypeError, ValueError):
        return DEFAULT_WEIGHT
    if weight <= 0 or weight != weight:  # NaN != NaN
        return DEFAULT_WEIGHT
    return weight


def concept_id_for_topic(topic: str) -> str:
    """Name the topic the way every other surface names it.

    `slugify_skill` is what Chat keys mastery on and what the classroom's
    evidence is canonicalised to, so a plan asking about "Quadratic Equations"
    reaches the row the learner filled in by answering questions about
    quadratic equations somewhere else entirely.
    """
    return slugify_skill(topic)


def _plan_topics(topics: Iterable[Any]) -> List[tuple]:
    """(name, concept_id, weight) per topic, de-duplicated, capped."""
    seen: Dict[str, tuple] = {}
    for entry in topics or []:
        name = topic_name(entry)
        if not name:
            continue
        concept_id = concept_id_for_topic(name)
        if concept_id in seen:
            # Two spellings of one topic are one topic. Keeping both would
            # double its weight in readiness and list it twice on a dashboard.
            continue
        seen[concept_id] = (name, concept_id, topic_weight(entry))
        if len(seen) >= TOPIC_CAP:
            break
    return list(seen.values())


def build_standings(
    topics: Iterable[Any],
    mastery_by_concept: Dict[str, tuple],
) -> List[TopicStanding]:
    """Join a profile's topics to whatever the learner's record holds.

    `mastery_by_concept` maps concept id to `(mastery_score, attempts)`. A
    topic with no row, or a row nobody has ever been assessed against, comes
    back with `mastery=None` — the plan has nothing to say about it yet, and
    saying "0%" would be inventing a result.
    """
    standings: List[TopicStanding] = []
    for name, concept_id, weight in _plan_topics(topics):
        row = mastery_by_concept.get(concept_id)
        mastery: Optional[float] = None
        attempts = 0
        if row is not None:
            score, attempts = row
            attempts = int(attempts or 0)
            # A row exists the moment a learner is *taught* the concept, with
            # no attempt behind it. That is exposure, not a result.
            if attempts > 0:
                mastery = max(0.0, min(1.0, float(score or 0.0)))
        standings.append(
            TopicStanding(
                topic=name,
                concept_id=concept_id,
                weight=weight,
                mastery=mastery,
                attempts=attempts,
            )
        )
    return standings


def readiness_fraction(standings: Sequence[TopicStanding]) -> Optional[float]:
    """How much of this test the learner has actually demonstrated, 0..1.

    Weighted by topic, with a never-assessed topic contributing nothing. That
    is deliberate and it is not the same judgement as `mastery=None` above:
    for a single concept "not assessed" is genuinely unknown, but for *am I
    ready for Friday's exam*, a topic you have never shown anything on is a
    topic you are not ready for.

    Returns None only when the profile lists no usable topics — then there is
    no test to be ready for, and a number would be about nothing.
    """
    total_weight = sum(s.weight for s in standings)
    if not standings or total_weight <= 0:
        return None
    earned = sum(s.weight * (s.mastery or 0.0) for s in standings)
    return max(0.0, min(1.0, earned / total_weight))


def days_until(test_date: Optional[date], today: date) -> Optional[int]:
    """Days left, negative once the date has passed, None if there is no date."""
    if test_date is None:
        return None
    return (test_date - today).days


def weakest_topics(
    standings: Sequence[TopicStanding], limit: int = 3
) -> List[TopicStanding]:
    """The topics most worth the learner's next hour.

    Weakest first, then heaviest first. A never-assessed topic sorts as zero,
    which puts it ahead of anything shaky — you cannot be ready for a topic
    you have never opened.

    It deliberately does *not* rank unopened topics above every measured one.
    An earlier version did, and it would have sent a learner to a topic worth
    one percent of the paper that they simply had not started, ahead of one
    worth forty that they had attempted and got entirely wrong. Both have
    nothing demonstrated; the heavier is the one that loses them the exam. So
    the two tie on mastery and weight breaks the tie.
    """
    return sorted(standings, key=lambda s: (s.mastery or 0.0, -s.weight))[:limit]


async def load_mastery(
    db: AsyncSession, user_id: int, concept_ids: Sequence[str]
) -> Dict[str, tuple]:
    """`{concept_id: (mastery_score, attempts)}` for slug-keyed evidence.

    Slug-identified concepts live in `objective_id`; `concept_id` carries
    graph UUIDs, which `load_taught_skill_mastery` below reads instead.
    `MasteryState` stores the user id as a string, which is what the
    projection writes.
    """
    if not concept_ids:
        return {}
    result = await db.execute(
        select(
            MasteryState.objective_id,
            MasteryState.mastery_score,
            MasteryState.attempts,
        ).where(
            MasteryState.user_id == str(user_id),
            MasteryState.objective_id.in_(list(concept_ids)),
        )
    )
    return {row[0]: (row[1], row[2]) for row in result.all() if row[0]}


async def load_taught_skill_mastery(
    db: AsyncSession, user_id: int, planned: Sequence[tuple]
) -> Dict[str, tuple]:
    """`{concept_id: (mastery_score, attempts)}` for what the Classroom taught.

    A plan topic is coarser than a taught skill: one hour on "Long division"
    is recorded against "Divide by a two-digit number" and "Interpret a
    remainder", each a `Concept` row of its own. They share the scope the
    topic's name derives, which is the only join available that does not
    involve guessing — and the reason `topic_scope` exists.

    A topic's score is the plain mean over the skills in it the learner has
    actually been assessed on, and its attempts are their sum. Mean rather
    than attempt-weighted so that one heavily drilled sub-skill cannot speak
    for the topic; over assessed skills only, because a unit the lesson has
    not reached yet is not a zero — it is silence, which is what a topic with
    no attempts already reports.
    """
    scopes = {}
    for name, concept_id, _ in planned:
        scope = topic_scope(name)
        # First spelling wins, matching the de-duplication in `_plan_topics`.
        if scope and scope not in scopes:
            scopes[scope] = concept_id
    if not scopes:
        return {}

    rows = (await db.execute(
        select(Concept.subject, MasteryState.mastery_score, MasteryState.attempts)
        .join(MasteryState, MasteryState.concept_id == Concept.id)
        .where(
            MasteryState.user_id == str(user_id),
            Concept.subject.in_(list(scopes)),
            # Only skills the Classroom recorded an identity for. A legacy
            # taxonomy row that happens to sit in this scope carries no
            # identity key and is not evidence of anything a learner did.
            Concept.identity_key.isnot(None),
        )
    )).all()

    folded: Dict[str, tuple] = {}
    for scope, score, attempts in rows:
        concept_id = scopes[scope]
        scores, total = folded.get(concept_id, ([], 0))
        attempts = int(attempts or 0)
        if attempts > 0:
            scores.append(float(score or 0.0))
        folded[concept_id] = (scores, total + attempts)
    return {
        concept_id: (sum(scores) / len(scores) if scores else 0.0, attempts)
        for concept_id, (scores, attempts) in folded.items()
    }


def _merge_mastery(*sources: Dict[str, tuple]) -> Dict[str, tuple]:
    """One standing per topic from evidence recorded under different keys.

    A learner can have both: chat answers filed under the slug, classroom
    work filed under skill ids. Attempts add up, and the two scores are
    combined in proportion to the attempts behind them, so neither half
    silently replaces the other.
    """
    merged: Dict[str, tuple] = {}
    for source in sources:
        for concept_id, (score, attempts) in source.items():
            attempts = int(attempts or 0)
            score = float(score or 0.0)
            if concept_id not in merged:
                merged[concept_id] = (score, attempts)
                continue
            prior_score, prior_attempts = merged[concept_id]
            total = prior_attempts + attempts
            if total <= 0:
                # Two rows of pure exposure. Keep the exposure, invent no score.
                merged[concept_id] = (0.0, 0)
                continue
            merged[concept_id] = (
                (prior_score * prior_attempts + score * attempts) / total, total,
            )
    return merged


async def standings_for_profile(
    db: AsyncSession, user_id: int, topics: Iterable[Any]
) -> List[TopicStanding]:
    """Where the learner stands on every topic of one test profile."""
    planned = _plan_topics(topics)
    by_slug = await load_mastery(db, user_id, [concept_id for _, concept_id, _ in planned])
    by_skill = await load_taught_skill_mastery(db, user_id, planned)
    return build_standings(topics, _merge_mastery(by_slug, by_skill))
