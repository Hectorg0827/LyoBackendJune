"""The independent live teacher harness must never target production from staging."""

from pathlib import Path

from scripts.live_teacher_quality import LEARNER_PROFILES, QUALITY_RUBRIC, SCENARIOS


WORKFLOW = Path(".github/workflows/staging-teacher-quality.yml").read_text(
    encoding="utf-8"
)


def test_staging_validation_is_manual_and_targets_staging_only():
    assert "workflow_dispatch:" in WORKFLOW
    assert "push:" not in WORKFLOW
    assert "pull_request:" not in WORKFLOW
    assert "schedule:" not in WORKFLOW
    assert (
        "LYO_BASE_URL: https://lyojourneystagingbackend-staging.up.railway.app"
        in WORKFLOW
    )
    assert "https://api.lyoai.app" not in WORKFLOW
    assert "--allow-http" not in WORKFLOW
    assert "base_url:" not in WORKFLOW


def test_dedicated_staging_learner_token_stays_out_of_cli_and_reports():
    assert "LYO_STAGING_TEACHER_QUALITY_TOKEN" in WORKFLOW
    assert "LYO_ACCESS_TOKEN:" in WORKFLOW
    assert "--access-token" not in WORKFLOW
    assert "--token" not in WORKFLOW
    assert 'echo "$LYO_ACCESS_TOKEN"' not in WORKFLOW
    assert 'printf "$LYO_ACCESS_TOKEN"' not in WORKFLOW
    assert "actions/upload-artifact@v4" in WORKFLOW
    assert "retention-days: 30" in WORKFLOW


def test_live_quality_requires_independent_harness_with_subject_coverage():
    assert len(SCENARIOS) >= 5
    assert len(LEARNER_PROFILES) >= 7
    assert len(QUALITY_RUBRIC) >= 7
    assert len({key for key, _ in QUALITY_RUBRIC}) == len(QUALITY_RUBRIC)
    assert "tests/test_live_teacher_quality_harness.py" in WORKFLOW
    assert "scripts/live_teacher_quality.py" in WORKFLOW
    assert (
        WORKFLOW.index("tests/test_live_teacher_quality_harness.py")
        < WORKFLOW.index("scripts/live_teacher_quality.py")
    )
    assert "group: live-teacher-quality-staging" in WORKFLOW


def test_live_report_keeps_unscored_human_quality_review_visible():
    from scripts.live_teacher_quality import quality_rubric_template

    rubric = quality_rubric_template()
    assert len(rubric) == len(QUALITY_RUBRIC)
    assert all(item["score"] is None for item in rubric)
    assert all(item["scale"] == "1-5" for item in rubric)
