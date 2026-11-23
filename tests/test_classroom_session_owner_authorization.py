"""Fail-closed ownership checks on Classroom session metadata and deletion.

No real learner, database, Redis, provider key or network request.
"""
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.routing import APIRoute
import pytest

from lyo_app.ai_classroom import routes


class DummyManager:
    def __init__(self):
        now = datetime(2026, 11, 22)
        self.sessions = {
            "mine": SimpleNamespace(
                session_id="mine", user_id="17",
                state=SimpleNamespace(value="active"),
                messages=["private learner message"], current_topic="Private topic",
                current_course_id="owned-course", preferences={"difficulty": "beginner"},
                created_at=now, updated_at=now,
            ),
            "unowned": SimpleNamespace(session_id="unowned", user_id=None),
        }
        self.deleted = []

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def end_session(self, session_id):
        if session_id not in self.sessions:
            return False
        del self.sessions[session_id]
        self.deleted.append(session_id)
        return True


@pytest.fixture
def manager(monkeypatch):
    dummy = DummyManager()
    monkeypatch.setattr(routes, "get_conversation_manager", lambda: dummy)
    return dummy


def _user(uid):
    return SimpleNamespace(id=uid)


def _assert_not_found(error):
    assert error.value.status_code == 404
    assert error.value.detail == "Session not found"


@pytest.mark.asyncio
async def test_owner_can_read_and_end_only_own_session(manager):
    info = await routes.get_session("mine", _user(17))
    assert info["current_topic"] == "Private topic"
    assert info["session_id"] == "mine"
    result = await routes.end_session("mine", _user(17))
    assert result == {"status": "ended", "session_id": "mine"}
    assert manager.deleted == ["mine"]
    with pytest.raises(HTTPException) as error:
        await routes.get_session("mine", _user(17))
    _assert_not_found(error)


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", ["mine", "unowned", "missing"])
async def test_other_user_cannot_read_session_data(manager, session_id):
    with pytest.raises(HTTPException) as error:
        await routes.get_session(session_id, _user(18))
    _assert_not_found(error)
    assert manager.deleted == []
    assert "mine" in manager.sessions


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", ["mine", "unowned", "missing"])
async def test_other_user_cannot_end_session(manager, session_id):
    with pytest.raises(HTTPException) as error:
        await routes.end_session(session_id, _user(18))
    _assert_not_found(error)
    assert manager.deleted == []
    assert "mine" in manager.sessions


@pytest.mark.asyncio
async def test_unowned_session_cannot_be_claimed_by_anyone(manager):
    for method in (routes.get_session, routes.end_session):
        with pytest.raises(HTTPException) as error:
            await method("unowned", _user(17))
        _assert_not_found(error)
    assert "unowned" in manager.sessions
    assert manager.deleted == []


@pytest.mark.asyncio
async def test_missing_identity_fails_closed(manager):
    for method in (routes.get_session, routes.end_session):
        with pytest.raises(HTTPException) as error:
            await method("mine", _user(None))
        _assert_not_found(error)
    assert manager.deleted == []


def test_both_public_routes_require_authentication_dependency():
    for path, method in (
        ("/api/v1/classroom/session/{session_id}", "GET"),
        ("/api/v1/classroom/session/{session_id}", "DELETE"),
    ):
        matches = [
            entry for entry in routes.router.routes
            if isinstance(entry, APIRoute)
            and entry.path == path and method in entry.methods
        ]
        assert len(matches) == 1
        assert any(
            dependency.call is routes.get_current_user
            for dependency in matches[0].dependant.dependencies
        ), f"{method} must depend on authenticated identity"
