"""Read the persisted learner ledger after grading, retry and processing failure."""
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from lyo_app.auth.models import User
from lyo_app.events.models import LearningEvent, EventType
from lyo_app.events.processor import _award_verified_learning_xp, _process_evolution_loop
from lyo_app.gamification.models import Achievement, AchievementType, UserXP, UserLevel, Streak, UserAchievement
from lyo_app.gamification.routes import get_gamification_overview, get_my_achievements
from lyo_app.gamification.service import GamificationService
from lyo_app.tenants.models import Organization


async def learner(db):
    db.add(Organization(id=1, name="Launch test", slug="launch-test"))
    user = User(email="launch-ledger@example.test", username="launch-ledger", hashed_password="not-a-login")
    db.add(user)
    await db.commit()
    return user.id


async def checkpoint(db, user_id, **overrides):
    event = LearningEvent(user_id=user_id, event_type=EventType.CLASSROOM_DEMONSTRATION,
                          source_surface="classroom", measurable_outcome=1.0,
                          evidence_confidence=0.9, **overrides)
    db.add(event)
    await db.commit()
    return event


@pytest.mark.asyncio
async def test_graded_checkpoint_updates_real_xp_level_streak_and_owned_achievement_once(db_session):
    user_id = await learner(db_session)
    db_session.add(Achievement(name="First checkpoint", description="One graded answer",
        type=AchievementType.LEARNING, criteria={"type": "lesson_count", "count": 1}, xp_reward=5))
    await db_session.commit()
    event = await checkpoint(db_session, user_id)
    assert await _award_verified_learning_xp(db_session, event)
    assert not await _award_verified_learning_xp(db_session, event)
    db_session.expire_all()
    total = (await db_session.execute(select(func.sum(UserXP.xp_earned)).where(UserXP.user_id == user_id))).scalar_one()
    level = (await db_session.execute(select(UserLevel).where(UserLevel.user_id == user_id))).scalar_one()
    streak = (await db_session.execute(select(Streak).where(Streak.user_id == user_id))).scalar_one()
    assert total == level.total_xp == 25  # 20 verified-answer XP + one 5-XP achievement.
    assert streak.current_count == 1
    rows = await get_my_achievements(skip=0, limit=50, completed_only=True,
                                    current_user=SimpleNamespace(id=user_id), db=db_session)
    assert len(rows) == 1 and rows[0].is_completed
    assert await get_my_achievements(skip=0, limit=50, completed_only=True,
        current_user=SimpleNamespace(id=user_id + 1), db=db_session) == []
    overview = await get_gamification_overview(current_user=SimpleNamespace(id=user_id), db=db_session)
    assert overview["xp_summary"]["total"] == 25
    assert overview["achievements"]["completed"] == 1
    assert overview["learning"] == {"courses_completed": 0, "total_hours": None}


@pytest.mark.asyncio
async def test_processing_failure_cannot_commit_partial_xp_or_level(db_session, monkeypatch):
    from lyo_app.events import processor
    from lyo_app.events.mastery_projection import ProjectionOutcome
    from unittest.mock import AsyncMock

    user_id = await learner(db_session)
    event = await checkpoint(db_session, user_id)
    event_id = event.id
    monkeypatch.setattr(processor, "project_event_to_mastery_state", AsyncMock(return_value=ProjectionOutcome.NOTHING_TO_PROJECT))
    monkeypatch.setattr(GamificationService, "_update_streak", AsyncMock(side_effect=RuntimeError("interrupted before commit")))
    await _process_evolution_loop(db_session, event)
    assert (await db_session.get(LearningEvent, event_id)).processed_for_mastery == -1
    for model in (UserXP, UserLevel, UserAchievement, Streak):
        assert (await db_session.execute(select(func.count()).select_from(model))).scalar_one() == 0
