"""Discover publishes and serves only videos that exist, on migrated PostgreSQL.

Two legacy clips stayed in the feed after a redeploy erased their videos, so
Discover offered reels that could only fail. A clip now records whether its
video is in storage; publishing checks before it creates the row, and the
feed, topic counts, saved list and shared links serve only "ready" clips.

Set ``DISCOVER_POSTGRES_URL`` to a database built by ``alembic upgrade head``
to run these; they are skipped otherwise.
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
from lyo_app.core.database import get_async_session
from lyo_app.core.exceptions import setup_error_handlers
from lyo_app.routers import clip_media_storage as media
from lyo_app.routers import clips as clips_router
from lyo_app.routers import user_media

POSTGRES_URL = os.getenv("DISCOVER_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="DISCOVER_POSTGRES_URL is not set")
HOST = "http://api.test"


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest_asyncio.fixture
async def pg(monkeypatch, tmp_path):
    # Uploads land in this folder, as they do with the explicit local option.
    monkeypatch.setattr(media, "_provider", lambda: None)
    monkeypatch.setattr(clips_router, "_media_root", lambda: tmp_path)
    monkeypatch.setattr(user_media, "_media_root", lambda: tmp_path)
    (tmp_path / "clips").mkdir()
    (tmp_path / "clip_thumbnails").mkdir()

    engine = create_async_engine(_async_url(POSTGRES_URL))
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:10]
    user_ids = []
    async with sessions() as session:
        for index in range(2):
            user_ids.append(await session.scalar(text(
                "INSERT INTO users (email, username, hashed_password, is_active, is_verified, "
                "is_superuser, created_at, updated_at) VALUES (:email, :username, 'x', true, true, "
                "false, now(), now()) RETURNING id"),
                {"email": f"discover-{tag}-{index}@lyoai.app", "username": f"disc{tag}{index}"}))
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

    def upload(folder="clips", ext="mp4", payload=b"video-bytes"):
        name = uuid.uuid4().hex + "." + ext
        (tmp_path / folder / name).write_bytes(payload)
        return f"{HOST}/api/v1/media/file/{folder}/{name}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url=HOST) as client:
        yield SimpleNamespace(client=client, upload=upload, sessions=sessions, tag=tag,
                              a={"X-Test-User": str(user_ids[0])}, b={"X-Test-User": str(user_ids[1])},
                              ids=user_ids)

    async with sessions() as session:
        await session.execute(text("DELETE FROM clip_saves WHERE user_id = ANY(:ids)"), {"ids": user_ids})
        await session.execute(text("DELETE FROM clip_views WHERE user_id = ANY(:ids)"), {"ids": user_ids})
        await session.execute(text("DELETE FROM clips WHERE user_id = ANY(:ids)"), {"ids": user_ids})
        await session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": user_ids})
        await session.commit()
    await engine.dispose()


def clip_body(pg, **overrides):
    body = {"title": f"Photosynthesis {pg.tag}", "videoUrl": pg.upload(), "subject": f"Biology{pg.tag}",
            "durationSeconds": 30}
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_publishing_records_a_verified_ready_clip(pg):
    response = await pg.client.post("/api/v1/clips", json=clip_body(pg), headers=pg.a)
    assert response.status_code == 200, response.text
    clip = response.json()["clip"]
    assert clip["mediaStatus"] == "ready"
    assert clip["attribution"] is None
    async with pg.sessions() as session:
        row = (await session.execute(text("SELECT media_status, media_bytes, media_checked_at "
                                          "FROM clips WHERE id = :id"), {"id": int(clip["id"])})).one()
    assert row.media_status == "ready" and row.media_bytes == len(b"video-bytes")
    assert row.media_checked_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("video_url", [
    "https://elsewhere.example/api/v1/media/file/clips/" + "a" * 32 + ".mp4",
    "https://cdn.example.com/lesson.mp4",
    "http://api.test/api/v1/media/file/content/" + "a" * 32 + ".mp4",
])
async def test_publishing_refuses_videos_this_api_did_not_store(pg, video_url):
    response = await pg.client.post("/api/v1/clips", json=clip_body(pg, videoUrl=video_url), headers=pg.a)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_publishing_an_upload_that_is_not_there_is_refused(pg):
    missing = f"{HOST}/api/v1/media/file/clips/{uuid.uuid4().hex}.mp4"
    response = await pg.client.post("/api/v1/clips", json=clip_body(pg, videoUrl=missing), headers=pg.a)
    assert response.status_code == 422
    async with pg.sessions() as session:
        count = await session.scalar(text("SELECT count(*) FROM clips WHERE user_id = :id"), {"id": pg.ids[0]})
    assert count == 0


@pytest.mark.asyncio
async def test_a_relative_upload_path_is_stored_as_an_absolute_url(pg):
    relative = "/api/v1/media/file/" + pg.upload().split("/api/v1/media/file/")[1]
    response = await pg.client.post("/api/v1/clips", json=clip_body(pg, videoUrl=relative), headers=pg.a)
    assert response.status_code == 200, response.text
    assert response.json()["clip"]["videoURL"] == HOST + relative


@pytest.mark.asyncio
async def test_a_missing_own_poster_is_dropped_but_another_poster_is_kept(pg):
    absent = f"{HOST}/api/v1/media/file/clip_thumbnails/{uuid.uuid4().hex}.jpg"
    dropped = await pg.client.post("/api/v1/clips", json=clip_body(pg, thumbnailUrl=absent), headers=pg.a)
    assert dropped.json()["clip"]["thumbnailURL"] is None
    present = pg.upload("clip_thumbnails", "jpg", b"jpeg")
    kept = await pg.client.post("/api/v1/clips", json=clip_body(pg, thumbnailUrl=present), headers=pg.a)
    assert kept.json()["clip"]["thumbnailURL"] == present


@pytest.mark.asyncio
async def test_library_videos_carry_their_credit_and_cannot_be_imported_twice(pg):
    source = f"https://images.nasa.gov/details/{pg.tag}"
    provenance = {"sourceName": "NASA Image and Video Library", "sourceUrl": source,
                  "licenseName": "Public domain", "licenseUrl": "https://www.nasa.gov/nasa-brand-center/images-and-media/",
                  "attribution": "NASA/JPL-Caltech"}
    first = await pg.client.post("/api/v1/clips", json=clip_body(pg, **provenance), headers=pg.a)
    assert first.status_code == 200, first.text
    assert first.json()["clip"]["attribution"] == {
        "credit": "NASA/JPL-Caltech", "sourceName": "NASA Image and Video Library",
        "sourceURL": source, "license": "Public domain",
        "licenseURL": "https://www.nasa.gov/nasa-brand-center/images-and-media/"}
    again = await pg.client.post("/api/v1/clips", json=clip_body(pg, **provenance), headers=pg.a)
    assert again.status_code == 409
    assert again.json()["error"]["details"]["clipId"] == first.json()["clip"]["id"]

    # One source is one video in the feed, whichever account imports it.
    other_account = await pg.client.post("/api/v1/clips", json=clip_body(pg, **provenance), headers=pg.b)
    assert other_account.status_code == 409

    for missing in ("licenseName", "attribution"):
        incomplete = dict(provenance, sourceUrl=f"{source}-{missing}", **{missing: "  "})
        refused = await pg.client.post("/api/v1/clips", json=clip_body(pg, **incomplete), headers=pg.a)
        assert refused.status_code == 400, missing


@pytest.mark.asyncio
async def test_two_imports_of_one_source_racing_each_other_end_in_one_clip(pg, monkeypatch):
    source = f"https://commons.wikimedia.org/wiki/File:{pg.tag}.webm"
    provenance = {"sourceName": "Wikimedia Commons", "sourceUrl": source,
                  "licenseName": "CC BY 4.0", "attribution": "Jane Doe · CC BY 4.0"}
    winner = (await pg.client.post("/api/v1/clips", json=clip_body(pg, **provenance), headers=pg.a)).json()["clip"]["id"]

    # The racing request checked before the winner committed, so its own
    # check saw nothing; the unique index is what has to catch it.
    real_check = clips_router._refuse_published_source
    calls = []

    async def check_that_lost_the_race(db, url):
        calls.append(url)
        if len(calls) > 1:
            await real_check(db, url)

    monkeypatch.setattr(clips_router, "_refuse_published_source", check_that_lost_the_race)
    loser = await pg.client.post("/api/v1/clips", json=clip_body(pg, **provenance), headers=pg.b)
    assert loser.status_code == 409
    assert loser.json()["error"]["details"]["clipId"] == winner
    async with pg.sessions() as session:
        count = await session.scalar(text("SELECT count(*) FROM clips WHERE source_url = :s"), {"s": source})
    assert count == 1


@pytest.mark.asyncio
async def test_an_image_uploaded_to_the_video_folder_is_not_a_video(pg):
    image = pg.upload("clips", "jpg", b"jpeg-bytes")
    response = await pg.client.post("/api/v1/clips", json=clip_body(pg, videoUrl=image), headers=pg.a)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_feed_filters_saved_and_links_serve_only_ready_videos(pg):
    subject = f"Biology{pg.tag}"
    ready = (await pg.client.post("/api/v1/clips", json=clip_body(pg), headers=pg.a)).json()["clip"]["id"]
    broken_ids = []
    for status in ("missing", "unverified", "external"):
        clip_id = (await pg.client.post("/api/v1/clips", json=clip_body(pg), headers=pg.a)).json()["clip"]["id"]
        async with pg.sessions() as session:
            await session.execute(text("UPDATE clips SET media_status = :s WHERE id = :id"),
                                  {"s": status, "id": int(clip_id)})
            await session.commit()
        broken_ids.append(clip_id)
    for clip_id in [ready, *broken_ids]:
        await pg.client.post(f"/api/v1/clips/{clip_id}/save", headers=pg.b)

    feed = (await pg.client.get("/api/v1/clips/discover", params={"subject": subject}, headers=pg.b)).json()
    assert [c["id"] for c in feed["clips"]] == [ready] and feed["total"] == 1
    filters = (await pg.client.get("/api/v1/clips/discover/filters", headers=pg.b)).json()["subjects"]
    assert {"name": subject, "count": 1} in filters
    saved = (await pg.client.get("/api/v1/clips/saved", params={"subject": subject}, headers=pg.b)).json()
    assert [c["id"] for c in saved["clips"]] == [ready] and saved["total"] == 1

    for clip_id in broken_ids:
        assert (await pg.client.get(f"/api/v1/clips/{clip_id}", headers=pg.b)).status_code == 404
        owner_view = await pg.client.get(f"/api/v1/clips/{clip_id}", headers=pg.a)
        assert owner_view.status_code == 200
        assert owner_view.json()["clip"]["mediaStatus"] != "ready"
    mine = (await pg.client.get("/api/v1/clips", headers=pg.a)).json()
    assert mine["total"] == 4, "a creator still sees every clip they made"


@pytest.mark.asyncio
async def test_views_and_saves_work_on_a_database_built_by_migrations(pg):
    clip_id = (await pg.client.post("/api/v1/clips", json=clip_body(pg), headers=pg.a)).json()["clip"]["id"]
    viewed = await pg.client.post(f"/api/v1/clips/{clip_id}/view", headers=pg.b)
    assert viewed.json() == {"success": True, "viewCount": 1}
    saved = await pg.client.post(f"/api/v1/clips/{clip_id}/save", headers=pg.b)
    assert saved.json() == {"success": True, "isSaved": True}
    async with pg.sessions() as session:
        await session.execute(text("DELETE FROM clip_views WHERE clip_id = :id"), {"id": int(clip_id)})
        await session.commit()
