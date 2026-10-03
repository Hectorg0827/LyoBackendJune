"""The judge that reads the teaching, and what it is allowed to do about it.

These cover the plumbing and the policy: what the judge is asked, what it is
allowed to object to, and what happens on each answer it can give. The first
authenticated production validation caught fluent but contradictory teaching,
so learner-facing review is enabled by default while still failing open if the
reviewer itself is unavailable.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

from lyo_app.ai_classroom.adaptive_teaching import GuidedState
from lyo_app.ai_classroom.semantic_review import (
    JUDGE_PROMPT, SemanticVerdict, judge_enabled, model_semantic_judge,
)
from tests.adaptive_fixtures import ScriptedTeacher, context, plan


def a_turn(move="guided"):
    teacher, ctx = ScriptedTeacher(), context()
    return teacher._turn(ctx, GuidedState(owner="42", plan=plan()), move)


async def judge(verdict=None, raises=None):
    unit = plan().units[0]
    target = AsyncMock(side_effect=raises) if raises else AsyncMock(return_value=verdict)
    with patch("lyo_app.ai_classroom.semantic_review.model_json", target):
        allowed = await model_semantic_judge("guided", unit, a_turn())
    return allowed, target


# ─── What it does with each answer ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_sound_teaching_is_allowed_through():
    allowed, _ = await judge(SemanticVerdict(sound=True))
    assert allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    "implausible_distractor", "mislabelled_gap", "incorrect_teaching",
])
async def test_each_named_failure_rejects_the_turn(failure):
    allowed, _ = await judge(SemanticVerdict(
        sound=False, failure=failure, reason="Quoted offending text."))
    assert not allowed


@pytest.mark.asyncio
async def test_a_rejection_that_names_no_cause_is_not_a_rejection():
    """An unactionable "no" is the shape a judge returns when it had nothing to say.

    Taking teaching away from a learner needs a reason someone can check
    afterwards. Without one there is nothing to audit, nothing to count, and
    nothing to fix — so the turn ships, having passed the deterministic gate.
    """
    allowed, _ = await judge(SemanticVerdict(sound=False, failure=None))
    assert allowed


# ─── Failing open ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    TimeoutError("provider timed out"),
    ValueError("unparseable response"),
    RuntimeError("no provider configured"),
])
async def test_an_unreachable_judge_never_takes_teaching_offline(failure):
    """A reviewer being down is not evidence about the content.

    The alternative turns one degraded dependency into a learner looking at a
    retry button, which is a worse outcome than a turn reviewed by the
    deterministic gate alone.
    """
    allowed, _ = await judge(raises=failure)
    assert allowed


# ─── What it is asked ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_judge_is_given_the_content_not_the_authors_verdict():
    """It must read the unit and the whole turn and decide for itself."""
    _, called = await judge(SemanticVerdict(sound=True))
    payload = called.await_args.args[1]
    assert payload["skill"] and payload["objective"] and payload["material"]
    assert payload["turn"]["speech"] and payload["move"] == "guided"


def test_it_is_asked_only_about_what_the_schema_cannot_decide():
    for failure in ("implausible_distractor", "mislabelled_gap", "incorrect_teaching"):
        assert failure in JUDGE_PROMPT
    # And told not to re-litigate the deterministic rules, which would make the
    # gate slower and less predictable without making it stricter.
    assert "ALREADY verified" in JUDGE_PROMPT
    assert "not failures" in JUDGE_PROMPT  # style and preference are not rejections


def test_the_verdict_cannot_invent_a_new_reason_to_refuse_teaching():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SemanticVerdict(sound=False, failure="tone_is_unfriendly")


# ─── The default ────────────────────────────────────────────────────────────

def test_the_review_is_on_unless_explicitly_switched_off():
    for value, expected in [(None, True), ("false", False), ("", True),
                            ("true", True), ("TRUE ", True)]:
        with patch.dict(os.environ, {} if value is None else {"CLASSROOM_SEMANTIC_JUDGE": value},
                        clear=value is None):
            assert judge_enabled() is expected, value


def test_plain_adaptive_teacher_still_has_no_implicit_reviewer():
    """The live engine wires the reviewer; isolated teachers stay dependency-free."""
    from lyo_app.ai_classroom.adaptive_teaching import AdaptiveTeacher
    assert AdaptiveTeacher().semantic_judge is None
