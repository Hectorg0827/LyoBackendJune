import ast
from pathlib import Path

import pytest

from scripts.live_teacher_quality import (
    LEARNER_PROFILES,
    SCENARIOS,
    Report,
    analytics_delta,
    choose_option,
    parse_sse_lines,
    require_https,
    safe_snapshot,
    scene_from_message,
    select_due_review,
    websocket_url,
)


def test_production_target_requires_https():
    assert require_https("https://api.lyoai.app/") == "https://api.lyoai.app"
    with pytest.raises(ValueError):
        require_https("http://api.lyoai.app")


def test_local_http_can_be_explicitly_enabled():
    assert require_https("http://127.0.0.1:8000/", allow_http=True) == "http://127.0.0.1:8000"


def test_websocket_url_preserves_target_and_query():
    value = websocket_url(
        "https://api.lyoai.app",
        "/api/v1/classroom/ws/connect",
        {"session_id": "abc 123", "topic": "fractions", "empty": None},
    )
    assert value.startswith("wss://api.lyoai.app/api/v1/classroom/ws/connect?")
    assert "session_id=abc+123" in value
    assert "topic=fractions" in value
    assert "empty=" not in value


def test_sse_parser_ignores_done_and_keeps_bad_json_visible():
    events = parse_sse_lines(
        [
            'data: {"type":"conversation","conversation_id":"c1"}',
            "",
            "data: not-json",
            "data: [DONE]",
        ]
    )
    assert events[0]["conversation_id"] == "c1"
    assert events[1]["type"] == "invalid_json"


def test_scene_is_found_in_wire_payload():
    scene = {"scene_id": "s1", "components": [{"type": "TeacherMessage", "text": "Hello learner"}]}
    message = {"event_type": "scene_start", "data": {"scene": scene}}
    assert scene_from_message(message) == scene


def test_forced_answer_only_claims_certainty_when_client_contract_declares_it():
    quiz = {
        "options": [
            {"id": "a", "is_correct": True},
            {"id": "b", "is_correct": False},
        ]
    }
    assert choose_option(quiz, want_correct=False) == ("b", "declared")
    assert choose_option(quiz, want_correct=True) == ("a", "declared")

    withheld = {
        "options": [
            {"id": "a", "is_correct": None},
            {"id": "b", "is_correct": None},
        ]
    }
    assert choose_option(withheld, want_correct=False) == ("a", "unknown")


def test_requested_review_must_exist_in_server_due_queue():
    due = [
        {"skill_id": "fractions", "display_name": "Fractions"},
        {"skill_id": "ratios", "display_name": "Ratios"},
    ]
    selected, reason = select_due_review(due, "ratios")
    assert selected == due[1]
    assert reason == "requested_due"

    selected, reason = select_due_review(due, "not-due-yet")
    assert selected is None
    assert reason == "requested_not_due"


def test_review_without_override_uses_first_genuinely_due_item():
    due = [{"skill_id": "fractions"}, {"skill_id": "ratios"}]
    selected, reason = select_due_review(due)
    assert selected == due[0]
    assert reason == "first_due"

    selected, reason = select_due_review([])
    assert selected is None
    assert reason == "none_due"


def test_reports_redact_bearer_material_recursively():
    snapshot = safe_snapshot(
        {
            "token": "secret-token",
            "nested": {"access_token": "secret-access", "value": "keep"},
        }
    )
    assert snapshot["token"] == "[REDACTED]"
    assert snapshot["nested"]["access_token"] == "[REDACTED]"
    assert snapshot["nested"]["value"] == "keep"


