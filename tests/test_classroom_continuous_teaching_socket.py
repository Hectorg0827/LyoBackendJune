"""Authenticated WebSocket bridge/scene concurrency test with no paid providers.

This uses the real Classroom websocket route and real bridge wire contracts,
but stubs only auth, DB, scene generation and delivery. It proves a bridge
reply can arrive while the director is still doing a slow scene generation,
without submitting a duplicate authoritative action or reading learner data.
"""
import asyncio
import json
from types import SimpleNamespace

from fastapi import WebSocketDisconnect

from lyo_app.ai_classroom import continuous_teaching
from lyo_app.ai_classroom import websocket_routes
from lyo_app.ai_classroom.websocket_manager import ConnectionState
from lyo_app.auth import jwt_auth


class SyntheticWebSocket:
    def __init__(self):
        self.query_params = {
            "token": "synthetic-test-token",
            "continuous_teaching": "1",
            "topic": "Fractions",
            "bridge_language": "en-US",
        }
        self.incoming = asyncio.Queue()
        self.sent = []
        self.client_state = SimpleNamespace(name="CONNECTED")

    async def receive_text(self):
        frame = await self.incoming.get()
        if frame is None:
            raise WebSocketDisconnect(code=1000)
        return json.dumps(frame)

    async def send_text(self, frame):
        self.sent.append(json.loads(frame))

    async def close(self, code=1000, reason=""):
        self.client_state.name = "DISCONNECTED"

    def push(self, message):
        self.incoming.put_nowait(message)


class SyntheticManager:
    def __init__(self):
        self.sent = []
        self.real_actions = []
        self.generation_started = asyncio.Event()
        self.generation_finished = asyncio.Event()
        self.disconnected = False

    async def connect_client(self, websocket, user_id, session_id, device_id=None):
        assert user_id == "synthetic-student"
        return SimpleNamespace(
            websocket=websocket,
            connection_id="connection-1",
            user_id=user_id,
            session_id=session_id,
            state=ConnectionState.ACTIVE,
        )

    async def send_to_connection(self, connection_id, payload):
        assert connection_id == "connection-1"
        self.sent.append(payload)

    async def handle_client_message(self, connection_id, message):
        self.real_actions.append(json.loads(message))
        self.generation_started.set()
        await self.generation_finished.wait()

    async def disconnect_client(self, connection_id):
        self.disconnected = True


def test_actual_websocket_receiver_stays_live_during_parallel_scene_generation(monkeypatch):
    async def run():
        async def fake_verify(token, expected_type=None):
            assert token == "synthetic-test-token"
            return SimpleNamespace(user_id="synthetic-student")

        async def fake_sessions():
            yield object()

        async def fake_heartbeat(*args):
            await asyncio.Event().wait()

        async def fake_register(*args):
            pass

        async def fake_welcome(*args, **kwargs):
            pass

        async def fast_reply(topic, language, answer):
            assert "pattern" in answer
            return "Interesting observation. Can you explain the pattern?"

        class FakeBridge(continuous_teaching.ContinuousTeachingBridge):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, ai_reply=fast_reply)

        monkeypatch.setattr(jwt_auth, "verify_token_async", fake_verify)
        monkeypatch.setattr(websocket_routes, "get_async_session", fake_sessions)
        monkeypatch.setattr(websocket_routes, "SceneLifecycleEngine", lambda db, manager: object())
        monkeypatch.setattr(websocket_routes, "_register_lifecycle_handlers", fake_register)
        monkeypatch.setattr(websocket_routes, "_send_welcome_scene", fake_welcome)
        monkeypatch.setattr(websocket_routes, "_classroom_heartbeat", fake_heartbeat)
        monkeypatch.setattr(continuous_teaching, "ContinuousTeachingBridge", FakeBridge)
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("LYO_CONTINUOUS_TEACHING_STAGING", "1")
        monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)

        socket = SyntheticWebSocket()
        manager = SyntheticManager()
        endpoint = asyncio.create_task(
            websocket_routes.websocket_endpoint(
                socket, "synthetic-session", ws_manager=manager,
            )
        )

        try:
            # The startup bridge is a separate non-scene event.
            await asyncio.wait_for(
                _wait_for(lambda: any(
                    m.event_type == "bridge_message"
                    and m.data.get("phase") == "startup"
                    for m in manager.sent
                )), 3,
            )
            socket.push({
                "event_type": "user_action",
                "action_intent": "continue",
                "session_id": "synthetic-session",
            })
            await asyncio.wait_for(manager.generation_started.wait(), 3)

            transition = [
                m for m in manager.sent
                if m.event_type == "bridge_message"
                and m.data.get("phase") == "transition"
            ]
            assert len(transition) == 1
            generation = transition[0].data["generation"]

            socket.push({
                "event_type": "bridge_reply",
                "session_id": "synthetic-session",
                "generation": generation,
                "text": "I noticed a pattern in the fractions",
            })
            await asyncio.wait_for(
                _wait_for(lambda: any(
                    m.event_type == "bridge_message"
                    and m.data.get("ai_generated") is True
                    for m in manager.sent
                )), 3,
            )
            assert not manager.generation_finished.is_set(), "Bridge reply must arrive while director is still busy"

            # Double-taps must not execute the authoritative action twice.
            socket.push({
                "event_type": "user_action",
                "action_intent": "continue",
                "session_id": "synthetic-session",
            })
            await asyncio.sleep(0.03)
            assert len(manager.real_actions) == 1
            manager.generation_finished.set()
            socket.push(None)
            await asyncio.wait_for(endpoint, 3)
            assert manager.disconnected
            assert len(manager.real_actions) == 1
            assert all(
                "verdict" not in m.data and "mastery" not in m.data
                for m in manager.sent if m.event_type == "bridge_message"
            )
        finally:
            manager.generation_finished.set()
            if not endpoint.done():
                endpoint.cancel()
                try:
                    await endpoint
                except asyncio.CancelledError:
                    pass

    asyncio.run(run())


async def _wait_for(predicate):
    while not predicate():
        await asyncio.sleep(0.005)
