"""Multi-exam Test Prep: a new intake must never reuse or mutate an old exam."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from lyo_app.study_plans.routes import NewTestStart, prep_state, start_new_test


@pytest.mark.asyncio
async def test_start_new_test_creates_separate_profile():
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            object(),  # User row lock
            SimpleNamespace(scalar_one_or_none=lambda: None),
        ]),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    db.add.side_effect = lambda profile: setattr(profile, "id", "new-exam-id")
    result = await start_new_test(
        body=NewTestStart(request_id="test-entry-12345678"),
        current_user=SimpleNamespace(id=72),
        db=db,
    )
    assert result == {"profile_id": "new-exam-id", "created": True}
    created = db.add.call_args.args[0]
    assert created.user_id == 72
    assert created.subject == "Pending Test"
    assert created.workflow_state["start_request_id"] == "test-entry-12345678"
    assert created.intake_transcript == []
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_uses_same_profile_and_never_adds_another():
    previous = SimpleNamespace(id="existing-exam-id")
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            object(),
            SimpleNamespace(scalar_one_or_none=lambda: previous),
        ]),
        add=Mock(),
        commit=AsyncMock(),
    )
    result = await start_new_test(
        body=NewTestStart(request_id="same-request-12345"),
        current_user=SimpleNamespace(id=72),
        db=db,
    )
    assert result == {"profile_id": "existing-exam-id", "created": False}
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_selecting_a_missing_or_other_user_profile_never_falls_back_to_latest():
    with patch("lyo_app.study_plans.routes.owned_profile", new=AsyncMock(return_value=None)) as lookup:
        with pytest.raises(HTTPException) as exc:
            await prep_state(profile_id="other-account-profile",
                             current_user=SimpleNamespace(id=72), db=AsyncMock())
        assert exc.value.status_code == 404
        lookup.assert_awaited_once()
        assert lookup.await_args.args[1] == 72
        assert lookup.await_args.args[2] == "other-account-profile"
