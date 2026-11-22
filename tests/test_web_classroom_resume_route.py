"""Unit contract: WebSocket resume cannot silently author a different scene."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from lyo_app.ai_classroom import websocket_routes as ws


def connection(resume="1"):
    socket = SimpleNamespace(query_params={"resume": resume}, send_text=AsyncMock())
    return SimpleNamespace(user_id="23", session_id="qa-session", websocket=socket)


@pytest.mark.asyncio
async def test_authenticated_reconnect_replays_exact_scene_without_welcome(monkeypatch):
    conn = connection("1")
    engine = SimpleNamespace(
        resume_saved_scene=AsyncMock(return_value=SimpleNamespace(scene_id="saved-scene"))
    )
    welcome = AsyncMock()
    monkeypatch.setattr(ws, "_send_welcome_scene", welcome)
    result = await ws._start_or_resume_scene(engine, conn, "adaptive")
    assert result == "resumed"
    engine.resume_saved_scene.assert_awaited_once_with("23", "qa-session")
    welcome.assert_not_awaited()
    conn.websocket.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_without_saved_state_never_generates_new_lesson(monkeypatch):
    conn = connection("true")
    engine = SimpleNamespace(resume_saved_scene=AsyncMock(return_value=None))
    welcome = AsyncMock()
    monkeypatch.setattr(ws, "_send_welcome_scene", welcome)
    result = await ws._start_or_resume_scene(engine, conn, "adaptive")
    assert result == "unavailable"
    welcome.assert_not_awaited()
    payload = json.loads(conn.websocket.send_text.await_args.args[0])
    assert payload["data"]["error"] == "resume_unavailable"
    assert payload["session_id"] == conn.session_id


@pytest.mark.asyncio
async def test_new_classroom_still_starts_welcome_scene(monkeypatch):
    conn = connection("")
    engine = SimpleNamespace(resume_saved_scene=AsyncMock())
    welcome = AsyncMock()
    monkeypatch.setattr(ws, "_send_welcome_scene", welcome)
    result = await ws._start_or_resume_scene(engine, conn, "adaptive")
    assert result == "new"
    welcome.assert_awaited_once()
    engine.resume_saved_scene.assert_not_awaited()
