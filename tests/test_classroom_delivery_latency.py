from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from lyo_app.ai_classroom.sdui_models import TeacherMessage
from lyo_app.ai_classroom.websocket_manager import SceneStreamer

@pytest.mark.asyncio
@pytest.mark.parametrize('latency', [0, 50, 500])
async def test_adaptive_delivery_has_no_artificial_thinking_delay(latency):
    manager = SimpleNamespace(send_to_connection=AsyncMock())
    streamer = SceneStreamer(manager)
    scene = SimpleNamespace(components=[TeacherMessage(text='A useful answer.')])
    connection = SimpleNamespace(connection_id='connection', session_id='lesson', user_id='learner', latency_ms=latency)
    with patch('lyo_app.ai_classroom.websocket_manager.asyncio.sleep', new_callable=AsyncMock) as sleep:
        await streamer._stream_adaptive(scene, connection)
        sleep.assert_not_awaited()
    payload = manager.send_to_connection.call_args.args[1]
    assert payload.render_immediately
    assert payload.delay_after_previous_ms == 0

@pytest.mark.asyncio
async def test_explicit_progressive_mode_honors_only_authored_delays():
    manager = SimpleNamespace(send_to_connection=AsyncMock())
    streamer = SceneStreamer(manager)
    scene = SimpleNamespace(components=[
        TeacherMessage(text='An immediate answer.', delay_ms=0),
        TeacherMessage(text='An intentional pause.', delay_ms=100),
    ])
    connection = SimpleNamespace(connection_id='connection', session_id='lesson', user_id='learner')
    with patch('lyo_app.ai_classroom.websocket_manager.asyncio.sleep', new_callable=AsyncMock) as sleep:
        await streamer._stream_progressive(scene, connection)
        sleep.assert_awaited_once_with(0.1)
    assert manager.send_to_connection.await_count == 2
