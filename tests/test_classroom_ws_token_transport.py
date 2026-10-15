"""Classroom credentials must not be embedded in WebSocket request URLs."""
import json
from pathlib import Path

from lyo_app.ai_classroom.websocket_routes import classroom_access_token_from_message


def test_dedicated_first_frame_requires_explicit_auth_event():
    token = "a" * 120
    assert classroom_access_token_from_message(json.dumps({
        "type": "classroom_auth", "token": token,
    })) == token
    assert classroom_access_token_from_message(json.dumps({
        "action_intent": "continue", "token": token,
    })) is None
    assert classroom_access_token_from_message(json.dumps({
        "type": "classroom_auth", "token": "",
    })) is None
    assert classroom_access_token_from_message(json.dumps({
        "type": "classroom_auth", "token": {"secret": token},
    })) is None
    assert classroom_access_token_from_message("not-json") is None
    assert classroom_access_token_from_message("[]") is None


def test_black_box_teacher_uses_first_frame_auth_and_not_query_token():
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "live_teacher_quality.py"
    ).read_text(encoding="utf-8")
    assert '"token": self.token,' not in source
    assert source.count('ws.send(json.dumps({"type": "classroom_auth", "token": self.token}))') == 1
    assert source.count('ws2.send(json.dumps({"type": "classroom_auth", "token": self.token}))') == 1


def test_websocket_route_keeps_legacy_query_auth_opt_out():
    source = (
        Path(__file__).resolve().parents[1] / "lyo_app" / "ai_classroom" / "websocket_routes.py"
    ).read_text(encoding="utf-8")
    assert 'CLASSROOM_ALLOW_QUERY_AUTH' in source
    assert 'classroom_access_token_from_message(auth_raw)' in source
    assert 'await websocket.accept()' in source
    assert 'await asyncio.wait_for(websocket.receive_text(), timeout=8)' in source
    assert 'f"WebSocket JWT authentication failed: {e}"' not in source
