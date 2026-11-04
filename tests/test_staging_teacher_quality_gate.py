"""Fail-closed staging teaching-quality release decisions; no network/model calls."""

from copy import deepcopy

from scripts.live_teacher_quality import LEARNER_PROFILES, SCENARIOS, quality_rubric_template
from scripts.staging_teacher_quality_gate import (
    STAGING_BASE_URL,
    validate_batch,
    validate_report,
)


def reviewed_report(scenario="math_fractions", profile="beginner", run_id="quality-1"):
    rubric = quality_rubric_template()
    for item in rubric:
        item["score"] = 5
        item["notes"] = "The reviewed transcript shows a targeted example and repair."
    return {
        "report_version": 2,
        "base_url": STAGING_BASE_URL,
        "run_id": run_id,
        "finished_at": "2026-11-04T12:00:00+00:00",
        "phase": "seed",
        "scenario": scenario,
        "learner_profile": profile,
        "checks": [
            {"name": "chat_stream_completed", "passed": True},
            {"name": "chat_smart_block_graded", "passed": True},
            {"name": "classroom_scene_received", "passed": True},
            {"name": "same_session_reconnected", "passed": None},
        ],
        "quality_rubric": rubric,
        "independent_review": {
            "reviewer_id": "external-reviewer-1",
            "reviewer_type": "human",
            "attests_independent": True,
            "reviewed_at": "2026-11-04T14:00:00Z",
            "transcript_evidence": "Compared classroom transcript to eight pedagogical criteria.",
        },
    }


def test_a_complete_reviewed_staging_report_passes():
    assert validate_report(reviewed_report()) == []


def test_unreviewed_rubric_does_not_pass_even_when_live_checks_pass():
    report = reviewed_report()
    report["quality_rubric"] = quality_rubric_template()
    assert any("Unreviewed/invalid" in p for p in validate_report(report))


def test_missing_independent_reviewer_never_passes():
    report = reviewed_report()
    del report["independent_review"]
    assert any("independent reviewer" in p for p in validate_report(report))


def test_quality_below_threshold_never_passes():
    report = reviewed_report()
    report["quality_rubric"][0]["score"] = 3
    assert any("Below quality threshold" in p for p in validate_report(report))
    report["quality_rubric"][0]["score"] = 4
    assert validate_report(report, min_score=4) == []
    assert any("Below quality threshold" in p for p in validate_report(report, min_score=5))


def test_live_failure_and_pending_essential_checks_block_release():
    report = reviewed_report()
    report["checks"][1]["passed"] = False
    problems = validate_report(report)
    assert any("Failed live check" in p for p in problems)
    assert any("Required live check not passed" in p for p in problems)

    report["checks"][1]["passed"] = None
    assert any("Required live check not passed" in p for p in validate_report(report))


def test_production_report_and_unknown_scenarios_are_rejected():
    report = reviewed_report()
    report["base_url"] = "https://api.lyoai.app"
    report["scenario"] = "unapproved_topic"
    problems = validate_report(report)
    assert any("pinned staging" in p for p in problems)
    assert any("Unknown subject" in p for p in problems)


def test_reviewer_must_supply_specific_evidence_and_attestation():
    report = reviewed_report()
    report["independent_review"]["attests_independent"] = False
    report["quality_rubric"][0]["notes"] = "good"
    problems = validate_report(report)
    assert any("attested independence" in p for p in problems)
    assert any("transcript evidence notes" in p for p in problems)


def pilot_reports():
    subjects = list(SCENARIOS)
    profiles = list(LEARNER_PROFILES)
    n = max(len(subjects), len(profiles))
    return [
        reviewed_report(subjects[i % len(subjects)], profiles[i % len(profiles)], str(i))
        for i in range(n)
    ]


def test_pilot_gate_requires_all_subjects_and_profiles():
    reports = pilot_reports()
    assert validate_batch(reports) == []
    assert any("Untested learner profiles" in p for p in validate_batch(reports[:2]))


def test_repeated_run_id_cannot_inflate_evidence():
    reports = pilot_reports()
    reports[1]["run_id"] = reports[0]["run_id"]
    assert any("repeated run_id" in p for p in validate_batch(reports))


def test_full_matrix_requires_every_subject_profile_pair():
    assert any("Full matrix incomplete" in p for p in validate_batch(
        pilot_reports(), full_matrix=True
    ))
    reports = [
        reviewed_report(subject, profile, f"{subject}-{profile}")
        for subject in SCENARIOS for profile in LEARNER_PROFILES
    ]
    assert validate_batch(reports, full_matrix=True) == []


def test_invalid_rubric_or_review_provenance_is_not_passed():
    report = reviewed_report()
    report["quality_rubric"] = deepcopy(report["quality_rubric"][:-1])
    report["independent_review"]["reviewer_id"] = "teacher"
    problems = validate_report(report)
    assert any("incomplete independent rubric" in p for p in problems)
    assert any("reviewer must be identified" in p for p in problems)
