"""Tests for the structured chat lesson composer.

These exercise the real ChatLesson schema and the real compose() control flow
with the model call stubbed — no network, no database.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from lyo_app.ai.lesson_composer import (
    ChatLesson,
    CheckItem,
    CheckOption,
    SectionKind,
    _entry_note,
    compose,
    slugify_skill,
)


# --- skill identity ---------------------------------------------------------

def test_slugify_gives_one_stable_skill_id_per_concept():
    # Mastery only accumulates if these collapse to one row.
    assert slugify_skill("Square Roots!") == slugify_skill("square roots") == "square_roots"
    assert slugify_skill("  ") == "general"
    assert len(slugify_skill("x" * 200)) <= 80


# --- grading is deterministic ----------------------------------------------

def _check():
    return CheckItem(
        question="What is the square root of 49?",
        options=[
            CheckOption(text="7"),
            CheckOption(text="9", reveals="confusing the root with a nearby square"),
            CheckOption(text="24.5", reveals="halving instead of finding the root"),
            CheckOption(text="Not sure — just explain it"),
        ],
        correct_index=0,
        explanation="7 x 7 = 49.",
        bailout_index=3,
    )


def test_wrong_answer_is_graded_wrong():
    """The original production bug: '9' was praised as correct."""
    check = _check()
    assert check.grade(1) is False
    assert check.grade(0) is True


def test_wrong_answer_carries_its_specific_misconception():
    check = _check()
    assert check.misconception_for(1) == "confusing the root with a nearby square"
    # A correct answer has no misconception to record.
    assert check.misconception_for(0) is None


def test_bailout_is_neither_correct_nor_a_misconception():
    check = _check()
    assert check.is_bailout(3) is True
    assert check.misconception_for(3) is None
    assert check.grade(3) is False


def test_out_of_range_selection_is_not_correct_and_does_not_crash():
    check = _check()
    assert check.grade(99) is False
    assert check.misconception_for(99) is None
    assert check.grade(-1) is False


# --- schema refuses malformed lessons ---------------------------------------

def test_correct_index_outside_options_is_rejected():
    with pytest.raises(Exception):
        CheckItem(
            question="q",
            options=[CheckOption(text="a"), CheckOption(text="b")],
            correct_index=5,
            explanation="e",
        )


def test_single_option_check_is_rejected():
    with pytest.raises(Exception):
        CheckItem(
            question="q",
            options=[CheckOption(text="only")],
            correct_index=0,
            explanation="e",
        )


# --- entry point selection --------------------------------------------------

def test_correct_probe_skips_the_basics():
    note = _entry_note({"correct": True})
    assert "CORRECTLY" in note
    assert "re-teach" in note.lower()


def test_wrong_probe_starts_from_the_definition_and_forbids_praise():
    note = _entry_note({"correct": False, "misconception": "confusing root with square"})
    assert "INCORRECTLY" in note
    assert "confusing root with square" in note
    assert "not tell them they were right" in note.lower()


def test_bailout_teaches_baseline_without_mentioning_the_skip():
    note = _entry_note({"bailed_out": True})
    assert "baseline" in note.lower()
    assert "do not mention" in note.lower()


# --- compose() control flow -------------------------------------------------

PROBE_JSON = {
    "sections": [{"kind": "hook", "text": "Square roots answer one question."}],
    "check": {
        "question": "What is the square root of 49?",
        "options": [
            {"text": "7"},
            {"text": "9", "reveals": "confusing root with nearby square"},
            {"text": "Not sure — just explain it"},
        ],
        "correct_index": 0,
        "explanation": "7 x 7 = 49.",
        "bailout_index": 2,
    },
    "next_directions": [],
}


def _run(coro):
    return asyncio.run(coro)


def test_compose_probe_returns_validated_lesson():
    with patch(
        "lyo_app.ai.lesson_composer._generate_json",
        new=AsyncMock(return_value=json.loads(json.dumps(PROBE_JSON))),
    ):
        lesson = _run(compose("square roots", mode="probe"))

    assert isinstance(lesson, ChatLesson)
    assert lesson.is_probe is True
    assert lesson.skill_id == "square_roots"
    assert lesson.sections[0].kind is SectionKind.hook
    assert lesson.check.correct_index == 0
    assert lesson.check.bailout_index == 2


def test_compose_falls_back_to_prose_when_model_unavailable():
    with patch("lyo_app.ai.lesson_composer._generate_json", new=AsyncMock(return_value=None)):
        assert _run(compose("square roots", mode="probe")) is None


def test_compose_falls_back_rather_than_showing_a_malformed_lesson():
    broken = {"sections": [{"kind": "not_a_real_kind", "text": "x"}], "next_directions": []}
    with patch("lyo_app.ai.lesson_composer._generate_json", new=AsyncMock(return_value=broken)):
        assert _run(compose("square roots", mode="teach")) is None


def test_probe_without_a_question_falls_back():
    no_check = {"sections": [{"kind": "hook", "text": "x"}], "next_directions": []}
    with patch("lyo_app.ai.lesson_composer._generate_json", new=AsyncMock(return_value=no_check)):
        assert _run(compose("square roots", mode="probe")) is None


def test_teach_prompt_carries_the_probe_outcome():
    captured = {}

    async def _capture(prompt):
        captured["prompt"] = prompt
        return {"sections": [{"kind": "core", "text": "x"}], "next_directions": []}

    with patch("lyo_app.ai.lesson_composer._generate_json", new=_capture):
        _run(compose("square roots", mode="teach", probe_result={"correct": False,
                                                                "misconception": "root vs square"}))

    assert "INCORRECTLY" in captured["prompt"]
    assert "root vs square" in captured["prompt"]


# --- plain-text fallback for non-block clients ------------------------------

def test_plain_text_fallback_includes_content_and_options():
    lesson = ChatLesson(
        topic="square roots",
        skill_id="square_roots",
        sections=[
            {"kind": "core", "text": "A square root undoes squaring."},
            {"kind": "example", "text": "Try 49.", "latex": "\\sqrt{49}=7"},
            {"kind": "reference", "text": "Common ones:",
             "table_markdown": "| n | root |\n|---|---|\n| 49 | 7 |"},
        ],
        check=_check(),
    )
    text = lesson.to_plain_text()

    assert "A square root undoes squaring." in text
    assert "\\sqrt{49}=7" in text
    assert "| 49 | 7 |" in text
    # Options are lettered so a text-only client can still answer.
    assert "A. 7" in text and "B. 9" in text
