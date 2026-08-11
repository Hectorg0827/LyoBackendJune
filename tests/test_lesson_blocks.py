"""Lesson -> SmartBlock rendering, and the emit/grade round trip.

The round-trip test is the important one: it proves the blocks the stream
emits are the same shape the grading endpoint can read back, so the two sides
cannot drift into "the check renders but nothing can grade it".
"""

from lyo_app.ai.lesson_composer import ChatLesson
from lyo_app.api.v1.stream_lyo2 import (
    _find_check_block,
    _grade_check_block,
    _lesson_to_smart_blocks,
)


class _FakeMessage:
    def __init__(self, blocks):
        self.blocks = blocks


def _lesson():
    return ChatLesson(
        topic="square roots",
        skill_id="square_roots",
        is_probe=True,
        sections=[
            {"kind": "hook", "text": "What number times itself gives you this?"},
            {"kind": "core", "text": "A square root undoes squaring."},
            {"kind": "representation", "text": "A square of area 16 has side 4.",
             "latex": "\\sqrt{16}=4"},
            {"kind": "trap", "text": "sqrt(a+b) is not sqrt(a)+sqrt(b)."},
            {"kind": "reference", "text": "Perfect squares",
             "table_markdown": "| n | root |\n|---|---|\n| 49 | 7 |"},
        ],
        check={
            "question": "What is the square root of 49?",
            "options": [
                {"text": "7"},
                {"text": "9", "reveals": "confusing the root with a nearby square"},
                {"text": "Not sure — just explain it"},
            ],
            "correct_index": 0,
            "explanation": "7 x 7 = 49.",
            "bailout_index": 2,
        },
        next_directions=["estimate irrational roots", "why negatives have no real root"],
    )


def _by_subtype(blocks, subtype):
    return [b for b in blocks if b.get("subtype") == subtype]


def test_each_lesson_beat_becomes_its_own_block():
    blocks = _lesson_to_smart_blocks(_lesson())
    # Distinct blocks are what make a lesson scannable rather than a wall.
    assert _by_subtype(blocks, "hook")
    assert _by_subtype(blocks, "core")
    assert _by_subtype(blocks, "representation")


def test_trap_section_becomes_a_styled_callout():
    blocks = _lesson_to_smart_blocks(_lesson())
    callouts = _by_subtype(blocks, "callout")
    assert len(callouts) == 1
    assert callouts[0]["type"] == "text"
    assert callouts[0]["content"]["style"] == "trap"
    assert "sqrt(a+b)" in callouts[0]["content"]["text"]


def test_reference_section_becomes_a_table_block():
    blocks = _lesson_to_smart_blocks(_lesson())
    tables = _by_subtype(blocks, "table")
    assert len(tables) == 1
    assert tables[0]["content"]["format"] == "table"
    assert "| 49 | 7 |" in tables[0]["content"]["source"]


def test_latex_becomes_a_math_block_not_inline_text():
    blocks = _lesson_to_smart_blocks(_lesson())
    math = [b for b in blocks if b["content"].get("format") == "math"]
    assert len(math) == 1
    assert math[0]["content"]["source"] == "\\sqrt{16}=4"
    # The prose beside it must not carry raw delimiters.
    rep = _by_subtype(blocks, "representation")[0]
    assert "$" not in rep["content"]["text"]


def test_check_block_carries_skill_and_probe_metadata():
    blocks = _lesson_to_smart_blocks(_lesson())
    check = [b for b in blocks if b["type"] == "quiz"][0]
    assert check["metadata"]["skill_id"] == "square_roots"
    assert check["metadata"]["is_probe"] is True


def test_check_block_preserves_distractor_reveals_and_bailout():
    blocks = _lesson_to_smart_blocks(_lesson())
    content = [b for b in blocks if b["type"] == "quiz"][0]["content"]
    assert content["correct_index"] == 0
    assert content["bailout_index"] == 2
    assert content["options"][1]["reveals"] == "confusing the root with a nearby square"
    assert content["options"][0]["reveals"] is None


def test_teach_lesson_without_a_bailout_emits_none():
    lesson = _lesson()
    lesson.is_probe = False
    lesson.check.bailout_index = None
    blocks = _lesson_to_smart_blocks(lesson)
    content = [b for b in blocks if b["type"] == "quiz"][0]["content"]
    assert content["bailout_index"] is None


def test_lesson_with_no_check_emits_no_quiz_block():
    lesson = _lesson()
    lesson.check = None
    blocks = _lesson_to_smart_blocks(lesson)
    assert not [b for b in blocks if b["type"] == "quiz"]


# --- the round trip ---------------------------------------------------------

def test_emitted_check_can_be_found_and_graded_by_the_endpoint():
    """What the stream emits must be exactly what the grader can read back."""
    blocks = _lesson_to_smart_blocks(_lesson())
    quiz = [b for b in blocks if b["type"] == "quiz"][0]

    # Exactly as the endpoint sees it: persisted on a message, looked up by id.
    found, skill_id = _find_check_block([_FakeMessage(blocks)], quiz["id"])
    assert found is not None
    assert skill_id == "square_roots"

    # The production bug, end to end: answering 9 must not be "correct".
    correct, bailed, misconception, correct_index, explanation = _grade_check_block(found, 1)
    assert correct is False
    assert bailed is False
    assert misconception == "confusing the root with a nearby square"
    assert correct_index == 0
    assert explanation == "7 x 7 = 49."

    # And the right answer still grades right.
    assert _grade_check_block(found, 0)[0] is True
    # And the opt-out is recognised as an opt-out.
    assert _grade_check_block(found, 2)[1] is True
