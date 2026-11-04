"""Independent objective-grade checks for the staging AI classroom.

Ten correct-answer fixtures and seven incorrect-answer fixtures form the
minimum exact arithmetic gate. No network, paid model, or prompt opinion is
involved. The AI's semantic path is separately checked for open reasoning.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, Evaluation, LearningTask, PendingTask, validate_evaluation,
)


def fraction_task(expected, *, question="What fraction of the shape is shaded?",
                  criteria=None, example=None):
    return LearningTask(
        kind="apply",
        response_format="short_answer",
        target_index=0,
        scenario="A geometric shape is divided into equal parts, with some parts shaded.",
        question=question,
        response_hint="Write the fraction, for example 7/10.",
        criteria=criteria or ["Identify the correct fraction of shaded parts."],
        example_answer=example or expected,
    )


def pending(expected, **kwargs):
    return PendingTask(
        task=fraction_task(expected, **kwargs),
        speech="Count the shaded and total equal parts.",
        board_title="Shaded shape",
        board_content="Write selected parts over total equal parts.",
    )


@pytest.mark.parametrize("expected,answer", [
    ("7/10", "7/10"),
    ("4/7", "4/7"),
    ("10/10", "10/10"),
    ("7/7", "7/7"),
    ("1/2", "2/4"),
    ("7/10", "14/20"),
    ("10/10", "7/7"),
    ("7/7", "10/10"),
    ("5/9", "5 / 9"),
    ("2/3", "4/6"),
])
@pytest.mark.asyncio
async def test_all_ten_correct_fraction_answers_pass_without_model(expected, answer):
    model = AsyncMock(side_effect=AssertionError("Objective math must not use the model"))
    lesson = pending(expected)
    result = await AdaptiveTeacher(model).evaluate(
        SimpleNamespace(language_code="en-US"), lesson, answer
    )
    assert result.verdict == "correct"
    assert result.confidence == 1
    assert len(result.criteria) == 1 and result.criteria[0].met
    validate_evaluation(result, lesson.task, [answer])
    model.assert_not_awaited()


@pytest.mark.parametrize("expected,answer", [
    ("7/10", "7/7"),
    ("4/7", "7/4"),
    ("10/10", "7/10"),
    ("7/7", "10/7"),
    ("5/9", "5/0"),
    ("2/3", "1/3"),
    ("1/2", "1/3"),
])
@pytest.mark.asyncio
async def test_all_seven_incorrect_fraction_answers_are_not_praised(expected, answer):
    model = AsyncMock(side_effect=AssertionError("Objective math must not use the model"))
    lesson = pending(expected)
    result = await AdaptiveTeacher(model).evaluate(
        SimpleNamespace(language_code="en-US"), lesson, answer
    )
    assert result.verdict == "incorrect"
    assert result.confidence == 1
    assert len(result.criteria) == 1 and not result.criteria[0].met
    validate_evaluation(result, lesson.task, [answer])
    model.assert_not_awaited()


@pytest.mark.parametrize("kwargs,answer", [
    ({"criteria": ["Explain why the fraction has that numerator and denominator."]}, "7/10"),
    ({"question": "What fraction is shaded, and why? Explain your reasoning."}, "7/10"),
    ({"example": "1/2 is greater than 1/3"}, "1/2"),
])
@pytest.mark.asyncio
async def test_open_reasoning_or_ambiguous_reference_stays_with_semantic_teacher(kwargs, answer):
    model = AsyncMock(return_value=Evaluation(
        verdict="unavailable", confidence=0, question_clear=True,
        feedback="The teacher could not grade this yet.",
    ))
    result = await AdaptiveTeacher(model).evaluate(
        SimpleNamespace(language_code="en-US"), pending("7/10", **kwargs), answer
    )
    assert result.verdict == "unavailable"
    model.assert_awaited_once()


@pytest.mark.asyncio
async def test_follow_up_is_not_overridden_by_fraction_shortcut():
    model = AsyncMock(return_value=Evaluation(
        verdict="unavailable", confidence=0, question_clear=True,
        feedback="The teacher could not grade this yet.",
    ))
    lesson = pending("7/10")
    lesson.answers = ["I counted the colored parts"]
    lesson.follow_up = "What fraction is shaded?"
    result = await AdaptiveTeacher(model).evaluate(
        SimpleNamespace(language_code="en-US"), lesson, "7/10"
    )
    assert result.verdict == "unavailable"
    model.assert_awaited_once()


@pytest.mark.asyncio
async def test_spanish_fraction_feedback_is_in_spanish():
    model = AsyncMock(side_effect=AssertionError("Objective math must not use the model"))
    result = await AdaptiveTeacher(model).evaluate(
        SimpleNamespace(language_code="es-ES"),
        pending("7/7", question="¿Qué fracción de la figura está sombreada?"),
        "7/7",
    )
    assert result.verdict == "correct"
    assert "¡Correcto!" in result.feedback
    model.assert_not_awaited()
