import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

import lyo_app.ai_agents.routes as routes_module
from lyo_app.main import app
from lyo_app.core.config import settings
from lyo_app.ai_agents.schemas import MentorMessageResponse, UserActionAnalysisResponse

client = TestClient(app)

# Fixture to override dependency get_current_user
@pytest.fixture(autouse=True)
def mock_current_user(monkeypatch):
    class DummyUser:
        id = 1
        def has_role(self, role): return True
    monkeypatch.setattr('lyo_app.auth.dependencies.get_current_user', lambda: DummyUser())

# Test mentor conversation endpoint
def test_mentor_conversation(monkeypatch):
    # Prepare request and mock ai_mentor.get_response
    fake_response = {
        'response': 'Hello student',
        'interaction_id': 123,
        'model_used': 'gemma_on_device',
        'response_time_ms': 50.0,
        'strategy_used': 'simple',
        'conversation_id': 'sess-1',
        'engagement_state': 'engaged',
        'timestamp': datetime.utcnow().isoformat()
    }
    monkeypatch.setattr(routes_module.ai_mentor, 'get_response', AsyncMock(return_value=fake_response))

    payload = {'message': 'Hi AI', 'context': {'foo': 'bar'}}
    response = client.post(f"{settings.api_v1_prefix}/ai/mentor/conversation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data['response'] == fake_response['response']
    assert data['interaction_id'] == fake_response['interaction_id']

# Test engagement analyze endpoint
def test_engagement_analyze(monkeypatch):
    # Mock sentiment_engagement_agent.analyze_user_action
    fake_analysis = {
        'user_id': 1,
        'action': 'test',
        'previous_state': 'idle',
        'new_state': 'engaged',
        'sentiment_analysis': None,
        'engagement_analysis': {
            'engagement_level': 'engaged',
            'recommended_actions': []
        },
        'intervention_triggered': False,
        'recommendations': [],
        'timestamp': datetime.utcnow().isoformat()
    }
    monkeypatch.setattr(routes_module.sentiment_engagement_agent, 'analyze_user_action', AsyncMock(return_value=fake_analysis))

    payload = {'user_id': 1, 'action': 'test', 'metadata': {}, 'user_message': 'hello'}
    response = client.post(f"{settings.api_v1_prefix}/ai/engagement/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data['user_id'] == fake_analysis['user_id']
    assert data['new_state'] == fake_analysis['new_state']

# Test WebSocket endpoint connection
@pytest.mark.asyncio
async def test_websocket_connection(monkeypatch, anyio_backend):
    from starlette.websockets import WebSocketDisconnect
    url = f"ws://testserver{settings.api_v1_prefix}/ai/ws/1"
    with client.websocket_connect(url) as ws:
        # The manager sends initial connection_established message
        msg = ws.receive_json()
        assert msg['type'] == 'connection_established'
        assert 'connection_id' in msg
        # Test disconnection cleanup
    # Closing the context should disconnect cleanly
