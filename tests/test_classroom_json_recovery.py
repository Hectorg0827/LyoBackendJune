"""Malformed provider JSON cannot unnecessarily block the live classroom."""

import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    PracticeTurn, parse_model_json_object,
)


def test_extract_first_object_without_appended_commentary():
    assert parse_model_json_object('```json\n{"speech":"Okay"}\n``` \nAdditional remarks: {ignore}') == {
        "speech": "Okay"
    }


def test_repair_trailing_commas_raw_newlines_and_latex_escapes():
    raw = '{"speech":"Here is the first line.\nAnd the next", "board_content":"\\frac{1}{2} = \\frac{2}{4}",}'
    recovered = parse_model_json_object(raw)
    assert recovered["speech"] == "Here is the first line.\nAnd the next"
    assert recovered["board_content"] == r"\frac{1}{2} = \frac{2}{4}"


def test_unfinished_object_is_not_reconstructed_or_graded():
    with pytest.raises(ValueError):
        parse_model_json_object('{"speech":"unfinished')


def test_recovered_object_must_still_satisfy_complete_teaching_schema():
    raw = '{"speech":"Not enough to count as a lesson",}'
    with pytest.raises(Exception):
        PracticeTurn.model_validate(parse_model_json_object(raw))
