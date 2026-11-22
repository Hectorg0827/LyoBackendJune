"""Diagnostic choice repair is targeted, bounded and never fabricates answers."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, DiagnosticTurn, GuidedState, TeachingUnavailable,
)
from tests.adaptive_fixtures import context, plan, probe


def valid_diagnostic():
    return DiagnosticTurn(
        speech="Look at these two equal pizzas. Which single piece is larger?",
        board_title="Compare equal portions",
        board_content="Two identical pizzas are cut into two or three equal pieces.",
        task=probe(),
        demonstration=[],
    )


def duplicate_diagnostic():
    value = valid_diagnostic().model_dump(mode="json")
    value["task"]["options"][2]["label"] = value["task"]["options"][1]["label"]
    return value


def do_not_prefetch(teacher):
    # No background work or network calls in this source-only test.
    teacher.schedule_package_prefetch = lambda *args, **kwargs: None
    teacher.schedule_next_unit_prefetch = lambda *args, **kwargs: None


def test_duplicate_diagnostic_still_fails_strict_validation():
    with pytest.raises(ValidationError, match="distinct visible answers"):
        DiagnosticTurn.model_validate(duplicate_diagnostic())


@pytest.mark.asyncio
async def test_second_attempt_receives_specific_duplicate_repair_and_stronger_routing():
    calls = []

    async def generate(_system, payload, schema):
        calls.append(deepcopy(payload))
        if len(calls) == 1:
            return schema.model_validate(duplicate_diagnostic())
        return valid_diagnostic()

    ctx = context()
    teacher = AdaptiveTeacher(generate=generate)
    do_not_prefetch(teacher)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    turn = await teacher.turn(ctx, state, "diagnose")
    assert len(calls) == 2
    assert "pairwise different" in calls[1]["repair"]
    assert "NEW concrete situation" in calls[1]["repair"]
    assert "misconception" in calls[1]["repair"]
    assert calls[1]["_escalate"] is True
    assert len(turn.task.options) == 4
    assert len(set(option.label for option in turn.task.options)) == 4


@pytest.mark.asyncio
async def test_repeated_duplicate_options_fail_closed_after_two_attempts():
    attempts = []

    async def generate(_system, payload, schema):
        attempts.append(deepcopy(payload))
        return schema.model_validate(duplicate_diagnostic())

    ctx = context()
    teacher = AdaptiveTeacher(generate=generate)
    do_not_prefetch(teacher)
    state = GuidedState(owner=ctx.user_id, plan=plan(1))
    with pytest.raises(TeachingUnavailable, match="clear checkpoint"):
        await teacher.turn(ctx, state, "diagnose")
    assert len(attempts) == 2
    assert attempts[1]["_escalate"] is True
