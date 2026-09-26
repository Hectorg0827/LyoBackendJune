"""Direct messages against a real, migrated PostgreSQL database.

The migrations created ``messages.metadata`` while the model maps
``message_metadata``, so every query that loaded a Message failed on a
database built by ``alembic upgrade head`` and the web Messages page showed
an empty list. SQLite test databases are built from the models, so the
in-memory suite never saw it.

Set ``COMMUNITY_POSTGRES_URL`` (the CI service database after
``alembic upgrade head``) to run these; they are skipped otherwise.
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.core.database import get_db
from lyo_app.routers.messaging import router as messaging_router

POSTGRES_URL = os.getenv("COMMUNITY_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="COMMUNITY_POSTGRES_URL is not set")


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest_asyncio.fixture
async def pg():
    engine = create_async_engine(_async_url(POSTGRES_URL))
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:10]
    user_ids = []
    async with sessions() as session:
        for index in range(2):
            user_ids.append(
                await session.scalar(
                    text(
                        "INSERT INTO users (email, username, hashed_password, is_active, "
                        "is_verified, is_superuser, created_at, updated_at) VALUES "
                        "(:email, :username, 'x', true, true, false, now(), now()) RETURNING id"
                    ),
                    {"email": f"dm-{tag}-{index}@lyoai.app", "username": f"dm{tag}{index}"},
                )
            )
        await session.commit()

    app = FastAPI()
    app.include_router(messaging_router)

    async def override_get_db():
        async with sessions() as session:
            yield session

    async def override_current_user(x_test_user: int = Header(...)):
        return SimpleNamespace(id=x_test_user)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://pg") as client:
        yield SimpleNamespace(
            client=client,
            a={"X-Test-User": str(user_ids[0])},
            b={"X-Test-User": str(user_ids[1])},
            ids=user_ids,
        )

    async with sessions() as session:
        params = {"ids": user_ids}
        conversation_ids = [
            row[0]
            for row in (
                await session.execute(
                    text("SELECT DISTINCT conversation_id FROM conversation_participants WHERE user_id = ANY(:ids)"),
                    params,
                )
            ).all()
        ]
        if conversation_ids:
            owned = {"conv": conversation_ids}
            for statement in (
                "DELETE FROM message_read_receipts WHERE message_id IN "
                "(SELECT id FROM messages WHERE conversation_id = ANY(:conv))",
                "DELETE FROM messages WHERE conversation_id = ANY(:conv)",
                "DELETE FROM conversation_participants WHERE conversation_id = ANY(:conv)",
                "DELETE FROM conversations WHERE id = ANY(:conv)",
            ):
                await session.execute(text(statement), owned)
        await session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), params)
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_migrated_messages_table_has_the_column_the_model_reads(pg):
    engine = create_async_engine(_async_url(POSTGRES_URL))
    async with engine.connect() as connection:
        columns = {
            row[0]
            for row in (
                await connection.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = 'messages'")
                )
            ).all()
        }
    await engine.dispose()
    assert "message_metadata" in columns


@pytest.mark.asyncio
async def test_direct_messages_round_trip_on_postgres(pg):
    # Someone starts a conversation and sends a message.
    created = await pg.client.post(
        "/messages/conversations", json={"participant_ids": [pg.ids[1]]}, headers=pg.a
    )
    assert created.status_code in (200, 201), created.text
    conversation_id = created.json()["id"]
    sent = await pg.client.post(
        f"/messages/conversations/{conversation_id}/messages",
        json={"content": "Are you coming to the lab?"},
        headers=pg.a,
    )
    assert sent.status_code == 201, sent.text

    # The other person sees it, unread, in their list.
    listed = await pg.client.get("/messages/conversations", headers=pg.b)
    assert listed.status_code == 200, listed.text
    conversation = next(c for c in listed.json()["conversations"] if c["id"] == conversation_id)
    assert conversation["unread_count"] == 1
    assert conversation["last_message"]["content"] == "Are you coming to the lab?"

    # Opening it shows the message; reading it clears the count.
    opened = await pg.client.get(f"/messages/conversations/{conversation_id}", headers=pg.b)
    assert opened.status_code == 200, opened.text
    assert [m["content"] for m in opened.json()["messages"]] == ["Are you coming to the lab?"]
    read = await pg.client.post(f"/messages/conversations/{conversation_id}/read", headers=pg.b)
    assert read.status_code == 200, read.text
    listed = await pg.client.get("/messages/conversations", headers=pg.b)
    conversation = next(c for c in listed.json()["conversations"] if c["id"] == conversation_id)
    assert conversation["unread_count"] == 0
