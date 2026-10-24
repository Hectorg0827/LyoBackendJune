"""Blocking someone hides them from Discover both ways, on migrated PostgreSQL.

Community already stored blocks (/api/v1/community/blocks), but Discover
ignored them. Now neither side of a block sees the other's clips or comments
in the feed, its topics, saved lists or a shared link, nor can like, save,
comment on or report them. Unblocking brings everything back. Blocking is
idempotent, so a second tap or two simultaneous requests are not errors.

Set ``DISCOVER_POSTGRES_URL`` to a database built by ``alembic upgrade head``
to run these; they are skipped otherwise.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lyo_app.auth import routes as auth_routes
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.community.routes import router as community_router
from lyo_app.core.database import get_async_session, get_db
from lyo_app.core.exceptions import setup_error_handlers
from lyo_app.routers import clip_media_storage as media
from lyo_app.routers import clips as clips_router
from lyo_app.routers import user_media

POSTGRES_URL = os.getenv("DISCOVER_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="DISCOVER_POSTGRES_URL is not set")
HOST = "http://api.test"
OWNER, VIEWER, BYSTANDER = 0, 1, 2


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest_asyncio.fixture
async def pg(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "_provider", lambda: None)
    monkeypatch.setattr(clips_router, "_media_root", lambda: tmp_path)
    monkeypatch.setattr(user_media, "_media_root", lambda: tmp_path)
    (tmp_path / "clips").mkdir()

    engine = create_async_engine(_async_url(POSTGRES_URL))
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:10]
    user_ids = []
    async with sessions() as session:
        for index in range(3):
            user_ids.append(await session.scalar(text(
                "INSERT INTO users (email, username, hashed_password, is_active, is_verified, "
                "is_superuser, created_at, updated_at) VALUES (:email, :username, 'x', true, true, "
                "false, now(), now()) RETURNING id"),
                {"email": f"block-{tag}-{index}@lyoai.app", "username": f"blk{tag}{index}"}))
        await session.commit()

    app = FastAPI()
    setup_error_handlers(app)
    app.include_router(clips_router.router, prefix="/api/v1")
    app.include_router(community_router, prefix="/api/v1/community")

    async def override_session():
        async with sessions() as session:
            yield session

    async def override_user(x_test_user: int = Header(...)):
        return SimpleNamespace(id=x_test_user, first_name="Test", last_name="Learner",
                               username="learner", avatar_url=None)

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_db] = override_session
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[auth_routes.get_current_user] = override_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url=HOST) as client:
        def as_user(index):
            return {"X-Test-User": str(user_ids[index])}

        async def publish(index):
            name = uuid.uuid4().hex + ".mp4"
            (tmp_path / "clips" / name).write_bytes(b"video-bytes")
            response = await client.post("/api/v1/clips", headers=as_user(index), json={
                "title": f"Tides {tag}", "subject": f"Ocean{tag}", "durationSeconds": 20,
                "videoUrl": f"{HOST}/api/v1/media/file/clips/{name}"})
            assert response.status_code == 200, response.text
            return response.json()["clip"]["id"]

        async def feed(index):
            response = await client.get("/api/v1/clips/discover", headers=as_user(index),
                                        params={"subject": f"Ocean{tag}", "per_page": 100})
            assert response.status_code == 200, response.text
            return {clip["id"] for clip in response.json()["clips"]}

        async def subjects(index):
            response = await client.get("/api/v1/clips/discover/filters", headers=as_user(index))
            assert response.status_code == 200, response.text
            return {s["name"]: s["count"] for s in response.json()["subjects"]}.get(f"Ocean{tag}", 0)

        async def block(index, other):
            return await client.post("/api/v1/community/blocks", headers=as_user(index),
                                     json={"user_id": user_ids[other]})

        async def unblock(index, other):
            return await client.delete(f"/api/v1/community/blocks/{user_ids[other]}", headers=as_user(index))

        yield SimpleNamespace(client=client, sessions=sessions, ids=user_ids, as_user=as_user,
                              publish=publish, feed=feed, subjects=subjects, block=block, unblock=unblock)

    async with sessions() as session:
        params = {"ids": user_ids}
        await session.execute(text(
            "DELETE FROM user_blocks WHERE blocker_id = ANY(:ids) OR blocked_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM content_reports WHERE reporter_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clip_saves WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clip_likes WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clip_views WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clip_comments WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clips WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), params)
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_block_hides_each_side_from_the_other_until_unblocked(pg):
    owners_clip = await pg.publish(OWNER)
    viewers_clip = await pg.publish(VIEWER)
    saved = await pg.client.post(f"/api/v1/clips/{owners_clip}/save", headers=pg.as_user(VIEWER))
    assert saved.status_code == 200, saved.text
    assert await pg.feed(VIEWER) >= {owners_clip, viewers_clip}

    assert (await pg.block(VIEWER, OWNER)).status_code == 201

    assert owners_clip not in await pg.feed(VIEWER), "the blocker still sees the blocked owner's clip"
    assert viewers_clip not in await pg.feed(OWNER), "the blocked owner still sees the blocker's clip"
    assert await pg.feed(BYSTANDER) >= {owners_clip, viewers_clip}, "a block must not touch anyone else"
    assert await pg.subjects(VIEWER) == 1, "the topic count still counts the blocked owner's clip"
    saved_list = await pg.client.get("/api/v1/clips/saved", headers=pg.as_user(VIEWER))
    assert owners_clip not in {clip["id"] for clip in saved_list.json()["clips"]}
    for viewer, clip_id in ((VIEWER, owners_clip), (OWNER, viewers_clip)):
        opened = await pg.client.get(f"/api/v1/clips/{clip_id}", headers=pg.as_user(viewer))
        assert opened.status_code == 404, opened.text
    own = await pg.client.get(f"/api/v1/clips/{owners_clip}", headers=pg.as_user(OWNER))
    assert own.status_code == 200, "an owner always sees their own clip"

    assert (await pg.unblock(VIEWER, OWNER)).status_code == 204
    assert await pg.feed(VIEWER) >= {owners_clip, viewers_clip}
    assert await pg.feed(OWNER) >= {owners_clip, viewers_clip}


@pytest.mark.asyncio
async def test_nobody_can_act_on_a_clip_across_a_block(pg):
    clip_id = await pg.publish(OWNER)
    assert (await pg.block(OWNER, VIEWER)).status_code == 201
    actions = [
        ("post", f"/api/v1/clips/{clip_id}/like", None),
        ("post", f"/api/v1/clips/{clip_id}/save", None),
        ("post", f"/api/v1/clips/{clip_id}/share", None),
        ("post", f"/api/v1/clips/{clip_id}/comments", {"content": "hello"}),
        ("get", f"/api/v1/clips/{clip_id}/comments", None),
        ("post", f"/api/v1/clips/{clip_id}/report", {"reason": "spam"}),
    ]
    for method, path, body in actions:
        kwargs = {"json": body} if body is not None else {}
        response = await getattr(pg.client, method)(path, headers=pg.as_user(VIEWER), **kwargs)
        assert response.status_code == 404, f"{method.upper()} {path} -> {response.status_code}"
        allowed = await getattr(pg.client, method)(path, headers=pg.as_user(BYSTANDER), **kwargs)
        assert allowed.status_code in (200, 201), f"{method.upper()} {path} for a bystander -> {allowed.text}"


@pytest.mark.asyncio
async def test_comments_from_someone_blocked_are_left_out(pg):
    clip_id = await pg.publish(BYSTANDER)
    for index, words in ((OWNER, "from the owner"), (VIEWER, "from the viewer")):
        made = await pg.client.post(f"/api/v1/clips/{clip_id}/comments", headers=pg.as_user(index),
                                    json={"content": words})
        assert made.status_code == 201, made.text
    assert (await pg.block(VIEWER, OWNER)).status_code == 201

    async def comments(index):
        response = await pg.client.get(f"/api/v1/clips/{clip_id}/comments", headers=pg.as_user(index))
        assert response.status_code == 200, response.text
        body = response.json()
        return {item["content"] for item in body["items"]}, body["total_count"]

    assert await comments(VIEWER) == ({"from the viewer"}, 1)
    assert await comments(OWNER) == ({"from the owner"}, 1)
    assert await comments(BYSTANDER) == ({"from the owner", "from the viewer"}, 2)


@pytest.mark.asyncio
async def test_blocking_is_idempotent_and_refuses_nobody_or_yourself(pg):
    first, second = await asyncio.gather(pg.block(VIEWER, OWNER), pg.block(VIEWER, OWNER))
    assert (first.status_code, second.status_code) == (201, 201), (first.text, second.text)
    assert first.json()["id"] == second.json()["id"]
    again = await pg.block(VIEWER, OWNER)
    assert again.status_code == 201 and again.json()["id"] == first.json()["id"]
    async with pg.sessions() as session:
        rows = await session.scalar(text(
            "SELECT count(*) FROM user_blocks WHERE blocker_id = :a AND blocked_id = :b"),
            {"a": pg.ids[VIEWER], "b": pg.ids[OWNER]})
    assert rows == 1

    listed = await pg.client.get("/api/v1/community/blocks", headers=pg.as_user(VIEWER))
    assert [entry["user_id"] for entry in listed.json()] == [pg.ids[OWNER]]

    nobody = await pg.client.post("/api/v1/community/blocks", headers=pg.as_user(VIEWER),
                                  json={"user_id": 2_000_000_000})
    assert nobody.status_code == 404, nobody.text
    yourself = await pg.block(VIEWER, VIEWER)
    assert yourself.status_code == 400, yourself.text
