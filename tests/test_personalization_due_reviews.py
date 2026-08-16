"""Tests for PersonalizationEngine.get_due_reviews.

Every check answered through /chat/check has been updating a SM-2 schedule
(`PersonalizationEngine._update_repetition_schedule`) since checks shipped —
nothing ever read it back out with enough context for a client to act on.
This is the read: one row per skill, most overdue first, with the mastery
estimate and last misconception attached so a client can say something real
("you were shaky on X") instead of just naming an opaque item id.
"""

from datetime import datetime, timedelta

import pytest

from lyo_app.personalization.models import LearnerMastery, SpacedRepetitionSchedule
from lyo_app.personalization.service import personalization_engine


async def _due_schedule(db_session, user_id, skill_id, item_id, days_overdue=1):
    schedule = SpacedRepetitionSchedule(
        user_id=user_id,
        skill_id=skill_id,
        item_id=item_id,
        interval=1,
        easiness_factor=2.5,
        repetitions=0,
        last_review=datetime.utcnow() - timedelta(days=days_overdue + 1),
        next_review=datetime.utcnow() - timedelta(days=days_overdue),
        last_grade=2,
    )
    db_session.add(schedule)
    await db_session.commit()
    return schedule


async def _mastery_row(db_session, user_id, skill_id, mastery_level, misconceptions=None):
    mastery = LearnerMastery(
        user_id=user_id,
        skill_id=skill_id,
        mastery_level=mastery_level,
        misconceptions=misconceptions or [],
    )
    db_session.add(mastery)
    await db_session.commit()
    return mastery


@pytest.mark.asyncio
async def test_get_due_reviews_returns_overdue_item_enriched(db_session):
    await _due_schedule(db_session, user_id=1, skill_id="square_roots", item_id="block-1", days_overdue=3)
    await _mastery_row(
        db_session, user_id=1, skill_id="square_roots", mastery_level=0.35,
        misconceptions=["confusing the root with a nearby square"],
    )

    due = await personalization_engine.get_due_reviews(db_session, user_id=1)

    assert len(due) == 1
    item = due[0]
    assert item["skill_id"] == "square_roots"
    assert item["mastery_level"] == 0.35
    assert item["last_misconception"] == "confusing the root with a nearby square"
    assert item["days_overdue"] >= 3


@pytest.mark.asyncio
async def test_get_due_reviews_excludes_not_yet_due_items(db_session):
    # Scheduled for the future — must not show up as due yet.
    schedule = SpacedRepetitionSchedule(
        user_id=1, skill_id="fractions", item_id="block-2",
        interval=6, easiness_factor=2.5, repetitions=2,
        next_review=datetime.utcnow() + timedelta(days=5),
    )
    db_session.add(schedule)
    await db_session.commit()

    due = await personalization_engine.get_due_reviews(db_session, user_id=1)
    assert due == []


@pytest.mark.asyncio
async def test_get_due_reviews_dedupes_to_one_row_per_skill_most_overdue_first(db_session):
    # Two distinct blocks trained the same skill; only the more overdue one
    # should surface, so a repeatedly-missed skill doesn't crowd the list.
    await _due_schedule(db_session, user_id=1, skill_id="square_roots", item_id="block-old", days_overdue=5)
    await _due_schedule(db_session, user_id=1, skill_id="square_roots", item_id="block-new", days_overdue=1)
    await _due_schedule(db_session, user_id=1, skill_id="fractions", item_id="block-3", days_overdue=2)

    due = await personalization_engine.get_due_reviews(db_session, user_id=1)

    skill_ids = [item["skill_id"] for item in due]
    assert skill_ids == ["square_roots", "fractions"]
    # The more-overdue of the two square_roots schedules won.
    assert due[0]["item_id"] == "block-old"


@pytest.mark.asyncio
async def test_get_due_reviews_respects_limit(db_session):
    for i in range(3):
        await _due_schedule(db_session, user_id=1, skill_id=f"skill_{i}", item_id=f"block-{i}", days_overdue=1)

    due = await personalization_engine.get_due_reviews(db_session, user_id=1, limit=2)
    assert len(due) == 2


@pytest.mark.asyncio
async def test_get_due_reviews_empty_for_a_learner_with_nothing_due(db_session):
    due = await personalization_engine.get_due_reviews(db_session, user_id=999)
    assert due == []
