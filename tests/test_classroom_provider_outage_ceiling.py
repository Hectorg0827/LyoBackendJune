"""Classroom provider outages never turn into infinite Retry loops or grades."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import TeachingUnavailable
from lyo_app.ai_classroom.sdui_models import ActionIntent


def context():
    return SimpleNamespace(
        user_id="test-synthetic-owner",
        language_code="en-US",
        lesson_title="Comparing fractions",
        topic="fractions",
        lesson_content="",
    )


def recovery_buttons(scene):
    return [
        component
        for component in scene.components
        if getattr(component, "action_intent", None) == ActionIntent.RETRY
    ]


@pytest.mark.asyncio
async def test_initial_provider_failure_is_bounded_and_ungraded():
    teacher = SimpleNamespace(plan=AsyncMock(
        side_effect=TeachingUnavailable("Provider temporarily unavailable")))
    session = AdaptiveSession(teacher)
    progress = {}
    trigger = SimpleNamespace(action_data={
        "action_intent": ActionIntent.RETRY,
        "record_scope": "unit",
    }, component_id=None)

    first = await session.run(context(), progress, trigger)
    second = await session.run(context(), progress, trigger)
    third = await session.run(context(), progress, trigger)
    fourth = await session.run(context(), progress, trigger)

    assert teacher.plan.await_count == 3
    assert progress["startup_generation_failures"] == 3
    assert recovery_buttons(first) and recovery_buttons(second)
    assert not recovery_buttons(third)
    assert not recovery_buttons(fourth)
    assert "guided_state" not in progress
    assert any(
        "temporarily unavailable" in str(getattr(c, "content", ""))
        for c in third.components
    )


@pytest.mark.asyncio
async def test_new_lesson_entry_retries_after_outage_instead_of_staying_permanently_locked():
    teacher = SimpleNamespace(plan=AsyncMock(
        side_effect=TeachingUnavailable("Provider temporarily unavailable")))
    progress = {"startup_generation_failures": 3}
    trigger = SimpleNamespace(action_data={"welcome": True}, component_id=None)
    await AdaptiveSession(teacher).run(context(), progress, trigger)
    assert teacher.plan.await_count == 1
    assert progress["startup_generation_failures"] == 3
