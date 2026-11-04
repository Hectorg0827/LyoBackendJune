#!/usr/bin/env python3
"""Fail-closed, independent quality gate for LYO Web STAGING classroom reports.

The black-box runner emits unscored rubrics. An external reviewer must inspect
transcripts, fill every rubric score and add review provenance. This gate never
calls a model, accesses production or changes any learner account.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from scripts.live_teacher_quality import LEARNER_PROFILES, QUALITY_RUBRIC, SCENARIOS

STAGING_BASE_URL = "https://lyojourneystagingbackend-staging.up.railway.app"
REQUIRED_CHECKS = (
    "chat_stream_completed",
    "chat_smart_block_graded",
    "classroom_scene_received",
)
CRITERIA = {key for key, _ in QUALITY_RUBRIC}


def validate_report(report: Any, *, min_score: int = 4) -> list[str]:
    """Return actionable failures; no score or missing review is ever a pass."""
    failures: list[str] = []
    if not isinstance(report, dict):
        return ["Report is not a JSON object"]
    if report.get("report_version") != 2:
        failures.append("Unsupported or missing report version")
    if report.get("base_url") != STAGING_BASE_URL:
        failures.append("Report is not from the pinned staging backend")
    if report.get("phase") != "seed":
        failures.append("Release gate requires a real seed teaching session")
    if not isinstance(report.get("scenario"), str) or report["scenario"] not in SCENARIOS:
        failures.append("Unknown subject scenario")
    if not isinstance(report.get("learner_profile"), str) or report["learner_profile"] not in LEARNER_PROFILES:
        failures.append("Unknown learner profile")
    if not report.get("run_id") or not report.get("finished_at"):
        failures.append("Incomplete session identity/timestamps")

    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        failures.append("No automated live checks were recorded")
    else:
        named: dict[str, bool | None] = {}
        for check in checks:
            if not isinstance(check, dict) or not isinstance(check.get("name"), str):
                failures.append("Malformed live check")
                continue
            outcome = check.get("passed")
            if outcome is not None and type(outcome) is not bool:
                failures.append(f"Invalid check verdict: {check['name']}")
            if outcome is False:
                failures.append(f"Failed live check: {check['name']}")
            if check["name"] in named:
                failures.append(f"Repeated live check: {check['name']}")
            named[check["name"]] = outcome
        for name in REQUIRED_CHECKS:
            if named.get(name) is not True:
                failures.append(f"Required live check not passed: {name}")

    rubric = report.get("quality_rubric")
    if not isinstance(rubric, list) or len(rubric) != len(CRITERIA):
        failures.append("Missing or incomplete independent rubric")
    else:
        scored: set[str] = set()
        for item in rubric:
            if not isinstance(item, dict):
                failures.append("Malformed rubric item")
                continue
            criterion = item.get("criterion")
            score = item.get("score")
            notes = item.get("notes")
            if not isinstance(criterion, str) or criterion not in CRITERIA or criterion in scored:
                failures.append(f"Unexpected/repeated criterion: {criterion}")
                continue
            scored.add(criterion)
            if type(score) is not int or not 1 <= score <= 5:
                failures.append(f"Unreviewed/invalid score: {criterion}")
            elif score < min_score:
                failures.append(f"Below quality threshold: {criterion} ({score}/5)")
            if not isinstance(notes, str) or len(notes.strip()) < 15:
                failures.append(f"Missing transcript evidence notes: {criterion}")
        if scored != CRITERIA:
            failures.append("Rubric criteria are incomplete")

    review = report.get("independent_review")
    if not isinstance(review, dict):
        failures.append("Missing independent reviewer attestation")
    else:
        reviewer = review.get("reviewer_id")
        if (
            not isinstance(reviewer, str)
            or len(reviewer.strip()) < 3
            or reviewer.strip().lower() in {"lyo", "ai_teacher", "teacher", "self"}
            or reviewer == report.get("run_id")
        ):
            failures.append("Independent reviewer must be identified")
        if review.get("reviewer_type") not in {"human", "independent-model"}:
            failures.append("Reviewer type must be human or independent-model")
        if review.get("attests_independent") is not True:
            failures.append("Reviewer has not attested independence")
        when = review.get("reviewed_at")
        try:
            if not isinstance(when, str):
                raise ValueError("missing")
            datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            failures.append("Missing/invalid reviewed_at timestamp")
        evidence = review.get("transcript_evidence")
        if not isinstance(evidence, str) or len(evidence.strip()) < 30:
            failures.append("Independent review lacks transcript evidence")
    return failures


def validate_batch(
    reports: Iterable[Any],
    *,
    min_score: int = 4,
    full_matrix: bool = False,
) -> list[str]:
    """Pilot requires all subjects/profiles; full requires every combination."""
    failures: list[str] = []
    found_subjects: set[str] = set()
    found_profiles: set[str] = set()
    found_pairs: set[tuple[str, str]] = set()
    run_ids: set[str] = set()
    count = 0
    for index, report in enumerate(reports, start=1):
        count += 1
        for issue in validate_report(report, min_score=min_score):
            failures.append(f"Report {index}: {issue}")
        if not isinstance(report, dict):
            continue
        run_id = report.get("run_id")
        if isinstance(run_id, str):
            if run_id in run_ids:
                failures.append(f"Report {index}: repeated run_id")
            run_ids.add(run_id)
        scenario = report.get("scenario")
        profile = report.get("learner_profile")
        if isinstance(scenario, str) and scenario in SCENARIOS:
            found_subjects.add(scenario)
        if isinstance(profile, str) and profile in LEARNER_PROFILES:
            found_profiles.add(profile)
        if (isinstance(scenario, str) and scenario in SCENARIOS
                and isinstance(profile, str) and profile in LEARNER_PROFILES):
            found_pairs.add((scenario, profile))

    if not count:
        failures.append("No live staging reports supplied")
    missing_subjects = set(SCENARIOS) - found_subjects
    missing_profiles = set(LEARNER_PROFILES) - found_profiles
    if missing_subjects:
        failures.append("Untested subjects: " + ", ".join(sorted(missing_subjects)))
    if missing_profiles:
        failures.append("Untested learner profiles: " + ", ".join(sorted(missing_profiles)))
    if full_matrix:
        missing_pairs = set((s, p) for s in SCENARIOS for p in LEARNER_PROFILES) - found_pairs
        if missing_pairs:
            failures.append(f"Full matrix incomplete: {len(missing_pairs)} subject/profile pairs")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="Reviewed live report JSON files")
    parser.add_argument("--min-score", type=int, choices=(4, 5), default=4)
    parser.add_argument("--full-matrix", action="store_true")
    args = parser.parse_args()

    reports = []
    for path in args.reports:
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            print(f"FAIL {path.name}: {type(exc).__name__}", file=sys.stderr)
            return 2
    problems = validate_batch(reports, min_score=args.min_score, full_matrix=args.full_matrix)
    for problem in problems:
        print("FAIL " + problem, file=sys.stderr)
    if problems:
        print(f"STAGING TEACHER QUALITY: BLOCKED ({len(problems)} issues)", file=sys.stderr)
        return 1
    print(f"STAGING TEACHER QUALITY: PASS ({len(reports)} independently reviewed runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
