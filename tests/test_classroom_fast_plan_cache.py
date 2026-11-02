"""Cache only validated, learner-scoped plans to shorten repeat classroom startups."""

from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, _FAST_PLAN_CACHE, _FAST_PLAN_CACHE_SECONDS,
)
from tests.adaptive_fixtures import context, plan


@pytest.fixture(autouse=True)
def empty_plan_cache():
    _FAST_PLAN_CACHE.clear()
    yield
    _FAST_PLAN_CACHE.clear()


@pytest.mark.asyncio
async def test_repeat_start_reuses_only_the_same_learners_validated_plan():
    generate = AsyncMock(return_value=plan(1))
    lesson = context(user_id="startup-cache-learner", total_lessons=4, target_duration_minutes=20)
    first = await AdaptiveTeacher(generate, fast_start=True).plan(lesson)
    first.units[0].title = "Changed only in this caller"
    again = await AdaptiveTeacher(generate, fast_start=True).plan(lesson)
    assert generate.await_count == 1
    assert again.units[0].title == "Fraction skill 1"

    other_learner = context(user_id="startup-cache-other", total_lessons=4, target_duration_minutes=20)
    await AdaptiveTeacher(generate, fast_start=True).plan(other_learner)
    assert generate.await_count == 2

    changed_material = context(user_id="startup-cache-learner", total_lessons=4,
                               target_duration_minutes=20, lesson_content="A different authored lesson.")
    await AdaptiveTeacher(generate, fast_start=True).plan(changed_material)
    assert generate.await_count == 3


@pytest.mark.asyncio
async def test_cached_plan_expires_and_non_fast_path_does_not_use_it(monkeypatch):
    current = [100.0]
    monkeypatch.setattr("lyo_app.ai_classroom.adaptive_teaching.perf_counter", lambda: current[0])
    generate = AsyncMock(return_value=plan(1))
    lesson = context(user_id="startup-cache-expiry", total_lessons=4, target_duration_minutes=20)
    await AdaptiveTeacher(generate, fast_start=True).plan(lesson)
    current[0] += _FAST_PLAN_CACHE_SECONDS + 1
    await AdaptiveTeacher(generate, fast_start=True).plan(lesson)
    assert generate.await_count == 2
    await AdaptiveTeacher(generate, fast_start=False).plan(lesson)
    assert generate.await_count == 3
