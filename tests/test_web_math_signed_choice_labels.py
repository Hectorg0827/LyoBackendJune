"""Signed algebra choices must remain distinguishable without relaxing duplicates."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from lyo_app.ai_classroom.adaptive_teaching import (
    LearningTask, comparable_option_label, comparable_text,
)
from tests.adaptive_fixtures import probe


def diagnostic_with_labels(labels):
    candidate = deepcopy(probe().model_dump(mode="json"))
    assert len(labels) == len(candidate["options"])
    for option, label in zip(candidate["options"], labels):
        option["label"] = label
    return candidate


@pytest.mark.parametrize("left,right", [
    ("x = -5", "x = 5"),
    ("x - 3", "x + 3"),
    ("-7", "7"),
    ("x <= 3", "x >= 3"),
    ("3.5", "3 5"),
    ("1/2", "12"),
])
def test_mathematically_distinct_options_are_not_rejected_as_duplicates(left, right):
    assert comparable_option_label(left) != comparable_option_label(right)


@pytest.mark.parametrize("left,right", [
    ("x = -5", "X=−5!"),
    ("-7", "−7"),
    ("One half!", "one half"),
    ("50%", "50"),
])
def test_true_duplicates_still_collide(left, right):
    assert comparable_option_label(left) == comparable_option_label(right)


def test_signed_algebra_diagnostic_retains_four_valid_choices():
    candidate = diagnostic_with_labels([
        "x = 5", "x = -5", "x = 3", "I'm not sure yet",
    ])
    validated = LearningTask.model_validate(candidate)
    assert len(validated.options) == 4
    assert validated.options[0].correct is True


def test_true_duplicate_options_remain_strictly_rejected():
    candidate = diagnostic_with_labels([
        "x = 5", "x = -5", "X=−5!", "I'm not sure yet",
    ])
    with pytest.raises(ValidationError, match="distinct visible answers"):
        LearningTask.model_validate(candidate)


def test_math_option_normalization_does_not_modify_other_rubric_comparisons():
    assert comparable_text("x = -5") == comparable_text("x = 5")
    assert comparable_option_label("x = -5") != comparable_option_label("x = 5")
