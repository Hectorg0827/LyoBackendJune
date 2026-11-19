"""Legacy Classroom session endpoints must never cross learner boundaries.

Historically GET /session/{id}, history, continue and DELETE did not require
authentication, despite returning and mutating private conversation state.
This test is scoped to those four endpoints; production rollout is separate.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import inspect

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from lyo_app.ai_classroom import routes as classroom_routes
from lyo_app.auth.dependencies import get_current_user


HANDLERS = (
    classroom_routes.get_session,
    classroom_routes.end_session,
    classroom_routes.get_conversation_history,
    classroom_routes.continue_learning,
)


@pytest.mark.parametrize("handler", HANDLERS)
def test_legacy_classroom_session_endpoints_require_current_user(handler):
    signature = inspect.signature(handler)
    user = signature.parameters.get("current_user")
    assert user is not None
    assert isinstance(user.default, type(Depends(get_current_user)))
    assert user.default.dependency is get_current_user


@pytest.mark.parametrize("url,method", (
    ("/api/v1/classroom/session/synthetic", "get"),
    ("/api/v1/classroom/session/synthetic", "delete"),
    ("/api/v1/classroom/session/synthetic/history", "get"),
    ("/api/v1/classroom/session/synthetic/continue", "post"),
))
def test_legacy_session_endpoints_reject_anonymous_requests(url, method):
    app = FastAPI()
    app.include_router(classroom_routes.router)
    with TestClient(app) as client:
        response = getattr(client, method)(url)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", HANDLERS)
async def test_other_learner_cannot_read_mutate_or_continue_session(monkeypatch, handler):
    manager = Mock()
    manager.get_session.return_value = SimpleNamespace(user_id="42")
    manager.end_session.return_value = True
    manager.process_message = AsyncMock()
    monkeypatch.setattr(classroom_routes, "get_conversation_manager", lambda: manager)

    session = "synthetic-session-42"
    other = SimpleNamespace(id=43)
    with pytest.raises(HTTPException) as exc:
        if handler is classroom_routes.get_conversation_history:
            await handler(session, limit=50, current_user=other)
        else:
            await handler(session, current_user=other)
    assert exc.value.status_code == 404
    manager.end_session.assert_not_called()
    manager.process_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_can_read_session_metadata(monkeypatch):
    now = __import__("datetime").datetime.now()
    manager = Mock()
    manager.get_session.return_value = SimpleNamespace(
        user_id="42",
        session_id="synthetic-session-42",
        state=SimpleNamespace(value="active"),
        messages=[],
        current_topic="fractions",
        current_course_id=None,
        preferences={},
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(classroom_routes, "get_conversation_manager", lambda: manager)
    data = await classroom_routes.get_session("synthetic-session-42", current_user=SimpleNamespace(id=42))
    assert data["session_id"] == "synthetic-session-42"
    assert data["current_topic"] == "fractions"
