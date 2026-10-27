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

    def token(uid, email, verified, provider="google.com", name="Test Person"):
        token_name = f"firebase-{uuid.uuid4().hex}"
        claims = {"uid": f"{uid}-{tag}", "email_verified": verified, "firebase": {"sign_in_provider": provider}}
        if email is not None:
            claims["email"] = email
        if name is not None:
            claims["name"] = name
        tokens[token_name] = claims
        return token_name

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

        async def user_by_uid(uid):
            async with sessions() as session:
                return (await session.execute(text(
                    "SELECT id, email, username, first_name, auth_provider, is_verified FROM users "
                    "WHERE firebase_uid = :uid"), {"uid": f"{uid}-{tag}"})).first()

        yield SimpleNamespace(tag=tag, owner_email=owner_email, owner_id=owner_id, token=token,
                              sign_in=sign_in, me=me, row=row, user_by_uid=user_by_uid, sessions=sessions)

    async with sessions() as session:
        ids = (await session.execute(text("SELECT id FROM users WHERE email LIKE :pattern OR firebase_uid LIKE :uid"),
                                     {"pattern": f"%-{tag}@lyoai.app", "uid": f"%-{tag}"})).scalars().all()
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


# Sign in with Apple. The apps use Firebase's Apple provider and send its ID
# token to POST /auth/firebase, the same as Google.

@pytest.mark.asyncio
async def test_apple_with_a_private_relay_email_and_no_name_gets_an_account(fb):
    relay = f"x7k2p9-{fb.tag}@privaterelay.appleid.com"
    signed_in = await fb.sign_in(fb.token("relay", relay, verified=True, provider="apple.com", name=None))
    assert signed_in.status_code == 200, signed_in.text
    body = signed_in.json()
    assert body["is_new_user"] is True
    assert body["user"]["email"] == relay
    assert body["user"]["first_name"] == "User"
    assert not body["user"]["username"].startswith("x7k2p9"), "a relay address's random part makes a poor username"
    stored = await fb.user_by_uid("relay")
    assert stored.auth_provider == "apple.com" and stored.is_verified is True
    assert (await fb.me(body["access_token"])).json()["id"] == stored.id

    again = await fb.sign_in(fb.token("relay", relay, verified=True, provider="apple.com", name=None))
    assert again.status_code == 200 and again.json()["user"]["id"] == stored.id
    assert again.json()["is_new_user"] is False


@pytest.mark.asyncio
async def test_apple_without_any_email_signs_in_by_its_firebase_id(fb):
    signed_in = await fb.sign_in(fb.token("hidden", None, verified=False, provider="apple.com", name=None))
    assert signed_in.status_code == 200, signed_in.text
    user = signed_in.json()["user"]
    assert user["email"] == f"hidden-{fb.tag}@users.lyoai.app"
    assert len(user["username"]) >= 3
    assert (await fb.user_by_uid("hidden")).is_verified is False

    # Later sign-ins (Apple sends the email only the first time) and the
    # Firebase token used directly as the bearer find the same account.
    later = fb.token("hidden", None, verified=False, provider="apple.com", name=None)
    assert (await fb.sign_in(later)).json()["user"]["id"] == user["id"]
    assert (await fb.me(later)).json()["id"] == user["id"]


@pytest.mark.asyncio
async def test_apple_with_a_display_name_keeps_it(fb):
    signed_in = await fb.sign_in(fb.token("named", f"named-{fb.tag}@lyoai.app", verified=True,
                                          provider="apple.com", name="Ada Lovelace"))
    assert signed_in.status_code == 200, signed_in.text
    assert (signed_in.json()["user"]["first_name"], signed_in.json()["user"]["last_name"]) == ("Ada", "Lovelace")


@pytest.mark.asyncio
async def test_apple_with_an_unconfirmed_email_gets_its_own_account_not_the_owners(fb):
    signed_in = await fb.sign_in(fb.token("unconfirmed", fb.owner_email, verified=False, provider="apple.com"))
    assert signed_in.status_code == 200, signed_in.text
    user = signed_in.json()["user"]
    assert user["id"] != fb.owner_id
    assert user["email"] == f"unconfirmed-{fb.tag}@users.lyoai.app", "an unconfirmed email is not claimed"
    assert (await fb.row(fb.owner_email)).firebase_uid is None, "the owner's account stays unlinked"


@pytest.mark.asyncio
async def test_an_old_stand_in_email_is_repaired_on_sign_in(fb):
    # Accounts made without an email used to get <uid>@firebase.local, which
    # fails email validation, so every sign-in to them was a server error.
    async with fb.sessions() as session:
        await session.execute(text(
            "INSERT INTO users (email, username, hashed_password, is_active, is_verified, is_superuser, "
            "firebase_uid, created_at, updated_at) VALUES (:email, :username, 'x', true, false, false, :uid, now(), now())"),
            {"email": f"legacy-{fb.tag}@firebase.local", "username": f"legacy{fb.tag}", "uid": f"legacy-{fb.tag}"})
        await session.commit()
    signed_in = await fb.sign_in(fb.token("legacy", None, verified=False, provider="apple.com", name=None))
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["user"]["email"] == f"legacy-{fb.tag}@users.lyoai.app"
