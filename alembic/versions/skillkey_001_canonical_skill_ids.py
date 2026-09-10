"""Give the Classroom and Chat one key per skill, without losing either's work.

`LearnerMastery.skill_id` was written two ways. Chat writes `slugify_skill`
output — lowercased, underscored, capped at 80 characters — so "Square Roots!"
and "square roots" reach one row. The Classroom wrote the learning objective
as authored: "Compare fractions".

So one learner accumulated two rows for one concept, and neither surface
could see the other's evidence. The code now canonicalises at both call
sites; this migration brings the existing rows along.

WHY IT MERGES RATHER THAN RENAMES

A plain UPDATE would collide wherever the learner already has a slug row for
the same concept — which is the common case, since that is exactly the
duplication being fixed. And simply abandoning the classroom-keyed rows would
show a mid-course learner their progress resetting.

So rows that collapse onto the same key are combined: attempts, successes and
hints add up, misconceptions are unioned, the earliest first_attempt and the
latest last_seen win, and the mastery estimate is taken from whichever row has
more attempts behind it. Where there is no collision the row is simply
re-keyed.

Revision ID: skillkey_001
Revises: evidence_001
Create Date: 2026-09-10
"""
import json
import re

import sqlalchemy as sa
from alembic import op

revision = "skillkey_001"
down_revision = "evidence_001"
branch_labels = None
depends_on = None

TABLE = "learner_mastery"


def _slugify(topic: str) -> str:
    """A copy of `lyo_app.ai.lesson_composer.slugify_skill`.

    Deliberately inlined. A migration has to keep producing the same result
    years from now, against whatever the application code has become; importing
    the live function would let a later refactor silently change what this
    already-applied migration meant.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", (topic or "").strip().lower()).strip("_")
    return slug[:80] or "general"


def _loads(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _merge(into: dict, other: dict) -> dict:
    """Combine two mastery rows for the same learner and skill."""
    merged = dict(into)

    # Decided before the counts are summed, or the comparison is meaningless.
    # The estimate with more evidence behind it wins; a tie keeps the
    # incumbent, which is the row that was already correctly keyed.
    if (other.get("attempts") or 0) > (into.get("attempts") or 0):
        merged["mastery_level"] = other.get("mastery_level")
        merged["uncertainty"] = other.get("uncertainty")

    into = merged

    for field in ("attempts", "successes", "hints_used"):
        into[field] = (into.get(field) or 0) + (other.get(field) or 0)

    misconceptions = _loads(into.get("misconceptions")) or []
    for entry in _loads(other.get("misconceptions")) or []:
        if entry not in misconceptions:
            misconceptions.append(entry)
    into["misconceptions"] = json.dumps(misconceptions[-20:])

    for field, pick in (("first_attempt", min), ("last_seen", max), ("mastery_achieved", min)):
        left, right = into.get(field), other.get(field)
        if left and right:
            into[field] = pick(left, right)
        else:
            into[field] = left or right

    return into


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(TABLE):
        return

    columns = [c["name"] for c in insp.get_columns(TABLE)]
    if "skill_id" not in columns or "user_id" not in columns:
        return

    quoted = ", ".join(f'"{c}"' for c in columns)
    rows = [
        dict(zip(columns, row))
        for row in bind.execute(sa.text(f"SELECT {quoted} FROM {TABLE}")).fetchall()
    ]

    # Group by what each row *should* be keyed as.
    canonical: dict = {}
    for row in rows:
        skill_id = row.get("skill_id")
        if not skill_id:
            continue
        key = (row.get("user_id"), _slugify(skill_id))
        canonical.setdefault(key, []).append(row)

    for (user_id, slug), group in canonical.items():
        already_correct = [r for r in group if r.get("skill_id") == slug]
        stale = [r for r in group if r.get("skill_id") != slug]

        if not stale:
            continue

        if not already_correct:
            # Nothing to collide with: re-key the row with the most evidence
            # and fold any siblings into it.
            stale.sort(key=lambda r: (r.get("attempts") or 0), reverse=True)
            survivor, rest = stale[0], stale[1:]
        else:
            already_correct.sort(key=lambda r: (r.get("attempts") or 0), reverse=True)
            survivor, rest = already_correct[0], already_correct[1:] + stale

        merged = survivor
        for other in rest:
            merged = _merge(merged, other)

        assignments = {
            "skill_id": slug,
            "attempts": merged.get("attempts") or 0,
            "successes": merged.get("successes") or 0,
            "hints_used": merged.get("hints_used") or 0,
            "mastery_level": merged.get("mastery_level") or 0.0,
            "uncertainty": merged.get("uncertainty") if merged.get("uncertainty") is not None else 0.5,
            "misconceptions": merged.get("misconceptions"),
            "first_attempt": merged.get("first_attempt"),
            "last_seen": merged.get("last_seen"),
        }
        sets = ", ".join(f'"{k}" = :{k}' for k in assignments)
        bind.execute(
            sa.text(f'UPDATE {TABLE} SET {sets} WHERE id = :row_id'),
            {**assignments, "row_id": survivor["id"]},
        )

        for other in rest:
            bind.execute(
                sa.text(f"DELETE FROM {TABLE} WHERE id = :row_id"),
                {"row_id": other["id"]},
            )


def downgrade() -> None:
    # Deliberately irreversible. The original keys were free text and merged
    # rows have no record of which half contributed what; inventing a split
    # would be worse than leaving the canonical rows in place.
    pass
