"""Resetting a forgotten password by email, on migrated PostgreSQL.

There was no way back into an account after forgetting its password. Now a
learner asks for a link by email, the link works once for an hour, and using
it sets the new password, ends every other open link and signs out the
account's other sessions. The request answers the same whether or not the
account exists.

Set ``DISCOVER_POSTGRES_URL`` to a database built by ``alembic upgrade head``
to run the database tests; they are skipped otherwise.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lyo_app.auth import password_reset
from lyo_app.auth import routes as auth_routes
from lyo_app.auth.jwt_auth import get_password_hash
from lyo_app.core.database import _ensure_refresh_tokens_table, get_db
from lyo_app.core.exceptions import setup_error_handlers

POSTGRES_URL = os.getenv("DISCOVER_POSTGRES_URL")
needs_db = pytest.mark.skipif(not POSTGRES_URL, reason="DISCOVER_POSTGRES_URL is not set")
OLD, NEW = "OldPassword1!", "BrandNew-Pass7"


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest_asyncio.fixture
async def pg(monkeypatch):
    engine = create_async_engine(_async_url(POSTGRES_URL))
    # The server creates refresh_tokens at startup, outside the migrations.
    async with engine.begin() as conn:
        await _ensure_refresh_tokens_table(conn)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:10]
    emails = {"owner": f"owner-{tag}@lyoai.app", "other": f"other-{tag}@lyoai.app"}
    ids = {}
    async with sessions() as session:
        for key, email in emails.items():
            ids[key] = await session.scalar(text(
                "INSERT INTO users (email, username, hashed_password, is_active, is_verified, "
                "is_superuser, created_at, updated_at) VALUES (:email, :username, :hashed, true, true, "
                "false, now(), now()) RETURNING id"),
                {"email": email, "username": f"{key}{tag}", "hashed": get_password_hash(OLD)})
        await session.commit()

    sent = []

    async def fake_send(to, link):
        sent.append(SimpleNamespace(to=to, link=link, token=parse_qs(urlsplit(link).query)["token"][0]))
        return True

    monkeypatch.setattr(password_reset, "send_reset_email", fake_send)

    app = FastAPI()
    setup_error_handlers(app)
    app.include_router(auth_routes.router, prefix="/auth")

    async def override_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as client:
        async def ask(email):
            response = await client.post("/auth/password-reset/request", json={"email": email})
            assert response.status_code == 200, response.text
            return response.json()["message"]

        async def confirm(token, password=NEW):
            return await client.post("/auth/password-reset/confirm",
                                     json={"token": token, "new_password": password})

        async def login(email, password):
            return await client.post("/auth/login", json={"email": email, "password": password})

        yield SimpleNamespace(client=client, sessions=sessions, emails=emails, ids=ids, sent=sent,
                              ask=ask, confirm=confirm, login=login)

    async with sessions() as session:
        params = {"ids": list(ids.values())}
        await session.execute(text("DELETE FROM password_resets WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM refresh_tokens WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), params)
        await session.commit()
    await engine.dispose()


@needs_db
@pytest.mark.asyncio
async def test_a_link_goes_only_to_a_real_account_and_only_its_hash_is_stored(pg):
    known = await pg.ask(pg.emails["owner"])
    unknown = await pg.ask(f"nobody-{uuid.uuid4().hex}@lyoai.app")
    assert known == unknown, "the answer must not reveal who has an account"
    assert len(pg.sent) == 1 and pg.sent[0].to == pg.emails["owner"]
    assert pg.sent[0].link.startswith("https://www.lyoai.app/auth/reset-password?token=")
    async with pg.sessions() as session:
        stored = (await session.execute(text(
            "SELECT token_hash, expires_at - created_at FROM password_resets WHERE user_id = :id"),
            {"id": pg.ids["owner"]})).one()
    assert stored[0] != pg.sent[0].token and len(stored[0]) == 64, "only the token's hash is kept"
    assert timedelta(minutes=59) < stored[1] <= timedelta(minutes=61)


@needs_db
@pytest.mark.asyncio
async def test_a_link_sets_the_password_once_and_signs_out_other_sessions(pg):
    session = await pg.login(pg.emails["owner"], OLD)
    assert session.status_code == 200, session.text
    before = await pg.client.post("/auth/refresh", json={"refresh_token": session.json()["refresh_token"]})
    assert before.status_code == 200, f"the session should refresh before the reset: {before.text}"
    refresh = before.json()["refresh_token"]
    await pg.ask(pg.emails["owner"])
    await pg.ask(pg.emails["owner"])
    first, second = pg.sent[0].token, pg.sent[1].token

    done = await pg.confirm(second)
    assert done.status_code == 200, done.text
    assert (await pg.login(pg.emails["owner"], NEW)).status_code == 200
    assert (await pg.login(pg.emails["owner"], OLD)).status_code == 401
    assert (await pg.login(pg.emails["other"], OLD)).status_code == 200, "nobody else's password changes"

    assert (await pg.confirm(second)).status_code == 400, "a link works once"
    assert (await pg.confirm(first)).status_code == 400, "using one link ends the others"
    refreshed = await pg.client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code in (400, 401), f"an old session kept working: {refreshed.status_code}"


@needs_db
@pytest.mark.asyncio
async def test_expired_unknown_and_weak_are_refused(pg):
    await pg.ask(pg.emails["owner"])
    token = pg.sent[0].token
    assert (await pg.confirm(token, "short")).status_code == 400
    assert (await pg.confirm("x" * 43)).status_code == 400
    async with pg.sessions() as session:
        await session.execute(text("UPDATE password_resets SET expires_at = now() - interval '1 minute' "
                                   "WHERE user_id = :id"), {"id": pg.ids["owner"]})
        await session.commit()
    assert (await pg.confirm(token)).status_code == 400, "an expired link must not work"
    assert (await pg.login(pg.emails["owner"], OLD)).status_code == 200


@needs_db
@pytest.mark.asyncio
async def test_three_links_an_hour_and_email_case_is_forgiven(pg):
    for _ in range(4):
        await pg.ask(pg.emails["owner"].upper())
    assert len(pg.sent) == 3, "a fourth link within the hour must not be sent"
    assert all(item.to == pg.emails["owner"] for item in pg.sent), "the link goes to the stored address"


@needs_db
@pytest.mark.asyncio
async def test_two_uses_of_one_link_at_once_only_one_counts(pg):
    await pg.ask(pg.emails["owner"])
    token = pg.sent[0].token
    results = await asyncio.gather(pg.confirm(token, NEW), pg.confirm(token, "Another-Pass9"))
    assert sorted(r.status_code for r in results) == [200, 400]


def _resend(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(password_reset.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.asyncio
async def test_the_email_goes_through_resend_with_the_configured_sender(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "email_1"})

    _resend(monkeypatch, handler)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    assert await password_reset.send_reset_email("a@b.co", "https://www.lyoai.app/auth/reset-password?token=t")
    request = seen[0]
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_test"
    import json
    body = json.loads(request.content)
    assert body["from"] == "Lyo <onboarding@resend.dev>" and body["to"] == ["a@b.co"]
    assert "token=t" in body["text"] and "token=t" in body["html"]

    monkeypatch.setenv("EMAIL_FROM", "Lyo <no-reply@lyoai.app>")
    await password_reset.send_reset_email("a@b.co", "https://x")
    assert json.loads(seen[1].content)["from"] == "Lyo <no-reply@lyoai.app>"


@pytest.mark.asyncio
async def test_no_key_or_a_refusal_sends_nothing_and_says_so(monkeypatch):
    calls = []
    _resend(monkeypatch, lambda request: calls.append(request) or httpx.Response(403, json={"message": "no"}))
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert not await password_reset.send_reset_email("a@b.co", "https://x")
    assert calls == [], "without a key nothing is sent"
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    assert not await password_reset.send_reset_email("a@b.co", "https://x")
    assert len(calls) == 1
