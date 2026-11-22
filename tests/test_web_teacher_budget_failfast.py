"""Guardrail: exhausted Classroom AI spend never triggers repair retries.

These tests are source-level and invoke no model/network/database.
"""
import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, TeachingUnavailable,
)
from lyo_app.ai_classroom.trial_budget import ClassroomTrialBudgetExceeded
from tests.adaptive_fixtures import context


@pytest.mark.asyncio
async def test_trial_budget_rejection_exits_once_without_second_model_attempt(caplog):
    attempts = []

    async def deny(*args, **kwargs):
        attempts.append(1)
        raise ClassroomTrialBudgetExceeded("Classroom AI trial $60 budget exhausted")

    teacher = AdaptiveTeacher(generate=deny, fast_start=False)
    with pytest.raises(TeachingUnavailable, match="budget controls"):
        await teacher.plan(context())
    assert len(attempts) == 1, "Budget-denied plan must not trigger repair attempt"
    assert "Classroom AI trial $60 budget exhausted" in caplog.text


@pytest.mark.asyncio
async def test_malformed_plan_still_gets_one_bounded_repair_attempt():
    attempts = []

    async def invalid(*args, **kwargs):
        attempts.append(1)
        raise ValueError("invalid schema")

    teacher = AdaptiveTeacher(generate=invalid, fast_start=False)
    with pytest.raises(TeachingUnavailable, match="validated pathway"):
        await teacher.plan(context())
    assert len(attempts) == 2, "Malformed plan deserves one bounded repair"


@pytest.mark.asyncio
async def test_no_provider_or_learners_logged_on_budget_denial(caplog):
    async def deny(*args, **kwargs):
        raise ClassroomTrialBudgetExceeded("Classroom trial ledger is unavailable")
    teacher = AdaptiveTeacher(generate=deny)
    with pytest.raises(TeachingUnavailable):
        await teacher.plan(context())
    assert "Classroom trial ledger is unavailable" in caplog.text
    assert "learner_context" not in caplog.text
    assert "model_json" not in caplog.text
