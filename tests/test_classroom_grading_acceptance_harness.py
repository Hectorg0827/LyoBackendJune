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
                "case": f"{index:02d}:{case.task}:{case.label}", "verdict": verdict,
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


def test_single_perfect_answer_cannot_claim_full_release():
    case = harness.CASES[0]
    result = {
        "case": f"00:{case.task}:{case.label}",
        "verdict": case.expect, "outcome": harness.classify(case, case.expect),
        "seconds": 1.0,
    }
    summary = harness.summarize([result, result])
    assert summary["checks"]["full_matrix_twice"] is False
    assert not summary["accepted"]


def test_whole_suite_run_only_once_cannot_claim_consistency():
    result = rows(lambda case: case.expect)[::2]
    assert len(result) == len(harness.CASES)
    summary = harness.summarize(result)
    assert summary["metrics"]["agreement"] == 1.0
    assert summary["metrics"]["consistency"] == 1.0
    assert summary["checks"]["full_matrix_twice"] is False
    assert not summary["accepted"]


def test_repeated_easy_answers_cannot_conceal_missing_prompt_injection():
    complete = rows(lambda case: case.expect)
    risky = next(i for i, c in enumerate(harness.CASES)
                 if "Ignore all previous instructions" in c.answer)
    missing_id = f"{risky:02d}:{harness.CASES[risky].task}:{harness.CASES[risky].label}"
    masked = [row for row in complete if row["case"] != missing_id]
    masked.extend(complete[:2])
    summary = harness.summarize(masked)
    assert len(masked) == len(complete)
    assert summary["metrics"]["false_pass"] == 0
    assert summary["checks"]["full_matrix_twice"] is False
    assert not summary["accepted"]


def test_complete_two_pass_matrix_reports_actual_case_coverage():
    summary = harness.summarize(rows(lambda case: case.expect))
    assert summary["checks"]["full_matrix_twice"] is True
    assert summary["metrics"]["expected_cases"] == len(harness.CASES)
    assert summary["metrics"]["cases_repeated_twice"] == len(harness.CASES)
    assert summary["metrics"]["attempts"] == 2 * len(harness.CASES)
    assert summary["accepted"]


def test_missing_spanish_case_refuses_release_even_with_duplicate_english_rows():
    all_rows = rows(lambda case: case.expect)
    spanish_index = next(i for i, case in enumerate(harness.CASES)
                         if case.task == "fracciones_es")
    missing_id = f"{spanish_index:02d}:{harness.CASES[spanish_index].task}:{harness.CASES[spanish_index].label}"
    filtered = [row for row in all_rows if row["case"] != missing_id]
    filtered.extend(all_rows[:2])
    assert not harness.summarize(filtered)["accepted"]


@pytest.mark.parametrize("environment,enabled,limit", [
    ("production", "1", "70"),
    ("staging", "0", "70"),
    ("staging", "1", "70.000001"),
    ("development", "1", "70"),
])
def test_live_runner_rejects_outside_owner_approved_staging_ledger(
        monkeypatch, capsys, environment, enabled, limit):
    # This fake key must NEVER initiate provider requests. The gate should
    # refuse before it reaches asyncio.run or creates an AdaptiveTeacher.
    for name in harness.PROVIDER_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "unusable-ci-fake-key")
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("CLASSROOM_AI_TRIAL_ENABLED", enabled)
    monkeypatch.setenv("CLASSROOM_AI_TRIAL_LIMIT_USD", limit)
    def no_provider_calls(*_args, **_kwargs):
        raise AssertionError("Unsafe provider invocation")
    monkeypatch.setattr(harness, "run", no_provider_calls)
    assert harness.main(["--repeats", "2"]) == 2
    assert "Nothing was run" in capsys.readouterr().err


def test_staging_trial_preflight_accepts_owner_approved_cumulative_70(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("CLASSROOM_AI_TRIAL_ENABLED", "1")
    monkeypatch.setenv("CLASSROOM_AI_TRIAL_LIMIT_USD", "70")
    assert harness.require_bounded_staging_trial() is None


def test_one_subject_cannot_claim_41_case_release_even_with_two_passes():
    first = harness.CASES[0]
    subset = [
        {
            "case": f"00:{first.task}:{first.label}",
            "verdict": first.expect,
            "outcome": harness.classify(first, first.expect),
            "seconds": 1.0,
        }
        for _ in range(2)
    ]
    assert not harness.summarize(subset)["accepted"]
