"""A slow first teaching turn must not leave a WebSocket idle."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.websocket_routes import _classroom_heartbeat


@pytest.mark.asyncio
async def test_heartbeat_keeps_a_waiting_class_alive_and_stops_on_disconnect():
    connection = SimpleNamespace(connection_id="conn", session_id="lesson", user_id="learner")
    manager = SimpleNamespace(connections={"conn": connection}, send_to_connection=AsyncMock())
    task = asyncio.create_task(_classroom_heartbeat(manager, connection, interval=0.01))
    try:
        for _ in range(30):
            if manager.send_to_connection.await_count:
                break
            await asyncio.sleep(0.01)
        manager.send_to_connection.assert_awaited()
        sent_id, payload = manager.send_to_connection.await_args.args
        assert sent_id == "conn"
        assert payload.event_type == "system_state"
        assert payload.data == {"heartbeat": True}
        manager.connections.clear()
        await asyncio.wait_for(task, timeout=0.1)
        count = manager.send_to_connection.await_count
        await asyncio.sleep(0.02)
        assert manager.send_to_connection.await_count == count
    finally:
        task.cancel()
