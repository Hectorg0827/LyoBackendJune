"""Moderators keep, remove and restore reported Discover videos, on migrated PostgreSQL.

Three different reporters hide a video until a moderator decides. Keep
dismisses its reports and serves it again. Remove resolves them, takes it out
of Discover for everyone but its owner, and moves its video and poster out of
public storage so their URLs stop working; restore brings both back. Only a
superuser or a learner listed in DISCOVER_MODERATOR_EMAILS may do any of it.

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
from lyo_app.routers import clip_moderation
from lyo_app.routers import clips as clips_router
from lyo_app.routers import user_media

POSTGRES_URL = os.getenv("DISCOVER_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="DISCOVER_POSTGRES_URL is not set")
HOST = "http://api.test"
OWNER, REPORTERS, MODERATOR, LEARNER = 0, (1, 2, 3), 4, 5


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
    (tmp_path / "clip_thumbnails").mkdir()

    engine = create_async_engine(_async_url(POSTGRES_URL))
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tag = uuid.uuid4().hex[:10]
    users = []
    async with sessions() as session:
        for index in range(6):
            email = f"moderation-{tag}-{index}@lyoai.app"
            user_id = await session.scalar(text(
                "INSERT INTO users (email, username, first_name, hashed_password, is_active, is_verified, "
                "is_superuser, created_at, updated_at) VALUES (:email, :username, :first, 'x', true, true, "
                "false, now(), now()) RETURNING id"),
                {"email": email, "username": f"mod{tag}{index}", "first": f"Learner{index}"})
            users.append(SimpleNamespace(id=user_id, email=email, first_name=f"Learner{index}",
                                         last_name="", username=f"mod{tag}{index}", avatar_url=None,
                                         is_superuser=False))
        await session.commit()
    monkeypatch.setenv("DISCOVER_MODERATOR_EMAILS", f"someone@else.test, {users[MODERATOR].email.upper()}")

    app = FastAPI()
    setup_error_handlers(app)
    for router in (clips_router.router, clip_moderation.router):
        app.include_router(router, prefix="/api/v1")
    app.include_router(user_media.router)  # already under /api/v1/media
    by_id = {user.id: user for user in users}

    async def override_session():
        async with sessions() as session:
            yield session

    async def override_user(x_test_user: int = Header(...)):
        return by_id[x_test_user]

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url=HOST) as client:
        def as_user(index):
            return {"X-Test-User": str(users[index].id)}

        def upload(folder, ext):
            name = uuid.uuid4().hex + "." + ext
            (tmp_path / folder / name).write_bytes(b"bytes-" + name.encode())
            return name, f"{HOST}/api/v1/media/file/{folder}/{name}"

        async def publish(video=None, **overrides):
            video_name, video_url = video or upload("clips", "mp4")
            poster_name, poster_url = upload("clip_thumbnails", "jpg")
            body = {"title": f"Rocks {tag}", "subject": f"Geology{tag}", "durationSeconds": 20,
                    "videoUrl": video_url, "thumbnailUrl": poster_url}
            body.update(overrides)
            response = await client.post("/api/v1/clips", json=body, headers=as_user(OWNER))
            assert response.status_code == 200, response.text
            return SimpleNamespace(id=response.json()["clip"]["id"], video=video_name, poster=poster_name,
                                   video_url=video_url, poster_url=poster_url)

        async def report(index, clip_id, reason="violence", description=None):
            response = await client.post(f"/api/v1/clips/{clip_id}/report", headers=as_user(index),
                                         json={"reason": reason, "description": description})
            assert response.status_code in (200, 201), response.text
            return response

        async def hide(clip_id):
            for index, reason in zip(REPORTERS, ("violence", "violence", "spam")):
                await report(index, clip_id, reason, description=f"note {index}")

        async def decide(clip_id, action, note=None, index=MODERATOR):
            return await client.post(f"/api/v1/moderation/clips/{clip_id}/decision", headers=as_user(index),
                                     json={"action": action, "note": note})

        async def listing(view, **params):
            response = await client.get("/api/v1/moderation/clips", headers=as_user(MODERATOR),
                                        params={"view": view, "q": tag, **params})
            assert response.status_code == 200, response.text
            return response.json()

        async def feed(index):
            response = await client.get("/api/v1/clips/discover", headers=as_user(index),
                                        params={"subject": f"Geology{tag}", "per_page": 100})
            return [clip["id"] for clip in response.json()["clips"]]

        yield SimpleNamespace(client=client, sessions=sessions, root=tmp_path, users=users, tag=tag,
                              as_user=as_user, upload=upload, publish=publish, report=report, hide=hide,
                              decide=decide, listing=listing, feed=feed)

    async with sessions() as session:
        params = {"ids": [user.id for user in users]}
        await session.execute(text("DELETE FROM content_reports WHERE reporter_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clip_views WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM clips WHERE user_id = ANY(:ids)"), params)
        await session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), params)
        await session.commit()
    await engine.dispose()


def public(pg, folder, name):
    return (pg.root / folder / name).is_file()


def removed(pg, folder, name):
    return (pg.root / media.LOCAL_REMOVED_DIR / folder / name).is_file()


async def _report_statuses(pg, clip_id):
    async with pg.sessions() as session:
        rows = (await session.execute(text(
            "SELECT status, reviewed_by_id, resolution_notes FROM content_reports "
            "WHERE target_type = 'clip' AND target_id = :id"), {"id": str(clip_id)})).all()
    return {(row.status, row.reviewed_by_id, row.resolution_notes) for row in rows}


def test_only_superusers_and_listed_emails_are_moderators(monkeypatch):
    monkeypatch.setenv("DISCOVER_MODERATOR_EMAILS", " Owner@LyoAI.app ,other@lyoai.app")
    assert clip_moderation.is_moderator(SimpleNamespace(email="owner@lyoai.app", is_superuser=False))
    assert clip_moderation.is_moderator(SimpleNamespace(email="x@y.z", is_superuser=True))
    assert not clip_moderation.is_moderator(SimpleNamespace(email="x@y.z", is_superuser=False))
    assert not clip_moderation.is_moderator(SimpleNamespace(email="", is_superuser=False))
    monkeypatch.delenv("DISCOVER_MODERATOR_EMAILS")
    assert not clip_moderation.is_moderator(SimpleNamespace(email="owner@lyoai.app", is_superuser=False))


@pytest.mark.asyncio
async def test_learners_who_are_not_moderators_are_refused(pg):
    clip = await pg.publish()
    me = await pg.client.get("/api/v1/moderation/me", headers=pg.as_user(LEARNER))
    assert me.json() == {"moderator": False}
    assert (await pg.client.get("/api/v1/moderation/me", headers=pg.as_user(MODERATOR))).json() == {"moderator": True}
    listing = await pg.client.get("/api/v1/moderation/clips", headers=pg.as_user(LEARNER))
    assert listing.status_code == 403
    assert (await pg.decide(clip.id, "remove", index=LEARNER)).status_code == 403
    assert public(pg, "clips", clip.video)


@pytest.mark.asyncio
async def test_reported_videos_are_listed_most_reported_first_with_reasons_and_notes(pg):
    quiet = await pg.publish(title=f"Quiet {pg.tag}")
    once = await pg.publish(title=f"Once {pg.tag}")
    hidden = await pg.publish(title=f"Hidden {pg.tag}")
    await pg.report(1, once.id, "spam", description="Selling things")
    await pg.hide(hidden.id)

    reported = await pg.listing("reported")
    assert [c["id"] for c in reported["clips"]] == [hidden.id, once.id]
    assert reported["total"] == 2
    top = reported["clips"][0]
    assert top["moderationStatus"] == "hidden"
    assert top["reports"]["pending"] == 3
    assert top["reports"]["reasons"] == {"violence": 2, "spam": 1}
    assert {n["text"] for n in top["reports"]["notes"]} == {"note 1", "note 2", "note 3"}
    assert top["authorName"] == "Learner0"

    everything = await pg.listing("all")
    assert {c["id"] for c in everything["clips"]} == {quiet.id, once.id, hidden.id}
    assert (await pg.listing("removed"))["clips"] == []


@pytest.mark.asyncio
async def test_keep_dismisses_the_reports_and_serves_the_video_again(pg):
    clip = await pg.publish()
    await pg.hide(clip.id)
    assert clip.id not in await pg.feed(LEARNER)

    response = await pg.decide(clip.id, "keep", note="It is a real experiment")
    assert response.status_code == 200, response.text
    assert response.json()["clip"]["moderationStatus"] == "active"
    assert response.json()["clip"]["moderatedBy"] == "Learner4"
    moderator_id = pg.users[MODERATOR].id
    assert await _report_statuses(pg, clip.id) == {("dismissed", moderator_id, "It is a real experiment")}
    assert clip.id in await pg.feed(LEARNER)
    assert clip.id not in await pg.feed(REPORTERS[0]), "a reporter still does not see what they reported"
    assert (await pg.listing("reported"))["clips"] == []
    assert public(pg, "clips", clip.video)


@pytest.mark.asyncio
async def test_remove_takes_the_video_and_poster_offline_and_restore_brings_them_back(pg):
    clip = await pg.publish()
    await pg.report(1, clip.id)
    file_path = f"/api/v1/media/file/clips/{clip.video}"
    assert (await pg.client.get(file_path)).status_code == 200

    response = await pg.decide(clip.id, "remove", note="Dangerous stunt")
    assert response.status_code == 200, response.text
    assert response.json()["clip"]["moderationStatus"] == "removed"
    assert removed(pg, "clips", clip.video) and not public(pg, "clips", clip.video)
    assert removed(pg, "clip_thumbnails", clip.poster) and not public(pg, "clip_thumbnails", clip.poster)
    assert (await pg.client.get(file_path)).status_code == 404
    assert (await pg.client.get(f"/api/v1/media/file/clip_thumbnails/{clip.poster}")).status_code == 404
    assert await _report_statuses(pg, clip.id) == {("resolved", pg.users[MODERATOR].id, "Dangerous stunt")}
    assert clip.id not in await pg.feed(LEARNER)
    link = await pg.client.get(f"/api/v1/clips/{clip.id}", headers=pg.as_user(LEARNER))
    assert link.status_code == 404
    own = await pg.client.get(f"/api/v1/clips/{clip.id}", headers=pg.as_user(OWNER))
    assert own.json()["clip"]["moderationStatus"] == "removed"
    gone = await pg.listing("removed")
    assert [(c["id"], c["moderatedBy"], c["moderationNote"]) for c in gone["clips"]] == [
        (clip.id, "Learner4", "Dangerous stunt")]
    assert clip.id not in [c["id"] for c in (await pg.listing("all"))["clips"]]

    response = await pg.decide(clip.id, "restore")
    assert response.status_code == 200, response.text
    assert response.json()["clip"]["moderationStatus"] == "active"
    assert public(pg, "clips", clip.video) and not removed(pg, "clips", clip.video)
    assert public(pg, "clip_thumbnails", clip.poster)
    assert (await pg.client.get(file_path)).status_code == 200
    assert clip.id in await pg.feed(LEARNER)


@pytest.mark.asyncio
async def test_decisions_that_do_not_apply_are_refused(pg):
    clip = await pg.publish()
    assert (await pg.decide(clip.id, "restore")).status_code == 409
    assert (await pg.decide(clip.id, "remove")).status_code == 200
    assert (await pg.decide(clip.id, "keep")).status_code == 409
    assert (await pg.decide(clip.id, "remove")).status_code == 409
    assert (await pg.decide(2_000_000_000, "keep")).status_code == 404
    assert (await pg.decide(clip.id, "delete")).status_code == 422


@pytest.mark.asyncio
async def test_a_storage_failure_part_way_changes_nothing(pg, monkeypatch):
    clip = await pg.publish()
    real = media.set_media_removed
    calls = []

    def flaky(folder, name, root, to_removed):
        calls.append((folder, to_removed))
        if folder == "clip_thumbnails" and to_removed:
            raise OSError("bucket unavailable")
        return real(folder, name, root, to_removed)

    monkeypatch.setattr(clip_moderation, "set_media_removed", flaky)
    response = await pg.decide(clip.id, "remove")
    assert response.status_code == 503
    assert public(pg, "clips", clip.video), "the video moved first and was moved back"
    assert calls == [("clips", True), ("clip_thumbnails", True), ("clips", False)]
    async with pg.sessions() as session:
        status = await session.scalar(text("SELECT moderation_status FROM clips WHERE id = :id"), {"id": int(clip.id)})
    assert status == "active"


@pytest.mark.asyncio
async def test_a_video_file_another_clip_uses_stays_online(pg):
    first = await pg.publish()
    second = await pg.publish(video=(first.video, first.video_url), title=f"Copy {pg.tag}")
    assert (await pg.decide(first.id, "remove")).status_code == 200
    assert public(pg, "clips", first.video), "the second clip still plays it"
    assert removed(pg, "clip_thumbnails", first.poster), "the poster was the first clip's own"
    assert second.id in await pg.feed(LEARNER)


@pytest.mark.asyncio
async def test_deleting_ones_own_video_deletes_its_files_unless_shared(pg):
    clip = await pg.publish()
    response = await pg.client.delete(f"/api/v1/clips/{clip.id}", headers=pg.as_user(OWNER))
    assert response.status_code == 200, response.text
    assert not public(pg, "clips", clip.video) and not public(pg, "clip_thumbnails", clip.poster)

    first = await pg.publish()
    second = await pg.publish(video=(first.video, first.video_url))
    assert (await pg.client.delete(f"/api/v1/clips/{first.id}", headers=pg.as_user(OWNER))).status_code == 200
    assert public(pg, "clips", first.video)
    assert second.id in await pg.feed(LEARNER)
