"""P0 reset safety: tampering, TTL, single use, and generic email behavior."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks

from lyo_app.auth import reset_routes as reset


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-test-secret-key-recovery-strong-123456789")
    monkeypatch.setenv("RESEND_API_KEY", "test-placeholder-not-delivered")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@example.org")


def user():
    return SimpleNamespace(id=51, email="learner@example.org", is_active=True,
                           hashed_password="existing-bcrypt-hash", auth_version=0)


def test_stateless_reset_token_is_password_bound_time_limited_and_tamper_proof():
    u = user()
    t = reset.create_reset_token(u, now=1000)
    assert reset.verify_reset_token(u, t, now=1001)
    assert not reset.verify_reset_token(u, t + "x", now=1002)
    assert not reset.verify_reset_token(u, t, now=4602)
    assert not reset.verify_reset_token(u, t, now=999)
    assert not reset.verify_reset_token(SimpleNamespace(id=99, hashed_password=u.hashed_password), t, now=1100)
    u.hashed_password = "changed-hash"
    assert not reset.verify_reset_token(u, t, now=1100)


@pytest.mark.asyncio
async def test_reset_request_is_nonenumerating_but_schedules_real_mail(monkeypatch):
    monkeypatch.setattr(reset, "_enforce_reset_limit", AsyncMock(return_value=None))
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    tasks = BackgroundTasks()
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user()
    db.execute = AsyncMock(return_value=result)
    reply = await reset.request_reset(
        payload=reset.ResetRequest(email="learner@example.org"),
        request=request, background_tasks=tasks, db=db)
    assert "If the account exists" in reply["message"]
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].func is reset._send_reset_email
    # An unknown email reports the same message and sends nothing.
    other = BackgroundTasks()
    result.scalar_one_or_none.return_value = None
    missing = await reset.request_reset(
        payload=reset.ResetRequest(email="missing@example.org"),
        request=request, background_tasks=other, db=db)
    assert missing == reply
    assert other.tasks == []


@pytest.mark.asyncio
async def test_confirm_changes_password_and_invalidates_link(monkeypatch):
    u = user()
    token = reset.create_reset_token(u)
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = u
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    monkeypatch.setattr(reset, "hash_password", lambda v: "new-bcrypt-hash")
    reply = await reset.confirm_reset(reset.ResetConfirm(
        token=token, new_password="a-long-new-password",
        confirm_password="a-long-new-password"), db=db)
    assert "Password updated" in reply["message"]
    assert u.hashed_password == "new-bcrypt-hash"
    assert not reset.verify_reset_token(u, token)
    assert u.auth_version == 1
    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_staging_reset_email_uses_explicit_https_frontend_url(monkeypatch):
    from urllib.parse import urlsplit, parse_qs

    monkeypatch.setenv("LYO_PASSWORD_RESET_URL",
                       "https://lyoonestagingweb-staging.up.railway.app/auth/reset-password")
    outgoing = {}

    class FakeReply:
        def raise_for_status(self):
            return None

    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, endpoint, headers, json):
            outgoing.update(json)
            return FakeReply()

    monkeypatch.setattr(reset.httpx, "AsyncClient", FakeHttpClient)
    await reset._send_reset_email("learner@example.org", "test-secret-token")
    url = outgoing["text"].split("within one hour: ", 1)[1]
    assert urlsplit(url).hostname == "lyoonestagingweb-staging.up.railway.app"
    assert urlsplit(url).path == "/auth/reset-password"
    assert parse_qs(urlsplit(url).query) == {"token": ["test-secret-token"]}


@pytest.mark.asyncio
async def test_reset_email_rejects_untrusted_non_https_url(monkeypatch):
    monkeypatch.setenv("LYO_PASSWORD_RESET_URL", "http://malicious.example/auth/reset-password")
    with pytest.raises(RuntimeError, match="HTTPS reset-password"):
        await reset._send_reset_email("learner@example.org", "test-secret-token")
