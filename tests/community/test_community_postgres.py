"""Community regressions that only PostgreSQL can reproduce.

SQLite accepts an offset-aware datetime in a naive column and has no native
enums, so the in-memory suite passed while production returned 500 for every
event created by web, iOS, or Android, for every content report, and for
``/community/me`` once a legacy row existed. These tests run the Community
router against a real, migrated PostgreSQL database.

Set ``COMMUNITY_POSTGRES_URL`` (for example the CI service database after
``alembic upgrade head``) to run them; they are skipped otherwise.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lyo_app.auth.routes import get_current_user
from lyo_app.community.routes import router as community_router
from lyo_app.core.database import get_db

POSTGRES_URL = os.getenv("COMMUNITY_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="COMMUNITY_POSTGRES_URL is not set"
)


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest_asyncio.fixture
async def pg(monkeypatch):
    monkeypatch.setenv("COMMUNITY_OVERPASS_URL", "")
    monkeypatch.setenv("COMMUNITY_GEOCODER_URL", "")
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
                    {"email": f"pg-{tag}-{index}@lyoai.app", "username": f"pg{tag}{index}"},
                )
            )
        await session.commit()

    app = FastAPI()
    app.include_router(community_router, prefix="/community")

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
            sessions=sessions,
            a={"X-Test-User": str(user_ids[0])},
            b={"X-Test-User": str(user_ids[1])},
            ids=user_ids,
        )

    async with sessions() as session:
        params = {"ids": user_ids}
        # The app creates ``notifications`` at startup rather than by migration.
        if await session.scalar(text("SELECT to_regclass('public.notifications') IS NOT NULL")):
            await session.execute(
                text("DELETE FROM notifications WHERE user_id = ANY(:ids) OR actor_id = ANY(:ids)"),
                params,
            )
        for statement in (
            "DELETE FROM community_event_guests WHERE user_id = ANY(:ids) OR event_id IN "
            "(SELECT id FROM community_events WHERE organizer_id = ANY(:ids))",
            "DELETE FROM community_event_invites WHERE created_by_id = ANY(:ids)",
            "DELETE FROM content_reports WHERE reporter_id = ANY(:ids)",
            "DELETE FROM community_saved_nodes WHERE user_id = ANY(:ids)",
            "DELETE FROM event_attendances WHERE user_id = ANY(:ids) OR event_id IN "
            "(SELECT id FROM community_events WHERE organizer_id = ANY(:ids))",
            "DELETE FROM community_events WHERE organizer_id = ANY(:ids)",
            "DELETE FROM group_memberships WHERE user_id = ANY(:ids)",
            "DELETE FROM study_groups WHERE creator_id = ANY(:ids)",
            "DELETE FROM users WHERE id = ANY(:ids)",
        ):
            await session.execute(text(statement), params)
        await session.commit()
    await engine.dispose()


def _payload(title: str, start_text: str, end: datetime) -> dict:
    return {
        "title": title,
        "event_type": "workshop",
        "location": "Bronx Library Center",
        "latitude": 40.8622,
        "longitude": -73.8903,
        "start_time": start_text,
        "end_time": end.isoformat().replace("+00:00", "Z"),
        "timezone": "America/New_York",
        "max_attendees": 20,
    }


async def test_events_from_every_client_format_are_created(pg):
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    end = start + timedelta(hours=2)
    formats = {
        "web": start.isoformat().replace("+00:00", ".000Z"),  # Date.toISOString()
        "ios": start.isoformat().replace("+00:00", "Z"),  # .iso8601
        "android": start.isoformat().replace("+00:00", "Z"),  # Instant.toString()
        "offset": start.astimezone(timezone(timedelta(hours=-4))).isoformat(),
    }
    for index, (client_name, start_text) in enumerate(formats.items()):
        response = await pg.client.post(
            "/community/events",
            headers=pg.a,
            json=_payload(f"{client_name} workshop {index}", start_text, end),
        )
        assert response.status_code == 201, (client_name, response.text)
        assert response.json()["start_time"] == start.isoformat().replace("+00:00", "Z")

    nearby = await pg.client.get(
        "/community/nearby",
        headers=pg.b,
        params={"lat": 40.86, "lng": -73.89, "radius_km": 5, "include_institutions": False},
    )
    assert nearby.status_code == 200, nearby.text
    titles = {item["title"] for item in nearby.json()["items"]}
    assert {f"{name} workshop {i}" for i, name in enumerate(formats)} <= titles


async def test_account_reads_survive_legacy_rows(pg):
    async with pg.sessions() as session:
        organizer = pg.ids[0]
        for title, description, capacity in (
            ("Legacy zero capacity", "d", 0),
            ("Legacy long description", "x" * 5000, 10),
        ):
            event_id = await session.scalar(
                text(
                    "INSERT INTO community_events (title, description, event_type, status, "
                    "location, is_online, start_time, end_time, timezone, max_attendees, "
                    "organizer_id, latitude, longitude, created_at, updated_at) VALUES "
                    "(:title, :description, 'LECTURE', 'SCHEDULED', 'Queens', false, "
                    "now() + interval '2 days', now() + interval '2 days 2 hours', 'UTC', "
                    ":capacity, :organizer, 40.73, -73.79, now(), now()) RETURNING id"
                ),
                {"title": title, "description": description, "capacity": capacity, "organizer": organizer},
            )
            await session.execute(
                text(
                    "INSERT INTO event_attendances (status, user_id, event_id, registered_at) "
                    "VALUES ('GOING', :user, :event, now())"
                ),
                {"user": organizer, "event": event_id},
            )
        group_id = await session.scalar(
            text(
                "INSERT INTO study_groups (name, description, privacy, status, max_members, "
                "requires_approval, creator_id, is_online, latitude, longitude, created_at, "
                "updated_at) VALUES ('Legacy pair', 'd', 'PUBLIC', 'ACTIVE', 1, false, :creator, "
                "false, 40.73, -73.79, now(), now()) RETURNING id"
            ),
            {"creator": organizer},
        )
        await session.execute(
            text(
                "INSERT INTO group_memberships (role, is_approved, user_id, study_group_id, "
                "joined_at) VALUES ('OWNER', true, :user, :group, now())"
            ),
            {"user": organizer, "group": group_id},
        )
        await session.commit()

    for path in ("/community/me", "/community/events", "/community/study-groups"):
        response = await pg.client.get(path, headers=pg.a)
        assert response.status_code == 200, (path, response.text)
    me = (await pg.client.get("/community/me", headers=pg.a)).json()
    assert {"Legacy zero capacity", "Legacy long description"} <= {
        node["title"] for node in me["hosting"]
    }


async def test_rsvp_save_and_report_on_postgres(pg):
    start = datetime.now(timezone.utc) + timedelta(days=3)
    created = await pg.client.post(
        "/community/events",
        headers=pg.a,
        json=_payload("Postgres RSVP", start.isoformat().replace("+00:00", "Z"), start + timedelta(hours=1)),
    )
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]

    rsvp = await pg.client.put(
        f"/community/events/{event_id}/rsvp", headers=pg.b, json={"status": "interested"}
    )
    assert rsvp.status_code == 200, rsvp.text
    assert rsvp.json()["rsvp_status"] == "interested"

    save = await pg.client.put(
        f"/community/saved-nodes/event/{event_id}", headers=pg.b, json={"snapshot": rsvp.json()}
    )
    assert save.status_code == 200, save.text

    report = await pg.client.post(
        f"/community/events/{event_id}/report", headers=pg.b, json={"reason": "spam"}
    )
    assert report.status_code == 201, report.text
    legacy_report = await pg.client.post(
        "/community/reports",
        headers=pg.b,
        json={"target_type": "event", "target_id": str(event_id), "reason": "other"},
    )
    assert legacy_report.status_code == 201, legacy_report.text

    me = (await pg.client.get("/community/me", headers=pg.b)).json()
    assert [node["id"] for node in me["interested"]] == [str(event_id)]
    assert [node["key"] for node in me["saved_nodes"]] == [f"event:{event_id}"]

    deleted = await pg.client.delete(f"/community/events/{event_id}", headers=pg.a)
    assert deleted.status_code == 204, deleted.text


async def test_private_event_invites_on_postgres(pg):
    """Links, guests, and removal on the real schema (migration 004)."""
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
    payload = _payload("Private lab", start.isoformat().replace("+00:00", "Z"), start + timedelta(hours=2))
    payload["visibility"] = "private"
    created = await pg.client.post("/community/events", headers=pg.a, json=payload)
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    assert (await pg.client.get(f"/community/nodes/event/{event_id}", headers=pg.b)).status_code == 404

    link = await pg.client.post(f"/community/events/{event_id}/invites", headers=pg.a, json={"max_uses": 1})
    assert link.status_code == 201, link.text
    token = link.json()["token"]
    accepted = await pg.client.post(f"/community/invites/{token}/accept", headers=pg.b)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["is_invited"] is True
    assert (await pg.client.post(f"/community/invites/{token}/accept", headers=pg.b)).status_code == 200
    rsvp = await pg.client.put(f"/community/events/{event_id}/rsvp", headers=pg.b, json={"status": "going"})
    assert rsvp.status_code == 200, rsvp.text

    listing = await pg.client.get(f"/community/events/{event_id}/invites", headers=pg.a)
    assert listing.status_code == 200, listing.text
    assert listing.json()["links"][0]["use_count"] == 1
    assert [g["rsvp_status"] for g in listing.json()["guests"]] == ["going"]

    removed = await pg.client.delete(f"/community/events/{event_id}/guests/{pg.ids[1]}", headers=pg.a)
    assert removed.status_code == 204, removed.text
    assert (await pg.client.get(f"/community/nodes/event/{event_id}", headers=pg.b)).status_code == 404

    direct = await pg.client.post(f"/community/events/{event_id}/guests", headers=pg.a, json={"user_id": pg.ids[1]})
    assert direct.status_code == 201, direct.text
    me = await pg.client.get("/community/me", headers=pg.b)
    assert me.status_code == 200, me.text
    assert [node["key"] for node in me.json()["invited"]] == [f"event:{event_id}"]

    deleted = await pg.client.delete(f"/community/events/{event_id}", headers=pg.a)
    assert deleted.status_code == 204, deleted.text
    assert (await pg.client.get(f"/community/invites/{token}", headers=pg.b)).status_code == 404
