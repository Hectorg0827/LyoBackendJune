"""P0: never allow signed-in learners to mint their own XP."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from lyo_app.gamification.routes import award_xp


@pytest.mark.asyncio
async def test_learner_cannot_award_arbitrary_xp():
    fake_service = AsyncMock()
    xp_data = SimpleNamespace(
        action_type="course_completed", context_type="course", context_id=1,
        context_data={"pretend": "finished"}, xp_earned=999999,
    )
    with pytest.raises(HTTPException) as err:
        await award_xp(
            xp_data=xp_data,
            current_user=SimpleNamespace(id=19, is_superuser=False),
            db=AsyncMock(),
        )
    assert err.value.status_code == 403
    assert "trusted server-side" in str(err.value.detail)


@pytest.mark.asyncio
async def test_learner_without_superuser_property_is_denied():
    xp_data = SimpleNamespace(action_type="lesson_completed", xp_earned=9999)
    with pytest.raises((HTTPException, AttributeError)) as err:
        await award_xp(
            xp_data=xp_data,
            current_user=SimpleNamespace(id=19, is_superuser=False),
            db=AsyncMock(),
        )
    assert isinstance(err.value, HTTPException) and err.value.status_code == 403
