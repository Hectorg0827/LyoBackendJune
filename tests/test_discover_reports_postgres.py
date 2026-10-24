"""Learners can report a Discover video, on migrated PostgreSQL.

Discover had no way to report a video. A report is now stored for review, a
learner's second report of the same video changes nothing, and the video
leaves the reporter's feed, topics and saved list at once while everyone
else still sees it. Once three different learners have reported it, it is
hidden from everyone but its owner until a moderator decides.

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

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.core.database import get_async_session
from lyo_app.core.exceptions import setup_error_handlers
from lyo_app.routers import clip_media_storage as media
from lyo_app.routers import clips as clips_router
from lyo_app.routers import user_media

POSTGRES_URL = os.getenv("DISCOVER_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="DISCOVER_POSTGRES_URL is not set")
HOST = "http://api.test"
LEARNERS = 5  # the owner, three reporters and one learner who never reports


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
        for index in range(LEARNERS):
            user_ids.append(await session.scalar(text(
                "INSERT INTO users (email, username, hashed_password, is_active, is_verified, "
                "is_superuser, created_at, updated_at) VALUES (:email, :username, 'x', true, true, "
                "false, now(), now()) RETURNING id"),
                {"email": f"report-{tag}-{index}@lyoai.app", "username": f"rep{tag}{index}"}))
        await session.commit()

    app = FastAPI()
    setup_error_handlers(app)
    app.include_router(clips_router.router, prefix="/api/v1")

    async def override_session():
        async with sessions() as session:
            yield session

    async def override_user(x_test_user: int = Header(...)):
        return SimpleNamespace(id=x_test_user, first_name="Test", last_name="Learner",
                               username="learner", avatar_url=None)

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url=HOST) as client:
        async def publish(**overrides):
            name = uuid.uuid4().hex + ".mp4"
            (tmp_path / "clips" / name).write_bytes(b"video-bytes")
            body = {"title": f"Volcanoes {tag}", "subject": f"Earth{tag}", "durationSeconds": 20,
                    "videoUrl": f"{HOST}/api/v1/media/file/clips/{name}"}
            body.update(overrides)
            response = await client.post("/api/v1/clips", json=body, headers=as_user(0))
            assert response.status_code == 200, response.text
            return response.json()["clip"]["id"]

        def as_user(index):
            return {"X-Test-User": str(user_ids[index])}

        async def feed(index):
            response = await client.get("/api/v1/clips/discover", headers=as_user(index),
                                        params={"subject": f"Earth{tag}", "per_page": 100})
            assert response.status_code == 200, response.text
            return [clip["id"] for clip in response.json()["clips"]]

        async def report(index, clip_id, **body):
            return await client.post(f"/api/v1/clips/{clip_id}/report", headers=as_user(index),
                                     json={"reason": "inappropriate", **body})

        yield SimpleNamespace(client=client, sessions=sessions, tag=tag, ids=user_ids,
                              publish=publish, as_user=as_user, feed=feed, report=report)

    async with sessions() as session:
        params = {"ids": user_ids}
        await session.execute(text("DELETE FROM content_reports WHERE reporter_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clip_saves WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clip_likes WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clip_views WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clip_comments WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clips WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), params)
        await session.commit()
    await engine.dispose()


async def _report_rows(pg, clip_id):
    async with pg.sessions() as session:
        return (await session.execute(text(
            "SELECT reporter_id, reason, description, status FROM content_reports "
            "WHERE target_type = 'clip' AND target_id = :id ORDER BY created_at"), {"id": str(clip_id)})).all()


async def _moderation_status(pg, clip_id):
    async with pg.sessions() as session:
        return await session.scalar(text("SELECT moderation_status FROM clips WHERE id = :id"),
                                    {"id": int(clip_id)})


@pytest.mark.asyncio
async def test_a_report_is_stored_for_review(pg):
    clip_id = await pg.publish()
    response = await pg.report(1, clip_id, reason="misinformation", description="  Wrong date  ")
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "reported"
    rows = await _report_rows(pg, clip_id)
    assert [(r.reporter_id, r.reason, r.description, r.status) for r in rows] == [
        (pg.ids[1], "misinformation", "Wrong date", "pending")]
    assert await _moderation_status(pg, clip_id) == "active"


@pytest.mark.asyncio
async def test_reporting_the_same_video_twice_changes_nothing(pg):
    clip_id = await pg.publish()
    assert (await pg.report(1, clip_id)).status_code == 201
    again = await pg.report(1, clip_id, reason="spam")
    assert again.status_code == 200
    assert again.json()["status"] == "already_reported"
    assert len(await _report_rows(pg, clip_id)) == 1


@pytest.mark.asyncio
async def test_reports_that_cannot_apply_are_refused(pg):
    clip_id = await pg.publish()
    private_id = await pg.publish(isPublic=False)
    assert (await pg.report(0, clip_id)).status_code == 400  # one's own video
    assert (await pg.report(0, private_id)).status_code == 400  # one's own, even private
    assert (await pg.report(1, private_id)).status_code == 404  # a video they cannot see
    assert (await pg.report(1, 2_000_000_000)).status_code == 404
    assert (await pg.report(1, clip_id, reason="boring")).status_code == 422
    assert (await pg.report(1, clip_id, description="x" * 1001)).status_code == 422
    assert await _report_rows(pg, clip_id) == []


@pytest.mark.asyncio
async def test_a_reported_video_leaves_only_the_reporters_feed_topics_and_saved_list(pg):
    clip_id = await pg.publish()
    other_id = await pg.publish(title=f"Glaciers {pg.tag}")
    saved = await pg.client.post(f"/api/v1/clips/{clip_id}/save", headers=pg.as_user(1))
    assert saved.status_code == 200, saved.text
    assert (await pg.report(1, clip_id)).status_code == 201

    assert await pg.feed(1) == [other_id]
    assert sorted(await pg.feed(4)) == sorted([clip_id, other_id])

    topics = await pg.client.get("/api/v1/clips/discover/filters", headers=pg.as_user(1))
    counts = {s["name"]: s["count"] for s in topics.json()["subjects"]}
    assert counts[f"Earth{pg.tag}"] == 1
    saved_list = await pg.client.get("/api/v1/clips/saved", headers=pg.as_user(1))
    assert clip_id not in [c["id"] for c in saved_list.json()["clips"]]


@pytest.mark.asyncio
async def test_three_different_reporters_hide_a_video_from_everyone_but_its_owner(pg):
    clip_id = await pg.publish()
    for reporter in (1, 2):
        assert (await pg.report(reporter, clip_id)).status_code == 201
    assert await _moderation_status(pg, clip_id) == "active"
    assert clip_id in await pg.feed(4)

    assert (await pg.report(3, clip_id)).status_code == 201
    assert await _moderation_status(pg, clip_id) == "hidden"
    assert clip_id not in await pg.feed(4)

    topics = await pg.client.get("/api/v1/clips/discover/filters", headers=pg.as_user(4))
    assert f"Earth{pg.tag}" not in [s["name"] for s in topics.json()["subjects"]]
    link = await pg.client.get(f"/api/v1/clips/{clip_id}", headers=pg.as_user(4))
    assert link.status_code == 404
    own = await pg.client.get(f"/api/v1/clips/{clip_id}", headers=pg.as_user(0))
    assert own.status_code == 200
    assert own.json()["clip"]["moderationStatus"] == "hidden"
    mine = await pg.client.get("/api/v1/clips", headers=pg.as_user(0))
    assert clip_id in [c["id"] for c in mine.json()["clips"]]


@pytest.mark.asyncio
async def test_reports_arriving_together_still_hide_at_three_and_count_once(pg):
    clip_id = await pg.publish()
    assert (await pg.report(1, clip_id)).status_code == 201
    together = await asyncio.gather(pg.report(2, clip_id), pg.report(3, clip_id))
    assert [r.status_code for r in together] == [201, 201]
    assert await _moderation_status(pg, clip_id) == "hidden"

    other_id = await pg.publish(title=f"Tides {pg.tag}")
    twice = await asyncio.gather(pg.report(1, other_id), pg.report(1, other_id))
    assert sorted(r.status_code for r in twice) == [200, 201]
    assert len(await _report_rows(pg, other_id)) == 1


@pytest.mark.asyncio
async def test_a_hidden_video_cannot_be_watched_liked_saved_or_commented_on_except_by_its_owner(pg):
    clip_id = await pg.publish()
    comment = await pg.client.post(f"/api/v1/clips/{clip_id}/comments", headers=pg.as_user(4),
                                   json={"content": "Before it was hidden"})
    assert comment.status_code == 201, comment.text
    for reporter in (1, 2, 3):
        assert (await pg.report(reporter, clip_id)).status_code == 201

    base = f"/api/v1/clips/{clip_id}"
    for method, path, body in [
        ("GET", "/comments", None), ("POST", "/comments", {"content": "Still here?"}),
        ("POST", "/like", None), ("POST", "/save", None), ("POST", "/view", None), ("POST", "/share", None),
    ]:
        response = await pg.client.request(method, base + path, headers=pg.as_user(4), json=body)
        assert response.status_code == 404, f"{method} {path}: {response.status_code}"
    owner = await pg.client.get(base + "/comments", headers=pg.as_user(0))
    assert owner.status_code == 200
    assert [c["content"] for c in owner.json()["items"]] == ["Before it was hidden"]


@pytest.mark.asyncio
async def test_someone_elses_private_video_has_no_readable_comments(pg):
    private_id = await pg.publish(isPublic=False)
    response = await pg.client.get(f"/api/v1/clips/{private_id}/comments", headers=pg.as_user(1))
    assert response.status_code == 404


def test_the_community_report_endpoint_sends_videos_to_their_own_endpoint():
    from pydantic import ValidationError
    from lyo_app.community.schemas import ReportCreate

    with pytest.raises(ValidationError, match="/api/v1/clips/"):
        ReportCreate(target_type="clip", target_id="1", reason="spam")
    assert ReportCreate(target_type="post", target_id="1", reason="spam").target_type.value == "post"
