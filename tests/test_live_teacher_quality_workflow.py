from pathlib import Path


WORKFLOW = Path(".github/workflows/live-teacher-quality.yml").read_text(
    encoding="utf-8"
)


def test_live_validation_workflow_is_manual_only():
    assert "workflow_dispatch:" in WORKFLOW
    assert "push:" not in WORKFLOW
    assert "pull_request:" not in WORKFLOW
    assert "schedule:" not in WORKFLOW


def test_live_validation_credential_never_becomes_a_cli_argument():
    assert "LYO_TEACHER_QUALITY_TOKEN" in WORKFLOW
    assert "LYO_ACCESS_TOKEN:" in WORKFLOW
    assert "--access-token" not in WORKFLOW
    assert "--token" not in WORKFLOW
    assert 'echo "$LYO_ACCESS_TOKEN"' not in WORKFLOW
    assert 'printf "$LYO_ACCESS_TOKEN"' not in WORKFLOW


def test_live_validation_target_is_fixed_to_production_https():
    assert "LYO_BASE_URL: https://api.lyoai.app" in WORKFLOW
    assert "base_url:" not in WORKFLOW
    assert "--allow-http" not in WORKFLOW


def test_live_validation_proves_harness_before_touching_production_and_keeps_report():
    test_pos = WORKFLOW.index("tests/test_live_teacher_quality_harness.py")
    run_pos = WORKFLOW.index("scripts/live_teacher_quality.py")
    assert test_pos < run_pos
    assert "if: always()" in WORKFLOW
    assert "actions/upload-artifact@v4" in WORKFLOW
    assert "retention-days: 30" in WORKFLOW


def test_live_validation_exposes_only_named_subject_and_learner_presets():
    assert "scenario:" in WORKFLOW
    assert "profile:" in WORKFLOW
    for scenario in (
        "math_fractions",
        "biology_photosynthesis",
        "physics_newton2",
        "spanish_past_tense",
        "business_contribution_margin",
    ):
        assert f"- {scenario}" in WORKFLOW
    for profile in (
        "interrupter",
        "beginner",
        "advanced",
        "confident_wrong",
        "quiet_partial",
        "curious",
        "struggling",
        "fast_learner",
    ):
        assert f"- {profile}" in WORKFLOW
    assert 'VALIDATION_SCENARIO: ${{ inputs.scenario }}' in WORKFLOW
    assert 'VALIDATION_PROFILE: ${{ inputs.profile }}' in WORKFLOW
    assert '--scenario "$VALIDATION_SCENARIO"' in WORKFLOW
    assert '--profile "$VALIDATION_PROFILE"' in WORKFLOW
    assert "--topic" not in WORKFLOW
    assert "--chat-prompt" not in WORKFLOW
    assert "--question" not in WORKFLOW
    assert "--transfer-answer" not in WORKFLOW


def test_live_validation_is_serialized_for_the_shared_test_learner():
    assert "group: live-teacher-quality-production" in WORKFLOW
    assert "live-teacher-quality-${{ github.ref }}" not in WORKFLOW
