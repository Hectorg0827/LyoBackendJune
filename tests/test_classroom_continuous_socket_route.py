"""Ephemeral authenticated WebSocket acceptance: no external services or real learner data.

Use the actual endpoint loop, mocked JWT and connection/delivery/scene providers.
This checks identity isolation and that bridge replies cannot reach lesson actions.
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from lyo_app.ai_classroom import websocket_routes as routes
from lyo_app.ai_classroom.websocket_manager import ConnectionState, StreamingMode


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.asyncio
async def test_parallel_bridge_socket_rejects_foreign_identity_and_never_grades_reply(
    monkeypatch, environment,
):
    import lyo_app.auth.jwt_auth as jwt_auth

    # The transport must pass in the ordinary staging mode and in a
    # production canary whose JWT-authenticated user is explicitly allowlisted.
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", environment)
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("LYO_CONTINUOUS_TEACHING_STAGING", "1")
    monkeypatch.setenv("LYO_CONTINUOUS_TEACHING_PRODUCTION_ENABLED", "1")
    monkeypatch.setenv("LYO_CONTINUOUS_TEACHING_PRODUCTION_USER_IDS", "learner-A")
    monkeypatch.setenv("CLASSROOM_AI_TRIAL_ENABLED", "0")
    monkeypatch.setattr(jwt_auth, "verify_token_async",
                        AsyncMock(return_value=SimpleNamespace(user_id="learner-A")))

    frames = [
        {"event_type": "user_action", "session_id": "other-seat",
         "action_intent": "continue"},
        {"event_type": "user_action", "session_id": "session-A",
         "user_id": "learner-B", "action_intent": "continue"},
        {"event_type": "user_action", "session_id": "session-A",
         "action_intent": "continue", "component_id": "continue-button"},
        {"event_type": "bridge_reply", "session_id": "other-seat",
         "generation": 2, "text": "Should be ignored"},
        {"event_type": "bridge_reply", "session_id": "session-A",
         "generation": 2, "text": "I see matching pieces"},
    ]

    class FakeSocket:
        query_params = {
            "token": "synthetic-test-token",
            "continuous_teaching": "1", "topic": "fractions",
            "language": "en-US",
        }
        client_state = SimpleNamespace(name="CONNECTED")

        async def receive_text(self):
            await asyncio.sleep(0.03)
            if frames:
                return json.dumps(frames.pop(0))
            raise WebSocketDisconnect(code=1000)

        async def close(self, **kwargs):
            pass

    websocket = FakeSocket()
    connection = SimpleNamespace(
        connection_id="conn-A", session_id="session-A", user_id="learner-A",
        websocket=websocket, state=ConnectionState.ACTIVE,
    )
    deliveries = []
    sequence = []
    real_actions = []

    async def deliver(connection_id, payload):
        deliveries.append((connection_id, payload))
        if payload.event_type == "bridge_message":
            sequence.append(payload.data["phase"])

    async def director_handler(connection_id, raw):
        real_actions.append((connection_id, json.loads(raw)))
        await asyncio.sleep(0.2)  # real generation still in flight

    manager = SimpleNamespace(
        connect_client=AsyncMock(return_value=connection),
        send_to_connection=AsyncMock(side_effect=deliver),
        handle_client_message=AsyncMock(side_effect=director_handler),
        disconnect_client=AsyncMock(),
    )

    async def fake_db():
        # Simulate a slow pool/setup: the local teacher must speak FIRST.
        await asyncio.sleep(0.06)
        sequence.append("db_ready")
        yield object()

    async def keepalive(*_args):
        await asyncio.Event().wait()

    monkeypatch.setattr(routes, "get_async_session", fake_db)
    monkeypatch.setattr(routes, "SceneLifecycleEngine", lambda db, manager: object())
    monkeypatch.setattr(routes, "_register_lifecycle_handlers", AsyncMock())
    monkeypatch.setattr(routes, "_send_welcome_scene", AsyncMock())
    monkeypatch.setattr(routes, "_classroom_heartbeat", keepalive)

    await asyncio.wait_for(
        routes.websocket_endpoint(
            websocket, session_id="session-A",
            streaming_mode=StreamingMode.ADAPTIVE, ws_manager=manager,
        ),
        timeout=4,
    )

    mismatch = [payload for conn, payload in deliveries
                if payload.event_type == "error"
                and payload.data.get("error") == "session_mismatch"]
    assert len(mismatch) == 3
    assert all(conn == "conn-A" for conn, _ in deliveries)
    assert len(real_actions) == 1
    assert real_actions[0][0] == "conn-A"
    assert real_actions[0][1]["action_intent"] == "continue"
    assert all(action["event_type"] != "bridge_reply" for _, action in real_actions)
    prompts = [payload for _, payload in deliveries
               if payload.event_type == "bridge_message"]
    assert len(prompts) >= 2
    assert prompts[0].data["ungraded"] is True
    assert prompts[0].session_id == "session-A"
    assert prompts[0].data["phase"] == "startup"
    assert prompts[1].data["phase"] == "transition"
    assert sequence.index("startup") < sequence.index("db_ready")
    manager.disconnect_client.assert_awaited_once_with("conn-A")
