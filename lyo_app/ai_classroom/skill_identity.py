"""Resolve authored classroom skills to persistent Concept rows.

Titles are display text. Evidence, DKT updates and reviews use the database
ID. A scope is derived from the actual course or topic; equal-looking titles
in different subjects never confer credit on each other. Legacy slug records
are deliberately not guessed into a scope.
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.ai_classroom.models import Concept, ConceptPrerequisite

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillPlanIdentity:
    unit_ids: list[str]
    topic_id: str | None


def normalized_name(value: str) -> str:
    """Keep the whole name, including meaningful punctuation and non-Latin text."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def topic_scope(topic: str | None) -> str | None:
    """The scope every skill taught under one free-topic heading shares.

    Derived from the topic's own name and nothing else, so a reader that
    holds only a topic name — a study plan's topic list, say — can name the
    same scope the classroom taught into without guessing at anything. This
    is not slug matching: the scope is the whole normalized name, and it
    still cannot reach a skill taught inside an authored lesson, which lives
    under a `lesson:` scope of its own.
    """
    normalized = normalized_name(topic) if topic else ""
    return "topic:" + _digest(normalized) if normalized else None


def identity_scope(context) -> str | None:
    # A session id may masquerade as course_id on a free-topic classroom, so
    # a course is authoritative only when it has a resolved lesson as well.
    if context.course_id and context.lesson_id:
        # Repeated titles in two authored lessons are not proof of the same
        # skill. Only an explicit later identity mapping can join them.
        return "lesson:" + _digest(f"{context.course_id}\0{context.lesson_id}")
    return topic_scope(context.topic or context.lesson_title)


async def _resolve(db: AsyncSession, scope: str, title: str, objective: str) -> Concept:
    normalized = normalized_name(title)
    if not normalized:
        raise ValueError("A skill needs a specific title")
    # Titles are insufficient: "Compare prices" can name different skills
    # with different learning objectives even in one topic.
    key = _digest(normalized + "\0" + normalized_name(objective))
    lookup = select(Concept).where(Concept.subject == scope, Concept.identity_key == key)
    found = (await db.execute(lookup)).scalar_one_or_none()
    if found is not None:
        return found

    # Preserve the complete normalized title in the key even when the public
    # label exceeds the existing 200-character taxonomy column.
    display = title.strip()[:200]
    name = display if len(title.strip()) <= 200 else f"{display[:180]} [{key[:12]}]"
    same_name = (await db.execute(select(Concept.id).where(
        Concept.subject == scope, Concept.name == name,
    ))).scalar_one_or_none()
    if same_name is not None:
        name = f"{display[:180]} [{key[:12]}]"
    try:
        async with db.begin_nested():
            found = Concept(id=str(uuid4()), name=name, display_name=display,
                            subject=scope, identity_key=key)
            db.add(found)
            await db.flush()
        return found
    except IntegrityError:
        # A concurrent turn may have inserted the same skill. An unrelated
        # name collision is an error; never silently bind to a different row.
        found = (await db.execute(lookup)).scalar_one_or_none()
        if found is None and name == display:
            # A different objective won the name race. Preserve both IDs;
            # name's legacy uniqueness is separate from the new identity key.
            async with db.begin_nested():
                found = Concept(id=str(uuid4()), name=f"{display[:180]} [{key[:12]}]",
                                display_name=display, subject=scope, identity_key=key)
                db.add(found)
                await db.flush()
            return found
        if found is None:
            raise
        return found


def _would_cycle(target: str, prerequisite: str, edges: set[tuple[str, str]]) -> bool:
    pending, visited = [prerequisite], set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(pre for skill, pre in edges if skill == current)
    return False


async def resolve_skill_plan(db: AsyncSession, context, plan) -> SkillPlanIdentity:
    """Create scoped skills and only the direct prerequisites the plan names.

    Edges inform teaching and future sequencing. They never prove a learner
    passed the prerequisite and never block completion of a harder unit.
    """
    # Review entry carries the canonical concept ID. It is populated by
    # ContextAssembler only after checking the learner's real due schedule,
    # so reusing it cannot be used by a client to mint retention on an
    # arbitrary concept. One due concept is one retrieval unit.
    review_concept_id = getattr(context, "review_concept_id", None)
    mode = getattr(getattr(context, "classroom_mode", None), "value", None)
    if mode == "review" and review_concept_id:
        if len(plan.units) != 1:
            raise ValueError("A due review must target exactly one concept")
        from lyo_app.events.mastery_projection import is_concept_graph_id

        review_id = str(review_concept_id)
        if not is_concept_graph_id(review_id):
            # Legacy Chat/personalization rows predate the UUID Concept graph.
            # Their schedule identity is still authoritative; preserve it
            # exactly rather than inventing a lookalike Concept.
            return SkillPlanIdentity(unit_ids=[review_id], topic_id=review_id)

        reviewed = await db.get(Concept, review_id)
        if reviewed is None:
            raise ValueError("Due review concept no longer exists")
        return SkillPlanIdentity(unit_ids=[reviewed.id], topic_id=reviewed.id)

    scope = identity_scope(context)
    if scope is None:
        return SkillPlanIdentity(unit_ids=[], topic_id=None)

    # Serialize graph writes within a scope on PostgreSQL. Otherwise two
    # concurrent plans could each see no reverse edge and insert a cycle.
    if db.get_bind().dialect.name == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8], "big", signed=True)
        await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})

    units = [await _resolve(db, scope, unit.title, unit.objective) for unit in plan.units]
    topic = context.lesson_title or context.topic
    topic_skill = await _resolve(db, scope, topic, context.learning_objective or topic) if topic else None

    titles = {normalized_name(unit.title): i for i, unit in enumerate(plan.units)}
    existing = (await db.execute(
        select(ConceptPrerequisite.concept_id, ConceptPrerequisite.prerequisite_id)
        .join(Concept, Concept.id == ConceptPrerequisite.concept_id)
        .where(Concept.subject == scope)
    )).all()
    edges = set(existing)
    for i, unit in enumerate(plan.units):
        for title in unit.prerequisite_titles:
            prerequisite_index = titles[normalized_name(title)]
            pair = (units[i].id, units[prerequisite_index].id)
            if pair in edges:
                continue
            if _would_cycle(*pair, edges):
                raise ValueError("Prerequisite cycle between saved classroom skills")
            try:
                async with db.begin_nested():
                    db.add(ConceptPrerequisite(concept_id=pair[0], prerequisite_id=pair[1]))
                    await db.flush()
            except IntegrityError:
                same = await db.get(ConceptPrerequisite, pair)
                if same is None:
                    raise
                logger.debug("Concurrent classroom prerequisite already saved")
            edges.add(pair)

    return SkillPlanIdentity([unit.id for unit in units], topic_skill.id if topic_skill else None)
