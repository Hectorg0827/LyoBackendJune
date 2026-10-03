import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    LearningTask,
    LearningTurn,
    TaskOption,
    TeachingContractError,
    validate_semantic_content,
)
from scripts.live_teacher_quality import scripted_fraction_response


def _choice_task(*, answer: str, scenario: str, question: str) -> LearningTask:
    labels = ["16", answer, "32"]
    return LearningTask(
        kind="choose",
        response_format="choice",
        target_index=0,
        scenario=scenario,
        question=question,
        response_hint="Choose the best answer.",
        criteria=["Select the mathematically correct result."],
        example_answer=answer,
        options=[
            TaskOption(
                id=chr(65 + index),
                label=label,
                correct=label == answer,
                feedback=f"Feedback for option {index}.",
            )
            for index, label in enumerate(labels)
        ],
    )


def test_short_numeric_answer_cannot_be_written_on_board_before_response():
    task = _choice_task(
        answer="24",
        scenario="Compare 3/8 and 5/12 using one common denominator.",
        question="What is the least common denominator?",
    )
    turn = LearningTurn(
        speech="Find the least common denominator before comparing the fractions.",
        board_title="Common denominator",
        board_content="The least common denominator is 24.",
        task=task,
    )

    with pytest.raises(TeachingContractError, match="short answer"):
        validate_semantic_content(turn)


def test_short_operand_already_present_in_question_is_not_false_positive():
    task = LearningTask(
        kind="choose",
        response_format="choice",
        target_index=0,
        scenario="Compare 3/8 and 5/12 and decide which fraction is larger.",
        question="Which fraction is larger?",
        response_hint="Choose one fraction.",
        criteria=["Select the larger fraction."],
        example_answer="5/12",
        options=[
            TaskOption(id="A", label="3/8", correct=False, feedback="Three eighths is smaller here."),
            TaskOption(id="B", label="5/12", correct=True, feedback="Five twelfths is larger here."),
            TaskOption(id="C", label="equal", correct=False, feedback="The fractions are not equal."),
        ],
    )
    turn = LearningTurn(
        speech="Compare the same two fractions without changing the question.",
        board_title="The two fractions",
        board_content="Fractions shown: 3/8 and 5/12.",
        task=task,
    )

    validate_semantic_content(turn)


def test_live_fraction_learner_solves_common_denominator_and_comparison():
    answer = scripted_fraction_response(
        "Compare 3/8 and 5/12. Find a common denominator and say which is larger."
    )

    assert "24" in answer
    assert "9/24" in answer
    assert "10/24" in answer
    assert "5/12 is larger" in answer


def test_live_fraction_learner_can_explain_denominator_piece_size():
    answer = scripted_fraction_response(
        "Why does a larger denominator make each equal piece smaller?"
    )

    assert "more equal pieces" in answer
    assert "each piece is smaller" in answer
