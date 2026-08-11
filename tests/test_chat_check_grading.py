"""Tests for server-authoritative grading of in-chat checks.

The production bug these guard against: chat told a learner "Spot on!" after
they answered 9 to "what is the square root of 49?". Correctness must be
decided from the block the server itself emitted, never from the client and
never by a model re-reading the transcript.
"""

import pytest

from lyo_app.ai.schemas.smart_block import SmartBlock, QuizOption
from lyo_app.api.v1.stream_lyo2 import _find_check_block, _grade_check_block


def _check_block(with_bailout: bool = True):
    """Build a check block exactly the way the stream endpoint persists one."""
    options = [
        QuizOption(id="0", text="7"),
        QuizOption(id="1", text="9"),
        QuizOption(id="2", text="24.5"),
    ]
    block = SmartBlock.quiz(
        question="What is the square root of 49?",
        options=options,
        correct_index=0,
        explanation="7 x 7 = 49.",
    ).model_dump(mode="json")
    # Distractor annotations + bailout, as the composer attaches them.
    block["content"]["options"][1]["reveals"] = "confusing the root with a nearby square"
    block["content"]["options"][2]["reveals"] = "halving instead of taking the root"
    if with_bailout:
        block["content"]["options"].append({"id": "3", "text": "Not sure — just explain it"})
        block["content"]["bailout_index"] = 3
    block["metadata"] = {"skill_id": "square_roots"}
    return block


class _FakeMessage:
    def __init__(self, blocks):
        self.blocks = blocks


# --- the original bug -------------------------------------------------------

def test_wrong_answer_is_graded_wrong_not_praised():
    correct, bailed, misconception, correct_index, _ = _grade_check_block(_check_block(), 1)
    assert correct is False
    assert bailed is False
    assert correct_index == 0
    assert misconception == "confusing the root with a nearby square"


def test_right_answer_is_graded_right():
    correct, bailed, misconception, _, explanation = _grade_check_block(_check_block(), 0)
    assert correct is True
    assert bailed is False
    assert misconception is None
    assert explanation == "7 x 7 = 49."


# --- opt-out is not evidence ------------------------------------------------

def test_bailout_is_not_correct_and_carries_no_misconception():
    correct, bailed, misconception, _, _ = _grade_check_block(_check_block(), 3)
    assert bailed is True
    assert correct is False
    assert misconception is None


def test_without_a_bailout_option_that_index_is_just_wrong():
    correct, bailed, _, _, _ = _grade_check_block(_check_block(with_bailout=False), 3)
    assert bailed is False
    assert correct is False


# --- hostile / malformed input ---------------------------------------------

def test_out_of_range_selection_is_wrong_and_does_not_crash():
    for bad in (99, -1, 4):
        correct, bailed, misconception, _, _ = _grade_check_block(_check_block(), bad)
        assert correct is False, f"index {bad} must not grade as correct"
        assert misconception is None


def test_block_with_no_correct_index_never_grades_correct():
    """A malformed block must fail closed, not praise everything."""
    block = {"content": {"options": [{"text": "a"}, {"text": "b"}]}}
    for i in (0, 1, -1):
        correct, _, _, correct_index, _ = _grade_check_block(block, i)
        assert correct is False
        assert correct_index == -1


# --- block lookup is scoped and typed --------------------------------------

def test_finds_the_check_block_and_its_skill():
    block = _check_block()
    messages = [_FakeMessage([{"id": "other", "type": "text"}]), _FakeMessage([block])]
    found, skill_id = _find_check_block(messages, block["id"])
    assert found is not None
    assert skill_id == "square_roots"


def test_unknown_block_id_is_not_found():
    """A client cannot have a block graded that the server never emitted."""
    found, skill_id = _find_check_block([_FakeMessage([_check_block()])], "fabricated-id")
    assert found is None
    assert skill_id is None


def test_non_quiz_block_is_refused():
    """Pointing the grader at a text block must not produce a verdict."""
    text_block = SmartBlock.text("just prose").model_dump(mode="json")
    found, _ = _find_check_block([_FakeMessage([text_block])], text_block["id"])
    assert found is None


def test_messages_without_blocks_are_skipped_safely():
    found, _ = _find_check_block([_FakeMessage(None), _FakeMessage([])], "anything")
    assert found is None
