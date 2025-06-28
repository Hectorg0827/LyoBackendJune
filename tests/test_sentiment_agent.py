import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from lyo_app.ai_agents.sentiment_agent import SentimentAndEngagementAgent
from lyo_app.ai_agents.models import UserEngagementStateEnum

@pytest.mark.asyncio
async def test_analyze_user_action_without_message(monkeypatch):
    agent = SentimentAndEngagementAgent()
    # Mock DB session and state retrieval
    dummy_state = MagicMock()
    dummy_state.state = UserEngagementStateEnum.IDLE
    monkeypatch.setattr(agent, "_get_or_create_engagement_state", AsyncMock(return_value=dummy_state))
    monkeypatch.setattr(agent, "_get_recent_activities", AsyncMock(return_value=[]))
    monkeypatch.setattr(agent, "_get_sentiment_history", AsyncMock(return_value=[]))
    # Stub engagement pattern analysis
    monkeypatch.setattr(
        agent.engagement_analyzer,
        "analyze_engagement_pattern",
        lambda **kwargs: {"engagement_level": "engaged", "recommended_actions": []}
    )
    # Stub update and check methods
    monkeypatch.setattr(agent, "_determine_new_engagement_state", AsyncMock(return_value=UserEngagementStateEnum.ENGAGED))
    monkeypatch.setattr(agent, "_update_engagement_state", AsyncMock())
    monkeypatch.setattr(agent, "_check_intervention_triggers", AsyncMock(return_value=False))
    monkeypatch.setattr(agent, "_log_analysis", AsyncMock())

    result = await agent.analyze_user_action(
        user_id=1,
        action="test_action",
        metadata={"foo": "bar"},
        db=AsyncMock(),
        user_message=None
    )
    assert result["user_id"] == 1
    assert result["action"] == "test_action"
    assert result["previous_state"] == "IDLE"
    assert result["new_state"] == "ENGAGED"
    assert result["intervention_triggered"] is False
    assert isinstance(datetime.fromisoformat(result["timestamp"]), datetime)
