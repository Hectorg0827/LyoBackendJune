"""Signing in with Google or Apple (through Firebase), on migrated PostgreSQL.

A Firebase sign-in used to open whichever account had the token's email,
even when the email was not confirmed. Anyone can make a Firebase account
with someone else's email, so that was a way into their account. Now an
unconfirmed email neither opens nor creates an account; Google and Apple
always confirm the email, so their sign-ins work as before.

Set ``DISCOVER_POSTGRES_URL`` to a database built by ``alembic upgrade head``
to run these tests; they are skipped otherwise.
"""
from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lyo_app.auth import routes as auth_routes
from lyo_app.auth.firebase_auth import firebase_auth_service
from lyo_app.auth.jwt_auth import get_password_hash
from lyo_app.core.database import _ensure_refresh_tokens_table, get_db
from lyo_app.core.exceptions import setup_error_handlers

POSTGRES_URL = os.getenv("DISCOVER_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="DISCOVER_POSTGRES_URL is not set")


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest_asyncio.fixture
async def fb(monkeypatch):
    engine = create_async_engine(_async_url(POSTGRES_URL))
    async with engine.begin() as conn:
        await _ensure_refresh_tokens_table(conn)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:10]
    owner_email = f"owner-{tag}@lyoai.app"
    async with sessions() as session:
        owner_id = await session.scalar(text(
            "INSERT INTO users (email, username, hashed_password, is_active, is_verified, "
            "is_superuser, created_at, updated_at) VALUES (:email, :username, :hashed, true, true, "
            "false, now(), now()) RETURNING id"),
            {"email": owner_email, "username": f"owner{tag}", "hashed": get_password_hash("OwnerPass1!")})
        await session.commit()

    # Each test names the Firebase tokens it uses; the token text maps to its claims.
    tokens = {}
    monkeypatch.setattr(firebase_auth_service, "is_available", lambda: True)

    async def verify(id_token):
        if id_token not in tokens:
            raise ValueError("Token verification failed")
        return tokens[id_token]

    monkeypatch.setattr(firebase_auth_service, "verify_firebase_token", verify)

    def token(uid, email, verified, provider="google.com"):
        name = f"firebase-{uuid.uuid4().hex}"
        tokens[name] = {"uid": f"{uid}-{tag}", "email": email, "email_verified": verified,
                        "name": "Test Person", "firebase": {"sign_in_provider": provider}}
        return name

    app = FastAPI()
    setup_error_handlers(app)
    app.include_router(auth_routes.router, prefix="/auth")

    async def override_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    async def row(email):
        async with sessions() as session:
            return (await session.execute(text(
                "SELECT id, firebase_uid FROM users WHERE email = :email"), {"email": email})).first()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as client:
        async def sign_in(id_token):
            return await client.post("/auth/firebase", json={"id_token": id_token})

        async def me(bearer):
            return await client.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"})

        yield SimpleNamespace(tag=tag, owner_email=owner_email, owner_id=owner_id, token=token,
                              sign_in=sign_in, me=me, row=row)

    async with sessions() as session:
        ids = (await session.execute(text("SELECT id FROM users WHERE email LIKE :pattern"),
                                     {"pattern": f"%-{tag}@lyoai.app"})).scalars().all()
        await session.execute(text("DELETE FROM refresh_tokens WHERE user_id = ANY(:ids)"), {"ids": list(ids)})
        await session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": list(ids)})
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_an_unconfirmed_email_does_not_open_its_account(fb):
    stranger = fb.token("stranger", fb.owner_email, verified=False, provider="password")
    signed_in = await fb.sign_in(stranger)
    assert signed_in.status_code == 401, signed_in.text
    assert (await fb.me(stranger)).status_code == 401, "a Firebase token sent as the sign-in also counts"
    assert (await fb.row(fb.owner_email)).firebase_uid is None, "the account must not be linked to it"


@pytest.mark.asyncio
async def test_a_confirmed_email_signs_in_to_its_account(fb):
    google = fb.token("google", fb.owner_email, verified=True)
    signed_in = await fb.sign_in(google)
    assert signed_in.status_code == 200, signed_in.text
    body = signed_in.json()
    assert body["user"]["id"] == fb.owner_id and body["is_new_user"] is False
    assert (await fb.me(body["access_token"])).json()["id"] == fb.owner_id
    assert (await fb.row(fb.owner_email)).firebase_uid == f"google-{fb.tag}"


@pytest.mark.asyncio
async def test_a_new_google_or_apple_person_gets_an_account(fb):
    email = f"new-{fb.tag}@lyoai.app"
    signed_in = await fb.sign_in(fb.token("apple", email, verified=True, provider="apple.com"))
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["is_new_user"] is True
    assert (await fb.row(email)).firebase_uid == f"apple-{fb.tag}"


@pytest.mark.asyncio
async def test_an_unconfirmed_email_creates_no_account(fb):
    email = f"taken-{fb.tag}@lyoai.app"
    first = fb.token("squatter", email, verified=False, provider="password")
    assert (await fb.sign_in(first)).status_code == 401
    second = fb.token("squatter2", email, verified=False, provider="password")
    assert (await fb.me(second)).status_code == 401
    assert await fb.row(email) is None, "nobody can claim an email they have not confirmed"


@pytest.mark.asyncio
async def test_an_account_already_linked_still_signs_in_by_its_firebase_id(fb):
    email = f"linked-{fb.tag}@lyoai.app"
    assert (await fb.sign_in(fb.token("linked", email, verified=True))).status_code == 200
    # The same Firebase account, now reporting its email as unconfirmed.
    again = fb.token("linked", email, verified=False)
    signed_in = await fb.sign_in(again)
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["user"]["id"] == (await fb.row(email)).id
    assert (await fb.me(again)).status_code == 200
