import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from lyo_app.core.celery_tasks.ai_tasks import analyze_user_activity_task
from lyo_app.ai_agents.sentiment_agent import sentiment_engagement_agent
from lyo_app.ai_agents.mentor_agent import AIMentor
import lyo_app.core.database as db_module

@pytest.fixture(autouse=True)
def setup_mocks(monkeypatch):
    # Mock DB session context manager
    class DummySession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
    dummy_db = DummySession()
    # get_db_session returns dummy session context manager
    async def fake_get_db_session():
        return dummy_db
    monkeypatch.setattr(db_module, 'get_db_session', fake_get_db_session)

    # Mock sentiment engagement analysis call
    monkeypatch.setattr(sentiment_engagement_agent, 'analyze_user_action', AsyncMock())
    # Mock proactive_check_in on AIMentor
    mock_mentor = MagicMock()
    mock_mentor.proactive_check_in = AsyncMock()
    monkeypatch.setattr(AIMentor, '__init__', lambda self: None)
    monkeypatch.setattr(AIMentor, 'proactive_check_in', mock_mentor.proactive_check_in)
    return {'db': dummy_db, 'mentor': mock_mentor}

def test_analyze_user_activity_task_calls_agents(setup_mocks):
    # Call the Celery task synchronously
    analyze_user_activity_task(user_id=5, action='test_action', metadata={'key': 'value'}, user_message='hi')
    # sentiment analysis should have been called once
    sentiment_engagement_agent.analyze_user_action.assert_awaited_once_with(
        user_id=5,
        action='test_action',
        metadata={'key': 'value'},
        db=setup_mocks['db'],
        user_message='hi'
    )
    # proactive_check_in should have been called once with same user_id and reason
    setup_mocks['mentor'].proactive_check_in.assert_awaited_once_with(
        user_id=5,
        reason='test_action',
        db=setup_mocks['db']
    )
