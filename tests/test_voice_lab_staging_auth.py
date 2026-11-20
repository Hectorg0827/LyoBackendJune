"""The dedicated Voice Lab trusts only the existing staging login service.

All tests use httpx.MockTransport and never call a real server or paid model.
"""
import httpx
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from lyo_app.auth.dependencies import get_current_user
from lyo_app.live_trial import staging_app, staging_auth


def _credential():
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake-staging-token")


def _mock_client(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(staging_auth.httpx, "AsyncClient",
                        lambda **kwargs: original(transport=transport, **kwargs))


@pytest.mark.asyncio
async def test_authenticated_active_staging_user(monkeypatch):
    def handler(request):
        assert request.url.host == "lyojourneystagingbackend-staging.up.railway.app"
        assert request.url.path == "/auth/me"
        assert request.headers.get("Authorization") == "Bearer fake-staging-token"
        return httpx.Response(200, json={
            "id": 42, "email": "tester@example.com", "username": "tester",
            "is_active": True, "is_verified": True,
            "created_at": "2026-10-31T00:00:00Z",
        })
    _mock_client(monkeypatch, handler)
    learner = await staging_auth.get_staging_trial_user(_credential())
    assert learner.id == 42
    assert staging_app.app.dependency_overrides[get_current_user] is staging_auth.get_staging_trial_user


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [301, 401, 403, 404, 500])
async def test_non_successful_staging_identity_fails_closed(monkeypatch, status_code):
    _mock_client(monkeypatch, lambda _: httpx.Response(status_code))
    with pytest.raises(HTTPException) as exc:
        await staging_auth.get_staging_trial_user(_credential())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"id": 42},
    {"id": -1, "email": "tester@example.com", "username": "tester",
     "is_active": True, "is_verified": True, "created_at": "2026-10-31T00:00:00Z"},
    {"id": 42, "email": "tester@example.com", "username": "tester",
     "is_active": False, "is_verified": True, "created_at": "2026-10-31T00:00:00Z"},
])
async def test_incomplete_or_inactive_staging_identity_fails_closed(monkeypatch, payload):
    _mock_client(monkeypatch, lambda _: httpx.Response(200, json=payload))
    with pytest.raises(HTTPException) as exc:
        await staging_auth.get_staging_trial_user(_credential())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_staging_identity_network_failure_fails_closed(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("offline", request=request)
    _mock_client(monkeypatch, handler)
    with pytest.raises(HTTPException) as exc:
        await staging_auth.get_staging_trial_user(_credential())
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_missing_or_oversized_bearer_never_calls_staging_server():
    for credentials in (None, HTTPAuthorizationCredentials(scheme="Bearer", credentials="x" * 8193)):
        with pytest.raises(HTTPException) as exc:
            await staging_auth.get_staging_trial_user(credentials)
        assert exc.value.status_code == 401
