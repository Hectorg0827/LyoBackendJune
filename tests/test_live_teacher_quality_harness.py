import pytest

from scripts.live_teacher_quality import (
    choose_option,
    parse_sse_lines,
    require_https,
    safe_snapshot,
    scene_from_message,
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