def test_analytics_delta_tracks_only_durable_counters():
    before = {
        "evidence_attempts": 3,
        "sessions": {"identified_sessions": 1, "successful_sessions": 0},
        "model_usage": {"calls": 4, "tokens": 100, "linked_calls": 3, "linked_tokens": 80},
        "transfer": {"attempts": 0, "successes": 0},
        "remediation": {"eligible_followups": 1, "repaired": 0},
    }
    after = {
        "evidence_attempts": 6,
        "sessions": {"identified_sessions": 2, "successful_sessions": 1},
        "model_usage": {"calls": 7, "tokens": 260, "linked_calls": 6, "linked_tokens": 230},
        "transfer": {"attempts": 1, "successes": 1},
        "remediation": {"eligible_followups": 2, "repaired": 1},
    }
    delta = analytics_delta(before, after)
    assert delta["evidence_attempts"] == 3
    assert delta["successful_sessions"] == 1
    assert delta["model_calls"] == 3
    assert delta["model_tokens"] == 160
    assert delta["transfer_successes"] == 1
    assert delta["remediation_repairs"] == 1



def test_subject_presets_are_coherent_and_cover_the_validation_matrix():
    assert set(SCENARIOS) == {
        "math_fractions",
        "biology_photosynthesis",
        "physics_newton2",
        "spanish_past_tense",
        "business_contribution_margin",
    }
    for preset in SCENARIOS.values():
        assert preset.topic.strip()
        assert preset.objective.strip()
        assert preset.chat_prompt.strip()
        assert preset.question.strip()
        assert preset.explanation_answer.strip()
        assert preset.transfer_answer.strip()
        assert preset.question != preset.transfer_answer


def test_learner_profiles_cover_distinct_behavioral_paths():
    assert set(LEARNER_PROFILES) == {
        "advanced",
        "beginner",
        "confident_wrong",
        "quiet_partial",
        "curious",
        "struggling",
        "fast_learner",
        "interrupter",
    }
    assert LEARNER_PROFILES["advanced"].wrong_attempts == 0
    assert LEARNER_PROFILES["beginner"].request_hint is True
    assert LEARNER_PROFILES["confident_wrong"].wrong_attempts == 1
    assert LEARNER_PROFILES["quiet_partial"].partial_free_response is True
    assert LEARNER_PROFILES["curious"].ask_question is True
    assert LEARNER_PROFILES["struggling"].attempt_correct is False
    assert LEARNER_PROFILES["struggling"].wrong_attempts >= 2
    assert LEARNER_PROFILES["fast_learner"].reconnect is False
    assert LEARNER_PROFILES["interrupter"].ask_question is True
    assert LEARNER_PROFILES["interrupter"].request_hint is True


def test_report_groups_results_by_scenario_and_learner_profile():
    report = Report(
        run_id="r1",
        phase="seed",
        base_url="https://api.lyoai.app",
        session_id="s1",
        scenario="biology_photosynthesis",
        learner_profile="curious",
        topic="photosynthesis",
    )
    body = report.to_dict()
    assert body["scenario"] == "biology_photosynthesis"
    assert body["learner_profile"] == "curious"
    assert body["report_version"] == 2



def test_report_includes_blank_human_quality_rubric():
    report = Report(
        run_id="r2",
        phase="seed",
        base_url="https://api.lyoai.app",
        session_id="s2",
        scenario="math_fractions",
        learner_profile="interrupter",
        topic="comparing fractions",
    ).to_dict()
    rubric = report["quality_rubric"]
    assert len(rubric) == 8
    assert {item["criterion"] for item in rubric} == {
        "answers_learner_words",
        "examples_progress",
        "detour_then_resume",
        "misconception_specific_repair",
        "hint_preserves_struggle",
        "transfer_is_novel",
        "avoids_monologue_repetition",
        "visual_adds_information",
    }
    assert all(item["score"] is None for item in rubric)
    assert all(item["scale"] == "1-5" for item in rubric)



def test_seed_and_review_classroom_calls_use_the_full_matrix_contract():
    tree = ast.parse(
        Path("scripts/live_teacher_quality.py").read_text(encoding="utf-8")
    )
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "classroom"
    ]
    assert len(calls) == 2
    required = {
        "question",
        "explanation_answer",
        "transfer_answer",
        "objective",
        "learner_profile",
    }
    for call in calls:
        names = {keyword.arg for keyword in call.keywords if keyword.arg}
        assert required <= names
