"""What to learn next, and why.

WHY THIS EXISTS

Home's "Recommended For You" rendered `courses.list(0, 4)` — the first four
rows of the catalogue, identical for every learner. A comment in the page
said so plainly: "the generic catalog list used below for Recommended For
You". It is a milder version of the fabrication this product was cleaned up
to remove: not invented data, but a claim about the learner ("for you") that
nothing behind it supports.

WHAT A RECOMMENDATION IS HERE

Something the learner's own record says they should do next, with the reason
attached. The reason is not decoration. "Because you were shaky on
completing the square four days ago" is a different thing to be shown than an
unexplained card, and it is the only version a learner can disagree with —
which is what makes it honest rather than oracular.

Two sources, in priority order, both already in the product:

1. Concepts due for retrieval. The schedule says the memory is fading now;
   nothing else is more time-sensitive.
2. Concepts the learner is weakest on, from their mastery profile.

WHEN THERE IS NOTHING TO SAY

It returns nothing. A learner with no history gets no recommendations, and
Home already has an honest empty state for that. Filling the space with the
catalogue is what this replaces.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Why this was chosen. The client renders these as text, so a new reason must
#: be added to both sides deliberately rather than appearing as a raw slug.
REASON_DUE = "due_for_review"
REASON_WEAK = "needs_practice"

DEFAULT_LIMIT = 4


class Recommendation(BaseModel):
    """One concrete next thing, and why it was chosen."""

    concept_id: str
    #: One of REASON_DUE / REASON_WEAK.
    reason: str
    #: Human-readable, already assembled server-side so every client says the
    #: same thing about the same learner.
    detail: str
    #: 0..1, or None when the learner has never been assessed on it. Null and
    #: zero are different claims — see the client's `normalizeMastery`.
    mastery: Optional[float] = None
    days_overdue: int = Field(0, ge=0)


class RecommendationList(BaseModel):
    items: List[Recommendation] = Field(default_factory=list)


def _readable(concept_id: str) -> str:
    """Turn a slug back into something a person can read.

    Concepts are keyed as `compare_fractions`. Showing that to a learner is
    showing them our database.
    """
    return (concept_id or "").replace("_", " ").strip() or "this concept"


def build_recommendations(
    due_reviews: List[Dict[str, Any]],
    weaknesses: List[str],
    skills: Dict[str, float],
    limit: int = DEFAULT_LIMIT,
) -> RecommendationList:
    """Assemble the list from a learner's own record.

    Due reviews come first: the schedule says that memory is fading now, and
    nothing on the weak list is more time-sensitive than that.

    A concept never appears twice. If it is both due and weak, being due is
    the more specific and more urgent thing to say about it.
    """
    items: List[Recommendation] = []
    seen: set = set()

    for entry in due_reviews or []:
        concept_id = (entry or {}).get("skill_id")
        if not concept_id or concept_id in seen:
            continue
        seen.add(concept_id)
        overdue = int((entry or {}).get("days_overdue") or 0)
        misconception = (entry or {}).get("last_misconception")

        if misconception:
            # The specific error is more useful than the fact of being due.
            detail = f"You slipped on {_readable(misconception)} last time"
        elif overdue > 0:
            days = "day" if overdue == 1 else "days"
            detail = f"Due for a look — {overdue} {days} overdue"
        else:
            detail = "Due for a look today"

        items.append(
            Recommendation(
                concept_id=concept_id,
                reason=REASON_DUE,
                detail=detail,
                mastery=(entry or {}).get("mastery_level"),
                days_overdue=max(0, overdue),
            )
        )
        if len(items) >= limit:
            return RecommendationList(items=items)

    for concept_id in weaknesses or []:
        if not concept_id or concept_id in seen:
            continue
        seen.add(concept_id)
        items.append(
            Recommendation(
                concept_id=concept_id,
                reason=REASON_WEAK,
                detail="Worth another pass — this one has not stuck yet",
                mastery=(skills or {}).get(concept_id),
            )
        )
        if len(items) >= limit:
            break

    return RecommendationList(items=items)


async def recommendations_for_user(
    db: AsyncSession, user_id: Any, limit: int = DEFAULT_LIMIT
) -> RecommendationList:
    """This learner's next moves, or an empty list.

    Empty rather than raising, and empty rather than generic. Home has an
    honest empty state for a learner with no history; filling that space with
    the catalogue and calling it "for you" is what this replaces.
    """
    from .service import personalization_engine

    try:
        learner_id = int(user_id)
    except (TypeError, ValueError):
        return RecommendationList()

    try:
        due = await personalization_engine.get_due_reviews(db, learner_id, limit=limit)
    except Exception:
        logger.exception("Due reviews unavailable for user %s", user_id)
        due = []

    try:
        profile = await personalization_engine.get_mastery_profile(db, str(learner_id))
        weaknesses, skills = profile.weaknesses, profile.skills
    except Exception:
        logger.exception("Mastery profile unavailable for user %s", user_id)
        weaknesses, skills = [], {}

    return build_recommendations(due, weaknesses, skills, limit=limit)
