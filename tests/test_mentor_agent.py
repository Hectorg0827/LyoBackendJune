import pytest
from unittest.mock import AsyncMock, MagicMock

import lyo_app.ai_agents.mentor_agent as mentor_module
from lyo_app.ai_agents.mentor_agent import AIMentor
from lyo_app.ai_agents.orchestrator import LanguageCode, ModelResponse, ModelType
from lyo_app.services.memory_synthesis import memory_synthesis_service


@pytest.mark.asyncio
async def test_get_response_and_persistence(monkeypatch):
    agent = AIMentor()
    fake_model_resp = ModelResponse(
        content="Test reply",
        model_used=ModelType.GEMMA_4_ON_DEVICE,
        response_time_ms=50.0,
        language_detected=LanguageCode.ENGLISH,
    )
    # get_response drives the orchestrator via generate_response
    monkeypatch.setattr(
        mentor_module,
        "ai_orchestrator",
        AsyncMock(generate_response=AsyncMock(return_value=fake_model_resp)),
    )
    # External context providers aren't under test here
    monkeypatch.setattr(
        memory_synthesis_service, "get_memory_for_prompt", AsyncMock(return_value="")
    )
    monkeypatch.setattr(agent, "_get_user_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(agent, "_get_engagement_state", AsyncMock(return_value=None))
    monkeypatch.setattr(agent, "_queue_memory_synthesis", MagicMock())

    # Mock DB session: capture the persisted interaction, assign an id on refresh
    added = []
    mock_db = AsyncMock()
    mock_db.add = MagicMock(side_effect=added.append)  # session.add is sync

    async def fake_refresh(obj):
        obj.id = 123

    mock_db.refresh = AsyncMock(side_effect=fake_refresh)
    mock_db.get = AsyncMock(return_value=None)

    result = await agent.get_response(
        user_id=42, message="Hello, AI", db=mock_db, context={"kata": "test"}
    )

    assert result["response"] == "Test reply"
    assert result["model_used"] == ModelType.GEMMA_4_ON_DEVICE
    assert isinstance(result["response_time_ms"], float)
    assert result["interaction_id"] == 123
    assert isinstance(result["conversation_id"], str)
    assert len(added) == 1
    inter = added[0]
    assert inter.user_message == "Hello, AI"
    assert inter.mentor_response == "Test reply"


@pytest.mark.asyncio
async def test_proactive_check_in(monkeypatch):
    agent = AIMentor()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()  # session.add is sync
    sent = []

    async def fake_send(message, user_id):
        sent.append((user_id, message))
        return True

    monkeypatch.setattr(
        mentor_module.connection_manager,
        "send_personal_message",
        AsyncMock(side_effect=fake_send),
    )

    await agent.proactive_check_in(user_id=7, reason="struggling", db=mock_db)

    assert mock_db.add.called
    assert len(sent) == 1
    uid, msg = sent[0]
    assert uid == 7
    assert "struggling" in msg
