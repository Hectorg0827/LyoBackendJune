"""DELETE /auth/me deletes the account and its data, on migrated PostgreSQL.

The person's rows go (posts, comments, messages, clips, follows, chat,
refresh tokens...), and so do rows that only existed because of theirs
(another person's comment on their post). Other people's own data stays: a
clip they moderated keeps existing with the moderator cleared, a shared
conversation keeps the other side's messages. Every token stops working, the
files they uploaded are deleted, and so is their Firebase account.

Set ``DISCOVER_POSTGRES_URL`` to a database built by ``alembic upgrade head``
to run these tests; they are skipped otherwise.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lyo_app.auth import account_deletion
from lyo_app.auth import routes as auth_routes
from lyo_app.auth.firebase_auth import firebase_auth_service
from lyo_app.auth.jwt_auth import create_access_token, create_refresh_token, get_password_hash
from lyo_app.core.database import _ensure_refresh_tokens_table, get_db
from lyo_app.core.exceptions import setup_error_handlers
from lyo_app.routers import clip_media_storage as media
from lyo_app.routers import user_media

POSTGRES_URL = os.getenv("DISCOVER_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="DISCOVER_POSTGRES_URL is not set")


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)


def _media_url(folder: str) -> tuple[str, str]:
    name = f"{uuid.uuid4().hex}.jpg"
    return f"http://api.test/api/v1/media/file/{folder}/{name}", name


@pytest_asyncio.fixture
async def world(monkeypatch, tmp_path):
    engine = create_async_engine(_async_url(POSTGRES_URL))
    async with engine.begin() as conn:
        await _ensure_refresh_tokens_table(conn)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:10]

    # Uploaded files live on this test's disk.
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    monkeypatch.setattr(media, "settings", SimpleNamespace(storage_provider="local", environment="development"))
    monkeypatch.setattr(user_media, "_media_root", lambda: tmp_path)
    files = {}

    def upload(folder):
        url, name = _media_url(folder)
        path = tmp_path / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"file")
        files[url] = path
        return url

    firebase_deleted = []
    monkeypatch.setattr(firebase_auth_service, "delete_firebase_user", lambda uid: firebase_deleted.append(uid) or True)

    async def sql(statement, **params):
        async with sessions() as session:
            result = await session.execute(text(statement), params)
            await session.commit()
            return result

    async def scalar(statement, **params):
        async with sessions() as session:
            return await session.scalar(text(statement), params)

    async def new_user(name, **extra):
        columns = {"email": f"{name}-{tag}@lyoai.app", "username": f"{name}{tag}",
                   "hashed_password": get_password_hash("Password1!"), **extra}
        names = ", ".join(columns)
        values = ", ".join(f":{key}" for key in columns)
        user_id = (await sql(
            f"INSERT INTO users ({names}, is_active, is_verified, is_superuser, created_at, updated_at) "
            f"VALUES ({values}, true, true, false, now(), now()) RETURNING id", **columns)).scalar_one()
        refresh = create_refresh_token(user_id=str(user_id))
        await sql("INSERT INTO refresh_tokens (token, user_id, is_revoked, expires_at, created_at) "
                  "VALUES (:token, :user_id, false, :expires, now())",
                  token=refresh, user_id=user_id, expires=datetime.utcnow() + timedelta(days=7))
        return SimpleNamespace(id=user_id, access=create_access_token(user_id=str(user_id)), refresh=refresh)

    alice = await new_user("alice", avatar_url=upload("avatars"), firebase_uid=f"apple-{tag}")
    bob = await new_user("bob")

    # Alice's post, with Bob's comment on it; Bob's post, with Alice's comment.
    async def post(author):
        return (await sql("INSERT INTO posts (post_type, author_id, content, is_public, is_pinned, created_at, updated_at) "
                          "VALUES ('TEXT', :author, 'hello', true, false, now(), now()) RETURNING id",
                          author=author)).scalar_one()

    async def comment(post_id, author):
        return (await sql("INSERT INTO comments (content, post_id, author_id, created_at, updated_at) "
                          "VALUES ('nice', :post, :author, now(), now()) RETURNING id",
                          post=post_id, author=author)).scalar_one()

    alice_post, bob_post = await post(alice.id), await post(bob.id)
    bob_on_alice = await comment(alice_post, bob.id)
    alice_on_bob = await comment(bob_post, alice.id)
    await sql("INSERT INTO user_follows (follower_id, following_id, created_at) VALUES (:a, :b, now()), (:b, :a, now())",
              a=alice.id, b=bob.id)

    # Clips: Alice's own, and Bob's that Alice moderated and watched.
    alice_clip_url = upload("clips")
    alice_clip = (await sql("INSERT INTO clips (user_id, title, video_url) VALUES (:u, 'mine', :url) RETURNING id",
                            u=alice.id, url=alice_clip_url)).scalar_one()
    bob_clip = (await sql("INSERT INTO clips (user_id, title, video_url, moderated_by_id) "
                          "VALUES (:u, 'his', 'https://example.com/v.mp4', :mod) RETURNING id",
                          u=bob.id, mod=alice.id)).scalar_one()
    await sql("INSERT INTO clip_views (clip_id, user_id) VALUES (:c, :u)", c=bob_clip, u=alice.id)

    # A direct conversation between them.
    conversation = (await sql("INSERT INTO conversations (type, created_at) VALUES ('direct', now()) RETURNING id")).scalar_one()
    await sql("INSERT INTO conversation_participants (conversation_id, user_id) VALUES (:c, :a), (:c, :b)",
              c=conversation, a=alice.id, b=bob.id)
    await sql("INSERT INTO messages (conversation_id, sender_id, content) VALUES (:c, :a, 'hi bob'), (:c, :b, 'hi alice')",
              c=conversation, a=alice.id, b=bob.id)

    # AI chat stores the user id as text, with no foreign key, and keeps
    # attachments as links in the message.
    chat_attachment = upload("chat")
    chat_id = f"chat-{tag}"
    await sql("INSERT INTO chat_conversations (id, user_id, session_id) VALUES (:id, :u, :s)",
              id=chat_id, u=str(alice.id), s=f"s-{tag}")
    await sql("INSERT INTO chat_messages (id, conversation_id, role, content) VALUES (:id, :c, 'user', :content)",
              id=f"m-{tag}", c=chat_id, content=f"What is this? ![notes]({chat_attachment})")

    app = FastAPI()
    setup_error_handlers(app)
    app.include_router(auth_routes.router, prefix="/auth")

    async def override_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as client:
        yield SimpleNamespace(
            client=client, alice=alice, bob=bob, scalar=scalar, sql=sql, files=files,
            firebase_deleted=firebase_deleted, tag=tag, alice_post=alice_post, bob_post=bob_post,
            bob_on_alice=bob_on_alice, alice_on_bob=alice_on_bob, alice_clip=alice_clip,
            bob_clip=bob_clip, conversation=conversation, chat_id=chat_id,
        )

    async with sessions() as session:
        for user in (alice, bob):
            await account_deletion.delete_account(session, user.id)
    await sql("DELETE FROM conversations WHERE id = :c", c=conversation)
    await engine.dispose()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_deleting_an_account_removes_its_data_and_keeps_everyone_elses(world):
    w = world
    response = await w.client.delete("/auth/me", headers=bearer(w.alice.access))
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": True}

    count = w.scalar
    assert await count("SELECT count(*) FROM users WHERE id = :u", u=w.alice.id) == 0
    assert await count("SELECT count(*) FROM refresh_tokens WHERE user_id = :u", u=w.alice.id) == 0
    assert await count("SELECT count(*) FROM posts WHERE author_id = :u", u=w.alice.id) == 0
    assert await count("SELECT count(*) FROM comments WHERE id IN (:a, :b)", a=w.bob_on_alice, b=w.alice_on_bob) == 0, \
        "her comments, and comments on her posts, go with her"
    assert await count("SELECT count(*) FROM user_follows WHERE :u IN (follower_id, following_id)", u=w.alice.id) == 0
    assert await count("SELECT count(*) FROM clips WHERE id = :c", c=w.alice_clip) == 0
    assert await count("SELECT count(*) FROM clip_views WHERE clip_id = :c", c=w.bob_clip) == 0
    assert await count("SELECT count(*) FROM messages WHERE sender_id = :u", u=w.alice.id) == 0
    assert await count("SELECT count(*) FROM conversation_participants WHERE user_id = :u", u=w.alice.id) == 0
    assert await count("SELECT count(*) FROM chat_conversations WHERE id = :c", c=w.chat_id) == 0
    assert await count("SELECT count(*) FROM chat_messages WHERE conversation_id = :c", c=w.chat_id) == 0

    # Bob keeps his account, post, clip and his side of the conversation.
    assert await count("SELECT count(*) FROM users WHERE id = :u", u=w.bob.id) == 1
    assert await count("SELECT count(*) FROM posts WHERE id = :p", p=w.bob_post) == 1
    assert await count("SELECT count(*) FROM clips WHERE id = :c AND moderated_by_id IS NULL", c=w.bob_clip) == 1
    assert await count("SELECT count(*) FROM messages WHERE conversation_id = :c AND sender_id = :u",
                       c=w.conversation, u=w.bob.id) == 1

    # Her uploaded files (avatar, clip, chat attachment) are deleted.
    assert w.files and not any(path.exists() for path in w.files.values())
    assert w.firebase_deleted == [f"apple-{w.tag}"]

    # Every session is over: the access token, the refresh token, a retry.
    assert (await w.client.get("/auth/me", headers=bearer(w.alice.access))).status_code == 401
    assert (await w.client.post("/auth/refresh", json={"refresh_token": w.alice.refresh})).status_code == 401
    assert (await w.client.delete("/auth/me", headers=bearer(w.alice.access))).status_code == 401
    assert (await w.client.get("/auth/me", headers=bearer(w.bob.access))).status_code == 200


@pytest.mark.asyncio
async def test_a_failed_deletion_changes_nothing(world):
    w = world

    collect = account_deletion._Purge._collect_media
    calls = []

    def fail_late(purge, name, cond):
        calls.append(name)
        if len(calls) == 12:
            assert purge.deleted, "the purge should have deleted rows by now"
            raise RuntimeError("reading row data failed")
        return collect(purge, name, cond)

    # Fails after the purge has already deleted some of her rows.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(account_deletion._Purge, "_collect_media", fail_late)
        response = await w.client.delete("/auth/me", headers=bearer(w.alice.access))
    assert response.status_code == 500
    assert await w.scalar("SELECT count(*) FROM users WHERE id = :u", u=w.alice.id) == 1
    assert await w.scalar("SELECT count(*) FROM comments WHERE id IN (:a, :b)", a=w.bob_on_alice, b=w.alice_on_bob) == 2
    assert await w.scalar("SELECT count(*) FROM refresh_tokens WHERE user_id = :u", u=w.alice.id) == 1
    assert all(path.exists() for path in w.files.values())
    assert not w.firebase_deleted
    assert (await w.client.get("/auth/me", headers=bearer(w.alice.access))).status_code == 200


@pytest.mark.asyncio
async def test_deletion_needs_a_signed_in_user(world):
    assert (await world.client.delete("/auth/me")).status_code in (401, 403)
    assert (await world.client.delete("/auth/me", headers=bearer("not-a-token"))).status_code == 401
