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


# --- verdict persistence ----------------------------------------------------

def test_locate_check_block_returns_the_owning_message():
    """The grader needs the message so it can write the verdict back."""
    from lyo_app.api.v1.stream_lyo2 import _locate_check_block

    block = _check_block()
    msg = _FakeMessage([block])
    found, skill_id, owner = _locate_check_block([_FakeMessage([]), msg], block["id"])
    assert found is not None
    assert skill_id == "square_roots"
    assert owner is msg


def test_persist_check_result_reassigns_blocks_so_json_column_saves():
    """A JSON column tracks changes by identity — an in-place edit is lost."""
    import asyncio

    from lyo_app.api.v1.stream_lyo2 import CheckAnswerResponse, _persist_check_result

    block = _check_block()
    original_list = [block]
    message = _FakeMessage(original_list)

    class _FakeDB:
        def __init__(self): self.commits = 0
        async def commit(self): self.commits += 1
        async def rollback(self): pass

    db = _FakeDB()
    verdict = CheckAnswerResponse(
        correct=False, correct_index=0, selected_index=1,
        explanation="7 x 7 = 49.", misconception="confusing root with square",
        bailed_out=False, skill_id="square_roots",
    )
    asyncio.run(_persist_check_result(db, message, block["id"], verdict))

    assert db.commits == 1
    assert message.blocks is not original_list, "must reassign, not mutate in place"
    stored = message.blocks[0]["metadata"]["result"]
    assert stored["correct"] is False
    assert stored["selected_index"] == 1
    assert stored["misconception"] == "confusing root with square"


def test_persist_check_result_is_a_noop_for_an_unknown_block():
    import asyncio

    from lyo_app.api.v1.stream_lyo2 import CheckAnswerResponse, _persist_check_result

    message = _FakeMessage([_check_block()])
    before = message.blocks

    class _FakeDB:
        def __init__(self): self.commits = 0
        async def commit(self): self.commits += 1
        async def rollback(self): pass

    db = _FakeDB()
    asyncio.run(_persist_check_result(
        db, message, "not-a-real-id",
        CheckAnswerResponse(correct=True, correct_index=0, selected_index=0),
    ))
    assert db.commits == 0
    assert message.blocks is before


def test_persist_check_result_tolerates_a_missing_message():
    import asyncio

    from lyo_app.api.v1.stream_lyo2 import CheckAnswerResponse, _persist_check_result

    asyncio.run(_persist_check_result(
        None, None, "x",
        CheckAnswerResponse(correct=True, correct_index=0, selected_index=0),
    ))  # must not raise


# --- session-close summary ---------------------------------------------------

def _answered_block(skill_id, correct, question="What is the square root of 49?",
                     misconception=None, bailed_out=False):
    block = _check_block(with_bailout=False)
    block["metadata"] = {
        "skill_id": skill_id,
        "result": {
            "correct": correct,
            "correct_index": 0,
            "selected_index": 0 if correct else 1,
            "misconception": misconception,
            "bailed_out": bailed_out,
        },
    }
    block["content"]["question"] = question
    return block


def test_collect_session_attempts_counts_and_extracts_skill():
    from lyo_app.api.v1.stream_lyo2 import _collect_session_attempts

    block = _answered_block("square_roots", correct=True)
    attempts, total, correct = _collect_session_attempts([_FakeMessage([block])])

    assert total == 1
    assert correct == 1
    assert attempts["square_roots"]["correct"] is True
    assert attempts["square_roots"]["question"] == "What is the square root of 49?"


def test_collect_session_attempts_keeps_latest_attempt_on_retry():
    from lyo_app.api.v1.stream_lyo2 import _collect_session_attempts

    first = _answered_block("square_roots", correct=False, misconception="confused root with square")
    second = _answered_block("square_roots", correct=True)
    attempts, total, correct = _collect_session_attempts(
        [_FakeMessage([first]), _FakeMessage([second])]
    )

    assert total == 2
    assert correct == 1
    # Only the latest attempt survives per skill.
    assert attempts["square_roots"]["correct"] is True
    assert attempts["square_roots"]["misconception"] is None


def test_collect_session_attempts_excludes_bailouts_and_unanswered():
    from lyo_app.api.v1.stream_lyo2 import _collect_session_attempts

    bailed = _answered_block("square_roots", correct=False, bailed_out=True)
    unanswered = _check_block()
    unanswered["metadata"] = {"skill_id": "square_roots"}  # no "result" yet
    attempts, total, correct = _collect_session_attempts(
        [_FakeMessage([bailed, unanswered])]
    )

    assert total == 0
    assert correct == 0
    assert attempts == {}


def test_classify_session_attempts_nailed_requires_mastery_agreement():
    from lyo_app.api.v1.stream_lyo2 import _classify_session_attempts

    attempts = {
        "square_roots": {"question": "q", "correct": True, "misconception": None},
        "fractions": {"question": "q2", "correct": True, "misconception": None},
    }
    # square_roots: correct just now AND mastery agrees -> nailed.
    # fractions: correct just now but mastery still tracks it as weak (a
    # lucky guess) -> stays shaky.
    masteries = {"square_roots": 0.8, "fractions": 0.2}

    nailed, shaky = _classify_session_attempts(attempts, masteries)

    assert [s.skill_id for s in nailed] == ["square_roots"]
    assert [s.skill_id for s in shaky] == ["fractions"]


def test_classify_session_attempts_wrong_answer_is_always_shaky():
    from lyo_app.api.v1.stream_lyo2 import _classify_session_attempts

    attempts = {
        "square_roots": {"question": "q", "correct": False, "misconception": "confused root with square"},
    }
    nailed, shaky = _classify_session_attempts(attempts, {"square_roots": 0.9})

    assert nailed == []
    assert shaky[0].skill_id == "square_roots"
    assert shaky[0].misconception == "confused root with square"


def test_classify_session_attempts_no_mastery_row_falls_back_to_correctness():
    """A skill mastered for the first time this session has no prior row yet."""
    from lyo_app.api.v1.stream_lyo2 import _classify_session_attempts

    attempts = {"new_skill": {"question": "q", "correct": True, "misconception": None}}
    nailed, shaky = _classify_session_attempts(attempts, {})

    assert [s.skill_id for s in nailed] == ["new_skill"]
    assert shaky == []
