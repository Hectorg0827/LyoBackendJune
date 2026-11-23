"""Run actual Classroom scene serializer/transport with two authenticated room owners.

This has real Starlette ASGI WebSocket framing and no mocks of the
WebSocketManager or SceneStreamer. A single client-selected session ID is
used by two different users and two devices for one owner. A generated test
scene with synthetic canary text may only reach the intended owner.
No external learner/model, DB, Redis, Railway endpoint or paid tokens.
"""
import asyncio
import json

import pytest
from starlette.websockets import WebSocket

from lyo_app.ai_classroom.sdui_models import Scene, SceneType, TeacherMessage
from lyo_app.ai_classroom.websocket_manager import WebSocketManager, StreamingMode


class SyntheticASGISeat:
    def __init__(self):
        self.frames = []
        self.acknowledged = False
        self.websocket = WebSocket(
            {
                "type": "websocket",
                "path": "/api/v1/classroom/ws/connect",
                "headers": [], "query_string": b"",
                "scheme": "wss", "server": ("staging.test", 443),
                "client": ("127.0.0.1", 12345),
                "subprotocols": [],
            },
            self.receive,
            self.send,
        )

    async def receive(self):
        if not self.acknowledged:
            self.acknowledged = True
            return {"type": "websocket.connect"}
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(self, message):
        if message.get("type") == "websocket.send":
            self.frames.append(json.loads(message["text"]))

    def events(self, kind):
        return [
            frame for frame in self.frames
            if str(frame.get("event_type", "")).lower() == kind.lower()
        ]


async def wait_completed(*seats):
    for _ in range(80):
        if all(seat.events("scene_complete") for seat in seats):
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Scene streamer did not deliver complete event")


@pytest.mark.asyncio
async def test_actual_scene_streaming_same_id_across_two_authenticated_owners():
    manager = WebSocketManager()
    one, another_device, other_user = (
        SyntheticASGISeat(), SyntheticASGISeat(), SyntheticASGISeat()
    )
    connections = []
    try:
        for seat, owner in [
            (one, "1001"), (another_device, "1001"), (other_user, "1002"),
        ]:
            connection = await manager.connect_client(
                seat.websocket, user_id=owner, session_id="shared-legacy-course"
            )
            connections.append(connection)
        assert set(manager.rooms) == {
            ("1001", "shared-legacy-course"),
            ("1002", "shared-legacy-course"),
        }
        private_a = "SYNTHETIC_ONLY_OWNER_A_CANARY"
        scene_a = Scene(
            scene_type=SceneType.INSTRUCTION,
            components=[TeacherMessage(text=private_a, language_code="en-US")],
        )
        await manager.stream_scene_to_session(
            "shared-legacy-course", scene_a, StreamingMode.INSTANT,
            user_id="1001"
        )
        await wait_completed(one, another_device)
        assert all(
            any(private_a in json.dumps(frame) for frame in seat.frames)
            for seat in (one, another_device)
        )
        assert not any(private_a in json.dumps(f) for f in other_user.frames)
        assert all(
            str(f.get("user_id")) == "1001"
            for seat in (one, another_device)
            for f in seat.events("scene_start")
        )

        private_b = "SYNTHETIC_ONLY_OWNER_B_CANARY"
        scene_b = Scene(
            scene_type=SceneType.INSTRUCTION,
            components=[TeacherMessage(text=private_b, language_code="en-US")],
        )
        await manager.stream_scene_to_session(
            "shared-legacy-course", scene_b, StreamingMode.INSTANT,
            user_id="1002",
        )
        await wait_completed(other_user)
        assert any(private_b in json.dumps(f) for f in other_user.frames)
        assert not any(
            private_b in json.dumps(f)
            for seat in (one, another_device) for f in seat.frames
        )
        assert all(
            str(f.get("user_id")) == "1002"
            for f in other_user.events("scene_start")
        )

        # Replaying scene A to the same user stays with that user's devices.
        previous_other_frames = len(other_user.frames)
        await manager.stream_scene_to_session(
            "shared-legacy-course", scene_a, StreamingMode.INSTANT,
            user_id="1001"
        )
        await asyncio.sleep(0.18)
        assert len(other_user.frames) == previous_other_frames
    finally:
        for connection in connections:
            await manager.disconnect_client(connection.connection_id)
    assert manager.rooms == {}
