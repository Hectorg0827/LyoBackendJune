"""Classroom WebSocket owner isolation: no provider, DB, or real sockets."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.sdui_models import WebSocketPayload, WebSocketEventType
from lyo_app.ai_classroom.websocket_manager import (
    ClientConnection, ConnectionState, WebSocketManager,
)


@pytest.fixture
def manager_and_connections():
    manager = WebSocketManager()
    manager.delivery_manager.queue_message = AsyncMock()
    manager.scene_streamer.stream_scene = AsyncMock()
    users = [
        ClientConnection(user_id="17", session_id="shared-id", state=ConnectionState.ACTIVE),
        ClientConnection(user_id="17", session_id="shared-id", state=ConnectionState.ACTIVE),
        ClientConnection(user_id="18", session_id="shared-id", state=ConnectionState.ACTIVE),
    ]
    for connection in users:
        manager.connections[connection.connection_id] = connection
    return manager, users


async def _add_all(manager, users):
    for connection in users:
        await manager._add_to_room(connection, "shared-id")


def _payload(owner=None):
    return WebSocketPayload(
        event_type=WebSocketEventType.SYSTEM_STATE,
        session_id="shared-id",
        user_id=owner,
        data={"synthetic": True},
    )


@pytest.mark.asyncio
async def test_same_client_selected_id_creates_separate_owner_rooms(manager_and_connections):
    manager, users = manager_and_connections
    await _add_all(manager, users)
    assert set(manager.rooms) == {("17", "shared-id"), ("18", "shared-id")}
    assert len(manager.rooms[("17", "shared-id")].connections) == 2
    assert len(manager.rooms[("18", "shared-id")].connections) == 1


@pytest.mark.asyncio
async def test_session_message_is_delivered_only_to_owner_devices(manager_and_connections):
    manager, users = manager_and_connections
    await _add_all(manager, users)
    await manager.send_to_session("shared-id", _payload("17"))
    queued = manager.delivery_manager.queue_message.await_args_list
    assert {call.args[0] for call in queued} == {
        users[0].connection_id, users[1].connection_id,
    }


@pytest.mark.asyncio
async def test_session_message_without_owner_fails_closed(manager_and_connections):
    manager, users = manager_and_connections
    await _add_all(manager, users)
    await manager.send_to_session("shared-id", _payload())
    manager.delivery_manager.queue_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_feedback_cannot_reach_other_user_sharing_session_id(manager_and_connections):
    manager, users = manager_and_connections
    await _add_all(manager, users)
    await manager.send_answer_feedback(
        session_id="shared-id", user_id="18", component_id="quiz",
        verdict="correct", feedback="private-feedback", language="en",
    )
    queued = manager.delivery_manager.queue_message.await_args_list
    assert [call.args[0] for call in queued] == [users[2].connection_id]


@pytest.mark.asyncio
async def test_scene_streaming_requires_and_filters_by_owner(manager_and_connections):
    manager, users = manager_and_connections
    await _add_all(manager, users)
    scene = SimpleNamespace(scene_id="synthetic-scene")
    await manager.stream_scene_to_session("shared-id", scene)
    manager.scene_streamer.stream_scene.assert_not_awaited()
    await manager.stream_scene_to_session("shared-id", scene, user_id="18")
    calls = manager.scene_streamer.stream_scene.await_args_list
    assert [call.args[1].connection_id for call in calls] == [users[2].connection_id]
    manager.scene_streamer.stream_scene.reset_mock()
    await manager.stream_scene_to_session("shared-id", scene, user_id="17")
    calls = manager.scene_streamer.stream_scene.await_args_list
    assert {call.args[1].connection_id for call in calls} == {
        users[0].connection_id, users[1].connection_id,
    }


@pytest.mark.asyncio
async def test_direct_delivery_rejects_mismatched_owner_tag(manager_and_connections):
    manager, users = manager_and_connections
    await _add_all(manager, users)
    await manager.send_to_connection(users[2].connection_id, _payload("17"))
    manager.delivery_manager.queue_message.assert_not_awaited()
    await manager.send_to_connection(users[2].connection_id, _payload("18"))
    assert manager.delivery_manager.queue_message.await_count == 1


@pytest.mark.asyncio
async def test_owner_tagged_global_broadcast_stays_with_owner(manager_and_connections):
    manager, users = manager_and_connections
    await _add_all(manager, users)
    await manager.broadcast(_payload("17"))
    calls = manager.delivery_manager.queue_message.await_args_list
    assert {call.args[0] for call in calls} == {
        users[0].connection_id, users[1].connection_id,
    }


@pytest.mark.asyncio
async def test_remove_one_owner_does_not_remove_other_owner_room(manager_and_connections):
    manager, users = manager_and_connections
    await _add_all(manager, users)
    await manager._remove_from_room(users[0], "shared-id")
    assert ("17", "shared-id") in manager.rooms
    await manager._remove_from_room(users[1], "shared-id")
    assert ("17", "shared-id") not in manager.rooms
    assert ("18", "shared-id") in manager.rooms
    assert users[2].connection_id in manager.rooms[("18", "shared-id")].connections
