import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

import lyo_app.ai_agents.mentor_agent as mentor_module
from lyo_app.ai_agents.mentor_agent import AIMentor, ConversationContext
from lyo_app.ai_agents.orchestrator import ModelResponse, ModelType

@pytest.mark.asyncio
async def test_get_response_and_persistence(monkeypatch):
    agent = AIMentor()
    # Prepare fake AI orchestrator response
    fake_model_resp = ModelResponse(content="Test reply", model_used=ModelType.GEMMA_ON_DEVICE, response_time_ms=50)
    # Monkeypatch global orchestrator
    monkeypatch.setattr(mentor_module, 'ai_orchestrator', AsyncMock(route_and_execute=AsyncMock(return_value=fake_model_resp)))

    # Create a mock DB session
    mock_db = AsyncMock()
    # Capture added interaction
    added = []
    async def add_interaction(obj):
        added.append(obj)
    mock_db.add.side_effect = add_interaction
    # Commit and refresh are no-ops
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    # Test get_response
    result = await agent.get_response(user_id=42, message="Hello, AI", db=mock_db, context={"kata": "test"})

    # Validate structure
    assert result['response'] == "Test reply"
    assert result['model_used'] == ModelType.GEMMA_ON_DEVICE
    assert isinstance(result['response_time_ms'], float)
    assert result['interaction_id'] is not None
    assert 'conversation_id' in result
    assert isinstance(result['conversation_id'], str)
    # Ensure DB add was called
    assert len(added) == 1
    inter = added[0]
    assert inter.user_message == "Hello, AI"
    assert inter.mentor_response == "Test reply"

@pytest.mark.asyncio
async def test_proactive_check_in(monkeypatch):
    agent = AIMentor()
    # Mock DB
    mock_db = AsyncMock()
    mock_db.add = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    # Mock WebSocket send
    sent = []
    async def fake_send(message, user_id):
        sent.append((user_id, message))
        return True
    monkeypatch.setattr(mentor_module.connection_manager, 'send_personal_message', AsyncMock(side_effect=fake_send))

    # Call proactive_check_in
    await agent.proactive_check_in(user_id=7, reason="struggling", db=mock_db)

    # Ensure DB interaction and websocket send
    assert mock_db.add.called
    assert len(sent) == 1
    uid, msg = sent[0]
    assert uid == 7
    assert 'struggling' in msg
