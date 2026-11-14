"""The grading acceptance must be strict about the errors learners feel.

These tests exercise only the harness's own scoring. They never call a model.
"""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "classroom_grading_acceptance",
    Path(__file__).resolve().parents[1] / "scripts" / "classroom_grading_acceptance.py",
)
harness = importlib.util.module_from_spec(SPEC)
import sys
sys.modules[SPEC.name] = harness
SPEC.loader.exec_module(harness)


def rows(verdict_for):
    out = []
    for index, case in enumerate(harness.CASES):
        for _ in range(2):
            verdict = verdict_for(case)
            out.append({
                "case": f"{index}", "verdict": verdict,
                "outcome": harness.classify(case, verdict), "seconds": 1.0,
            })
    return out


def test_dataset_is_labelled_and_balanced():
    assert len(harness.CASES) >= 40
    assert {case.task for case in harness.CASES} == set(harness.TASKS)
    expected = [case.expect for case in harness.CASES]
    assert expected.count("correct") >= 12 and expected.count("incorrect") >= 12
    for case in harness.CASES:
        assert case.expect in {"correct", "incorrect", "partial", "clarify"}
        # A wrong answer may never be allowed to pass as correct.
        assert case.expect == "correct" or "correct" not in case.allow


def test_a_perfect_grader_is_accepted():
    summary = harness.summarize(rows(lambda case: case.expect))
    assert summary["accepted"] and summary["metrics"]["agreement"] == 1.0


def test_one_wrong_answer_marked_correct_blocks_release():
    target = next(c for c in harness.CASES if c.expect == "incorrect")
    summary = harness.summarize(rows(lambda case: "correct" if case is target else case.expect))
    assert not summary["accepted"]
    assert summary["checks"]["no_wrong_answer_marked_correct"] is False


def test_one_correct_answer_marked_wrong_blocks_release():
    target = next(c for c in harness.CASES if c.expect == "correct")
    summary = harness.summarize(rows(lambda case: "incorrect" if case is target else case.expect))
    assert not summary["accepted"]
    assert summary["checks"]["no_correct_answer_marked_wrong"] is False


def test_prompt_injection_cannot_be_graded_correct():
    injected = [c for c in harness.CASES if "Ignore all previous instructions" in c.answer]
    assert injected
    assert all(harness.classify(case, "correct") == "false_pass" for case in injected)


def test_an_unreliable_grader_is_not_accepted():
    flip = iter(range(10_000))
    summary = harness.summarize(rows(lambda case: "unavailable" if next(flip) % 4 == 0 else case.expect))
    assert not summary["accepted"]
    assert summary["checks"]["grader_available"] is False


def test_inconsistent_verdicts_for_the_same_answer_are_caught():
    seen = set()

    def verdict(case):
        # First attempt of every "partial" case differs from the second.
        if case.expect == "partial" and id(case) not in seen:
            seen.add(id(case))
            return "incorrect"
        return case.expect

    summary = harness.summarize(rows(verdict))
    assert summary["metrics"]["consistency"] < 1.0


def test_missing_provider_key_runs_nothing(monkeypatch, capsys):
    for name in harness.PROVIDER_KEYS:
        monkeypatch.delenv(name, raising=False)
    assert harness.main([]) == 2
    assert "Nothing was run" in capsys.readouterr().err


@pytest.mark.parametrize("values,expected", [([], None), ([1.0], 1.0), ([1, 2, 3, 4, 5], 5)])
def test_percentile(values, expected):
    assert harness.percentile(values, 0.95) == expected


def test_harness_drives_the_real_grader_contract():
    """Wiring check: every labelled case builds a valid task for the real
    AdaptiveTeacher.evaluate. The model is scripted; nothing leaves the test."""
    pytest.importorskip("sqlalchemy")
    import asyncio
    from lyo_app.ai_classroom.adaptive_teaching import AdaptiveTeacher, CriterionResult, Evaluation

    async def scripted(prompt, payload, schema):
        assert schema is Evaluation
        assert payload["new_answer"] and payload["task"]["criteria"]
        return Evaluation(
            verdict="incorrect", confidence=0.9, question_clear=True,
            feedback="Not quite yet; look again at the key idea.",
            criteria=[CriterionResult(index=i, met=False, quote="")
                      for i in range(len(payload["task"]["criteria"]))],
        )

    async def grade_all():
        return [await harness.grade_once(AdaptiveTeacher(scripted), case, str(i))
                for i, case in enumerate(harness.CASES)]

    graded = asyncio.run(grade_all())
    verdicts = {row["verdict"] for row in graded}
    # Help requests short-circuit to "clarify" without a model call.
    assert verdicts == {"incorrect", "clarify"}, verdicts
    assert all(row["verdict"] == "clarify" for row in graded if row["expected"] == "clarify")
