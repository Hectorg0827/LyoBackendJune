"""Contract tests for the shared Community discovery API (contract 4).

These drive the real Community router the way the three clients do: the
same account from "web", "ios", and "android" test clients, and a second
account that must never inherit the first account's state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient

from lyo_app.auth.routes import get_current_user
from lyo_app.community import geocoding
from lyo_app.community.content_safety import plain_text, safe_web_url
from lyo_app.community.learning_around import LearningAroundService, learning_around_service
from lyo_app.community.models import CommunityEvent, EventStatus, EventType
from lyo_app.community.query_intent import classify, parse_topic
from lyo_app.community.routes import router as community_router
from lyo_app.community.schemas import (
    CommunityEventRead,
    LearningNodeCategory,
    PlaceSuggestion,
    StudyGroupRead,
)
from lyo_app.community.timeutil import as_utc, day_window, to_naive_utc
from lyo_app.core.database import get_db

USER_A = {"X-Test-User": "101"}
USER_B = {"X-Test-User": "202"}
USER_C = {"X-Test-User": "303"}
USER_D = {"X-Test-User": "404"}
NYC = {"lat": 40.7128, "lng": -74.0060}


@pytest.fixture(autouse=True)
def _no_external_providers(monkeypatch):
    """Tests never reach Overpass or the geocoder unless they opt in."""
    monkeypatch.setenv("COMMUNITY_OVERPASS_URL", "")
    monkeypatch.setenv("COMMUNITY_GEOCODER_URL", "")
    LearningAroundService._poi_cache.clear()
    LearningAroundService._place_index.clear()


@pytest_asyncio.fixture
async def clients(db_session):
    """web, ios, and android clients sharing one backend and identity header."""
    app = FastAPI()
    app.include_router(community_router, prefix="/api/v1/community")

    async def override_get_db():
        yield db_session

    async def override_current_user(x_test_user: int = Header(101)):
        return SimpleNamespace(id=x_test_user)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://web") as web,
        AsyncClient(transport=transport, base_url="http://ios") as ios,
        AsyncClient(transport=transport, base_url="http://android") as android,
    ):
        yield SimpleNamespace(web=web, ios=ios, android=android, db=db_session)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_payload(title: str, *, days: float = 1, hours: float = 2, **overrides) -> dict:
    start = datetime.now(timezone.utc) + timedelta(days=days)
    payload = {
        "title": title,
        "description": "Learn together",
        "event_type": "workshop",
        "location": "Midtown Library",
        "latitude": 40.7130,
        "longitude": -74.0050,
        "start_time": _iso_z(start),
        "end_time": _iso_z(start + timedelta(hours=hours)),
        "timezone": "America/New_York",
    }
    payload.update(overrides)
    return payload


async def _create(client: AsyncClient, headers: dict, title: str, **overrides) -> dict:
    response = await client.post(
        "/api/v1/community/events", headers=headers, json=_event_payload(title, **overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _nearby(client: AsyncClient, headers: dict, **params) -> list[dict]:
    query = {**NYC, "radius_km": 10, "include_institutions": False, **params}
    response = await client.get("/api/v1/community/nearby", headers=headers, params=query)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _insert_event(db, **fields) -> CommunityEvent:
    now = datetime.utcnow()
    values = dict(
        title="Inserted event",
        event_type=EventType.WORKSHOP,
        status=EventStatus.SCHEDULED,
        location="Midtown Library",
        is_online=False,
        latitude=40.7130,
        longitude=-74.0050,
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=2),
        timezone="UTC",
        organizer_id=101,
        created_at=now,
        updated_at=now,
    )
    values.update(fields)
    event = CommunityEvent(**values)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# The production 500s
# ---------------------------------------------------------------------------


async def test_offset_aware_times_from_every_client_are_accepted(clients):
    """web toISOString(), iOS .iso8601, Android Instant, and +05:30 offsets."""
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
    ist = timezone(timedelta(hours=5, minutes=30))
    variants = {
        "web": start.isoformat().replace("+00:00", ".000Z"),
        "ios": start.isoformat().replace("+00:00", "Z"),
        "offset": start.astimezone(ist).isoformat(),
    }
    for index, (label, start_text) in enumerate(variants.items()):
        response = await clients.web.post(
            "/api/v1/community/events",
            headers=USER_A,
            json=_event_payload(
                f"Offset {label}",
                start_time=start_text,
                end_time=_iso_z(start + timedelta(hours=1)),
            ),
        )
        assert response.status_code == 201, (label, response.text)
        body = response.json()
        # Stored as the same instant, returned with an explicit UTC marker.
        assert body["start_time"] == _iso_z(start), label
        assert body["start_time"].endswith("Z")


async def test_read_models_tolerate_legacy_rows():
    now = datetime.utcnow()
    legacy_event = SimpleNamespace(
        id=1, title="Old", description="x" * 5000, event_type=EventType.LECTURE,
        location=None, is_online=None, meeting_url=None, max_attendees=0,
        start_time=now, end_time=now + timedelta(hours=1), timezone=None,
        study_group_id=None, course_id=None, lesson_id=None, status=EventStatus.SCHEDULED,
        organizer_id=1, latitude=200.0, longitude=-74.0, room_id=None, image_url=None,
        created_at=now, updated_at=now,
    )
    event = CommunityEventRead.model_validate(legacy_event)
    assert event.max_attendees is None
    assert event.latitude is None
    assert event.timezone == "UTC"
    assert event.visibility.value == "public"
    legacy_group = SimpleNamespace(
        id=1, name="Pair", description="y" * 5000, privacy="public", max_members=1,
        requires_approval=None, course_id=None, location=None, is_online=None,
        meeting_url=None, latitude=None, longitude=None, image_url=None,
        status="active", creator_id=1, created_at=now, updated_at=now,
    )
    group = StudyGroupRead.model_validate(legacy_group)
    assert group.max_members == 1
    assert group.is_online is False


async def test_me_and_lists_survive_legacy_rows(clients):
    await _insert_event(clients.db, title="Zero capacity", max_attendees=0)
    await _insert_event(clients.db, title="Long description", description="z" * 6000)
    await _create(clients.web, USER_A, "Healthy event")
    for path in ("/api/v1/community/me", "/api/v1/community/events"):
        response = await clients.web.get(path, headers=USER_A)
        assert response.status_code == 200, (path, response.text)


async def test_me_isolates_a_failing_section(clients, monkeypatch):
    await _create(clients.web, USER_A, "Still listed")

    async def broken_following(db, user_id):
        raise RuntimeError("user_follows table is missing")

    monkeypatch.setattr(learning_around_service, "_following", broken_following)
    response = await clients.web.get("/api/v1/community/me", headers=USER_A)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["following"] == []
    assert [node["title"] for node in body["hosting"]] == ["Still listed"]


async def test_nearby_returns_partial_map_when_a_source_fails(clients, monkeypatch):
    await _create(clients.web, USER_A, "Survives")
    original = LearningAroundService._scalar_rows

    async def flaky(db, statement):
        if "study_groups" in str(statement):
            raise RuntimeError("study_groups relation is broken")
        return await original(db, statement)

    monkeypatch.setattr(LearningAroundService, "_scalar_rows", staticmethod(flaky))
    response = await clients.web.get(
        "/api/v1/community/nearby",
        headers=USER_A,
        params={**NYC, "radius_km": 10, "include_institutions": False},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "study_groups" in body["degraded_sources"]
    assert [item["title"] for item in body["items"]] == ["Survives"]


async def test_reports_are_stored(clients):
    event = await _create(clients.web, USER_A, "Report target")
    response = await clients.web.post(
        "/api/v1/community/reports",
        headers=USER_B,
        json={"target_type": "event", "target_id": str(event["id"]), "reason": "spam"},
    )
    assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# Discovery basics
# ---------------------------------------------------------------------------


async def test_unauthenticated_requests_are_rejected(async_client):
    response = await async_client.get("/api/v1/community/nearby", params=NYC)
    assert response.status_code in (401, 403)


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 200, "lng": 0},
        {"lat": 0, "lng": -181},
        {"lat": "north", "lng": 0},
        {"lng": 0},
        {"lat": 0, "lng": 0, "radius_km": 0},
        {"lat": 0, "lng": 0, "radius_km": 500},
        {"lat": 0, "lng": 0, "when": "yesterday"},
        {"lat": 0, "lng": 0, "categories": "casino"},
    ],
)
async def test_malformed_discovery_parameters_are_422(clients, params):
    response = await clients.web.get("/api/v1/community/nearby", headers=USER_A, params=params)
    assert response.status_code == 422, response.text


async def test_empty_area_is_an_empty_map_not_an_error(clients):
    await _create(clients.web, USER_A, "Far away")
    items = await _nearby(clients.web, USER_A, lat=-33.87, lng=151.21)
    assert items == []


async def test_bounding_radius_excludes_distant_events(clients):
    await _create(clients.web, USER_A, "Near")
    await _create(clients.web, USER_A, "Across the river", latitude=40.7580, longitude=-73.9855)
    near = await _nearby(clients.web, USER_A, radius_km=1)
    wide = await _nearby(clients.web, USER_A, radius_km=10)
    assert [item["title"] for item in near] == ["Near"]
    assert {item["title"] for item in wide} == {"Near", "Across the river"}


# ---------------------------------------------------------------------------
# Create, edit, delete
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"end_time": _iso_z(datetime.now(timezone.utc) + timedelta(hours=1))}, "end after it starts"),
        ({"hours": 24 * 40}, "at most 31 days"),
        ({"days": -2}, "already ended"),
        ({"latitude": 40.7, "longitude": None}, "both latitude and longitude"),
        ({"meeting_url": "javascript:alert(1)"}, "http"),
        ({"website_url": "ftp://files.example.com"}, "http"),
        ({"description": "http://a.io http://b.io http://c.io http://d.io"}, "at most 3 links"),
        ({"currency": "US1", "price_type": "paid", "price_amount": 5}, "three-letter"),
    ],
)
async def test_invalid_events_are_rejected(clients, overrides, message):
    payload = _event_payload("Invalid", **{k: v for k, v in overrides.items() if k in {"days", "hours"}})
    payload.update({k: v for k, v in overrides.items() if k not in {"days", "hours"}})
    response = await clients.web.post("/api/v1/community/events", headers=USER_A, json=payload)
    assert response.status_code == 422, response.text
    assert message in response.text


async def test_user_content_is_stored_as_plain_text(clients):
    event = await _create(
        clients.web,
        USER_A,
        "<b>Q&amp;A</b> <script>alert(1)</script>night",
        description="<img src=x onerror=alert(1)>Bring &lt;script&gt;notes&lt;/script&gt;",
        website_url="www.lyoai.app/events",
    )
    assert event["title"] == "Q&A alert(1)night"
    assert "<" not in event["description"]
    assert event["website_url"] == "https://www.lyoai.app/events"


async def test_resubmitting_the_same_create_does_not_duplicate(clients):
    first = await _create(clients.web, USER_A, "Once only", client_request_id="req-123")
    again = await _create(clients.web, USER_A, "Once only", client_request_id="req-123")
    assert again["id"] == first["id"]
    # Older clients without a request id: same title + start within minutes.
    payload = _event_payload("Legacy double tap")
    one = await clients.web.post("/api/v1/community/events", headers=USER_A, json=payload)
    two = await clients.web.post("/api/v1/community/events", headers=USER_A, json=payload)
    assert one.json()["id"] == two.json()["id"]
    titles = [item["title"] for item in await _nearby(clients.web, USER_A)]
    assert titles.count("Once only") == 1
    assert titles.count("Legacy double tap") == 1


async def test_event_creation_is_rate_limited(clients):
    for index in range(10):
        await _create(clients.web, USER_A, f"Burst {index}")
    response = await clients.web.post(
        "/api/v1/community/events", headers=USER_A, json=_event_payload("Burst 11")
    )
    assert response.status_code == 429, response.text
    assert response.headers.get("retry-after")
    # Another organizer is unaffected.
    await _create(clients.web, USER_B, "Different host")


async def test_only_the_organizer_can_edit_or_delete(clients):
    event = await _create(clients.web, USER_A, "Owned")
    path = f"/api/v1/community/events/{event['id']}"

    denied = await clients.android.patch(path, headers=USER_B, json={"title": "Hijacked"})
    assert denied.status_code == 403
    denied = await clients.android.delete(path, headers=USER_B)
    assert denied.status_code == 403

    edited = await clients.ios.patch(
        path, headers=USER_A, json={"title": "Owned and renamed", "price_type": "paid", "price_amount": 12}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Owned and renamed"
    assert edited.json()["price_type"] == "paid"
    moved = await clients.ios.put(
        path,
        headers=USER_A,
        json={"end_time": _iso_z(datetime.now(timezone.utc) - timedelta(hours=1))},
    )
    assert moved.status_code == 400

    # User B saved it; deleting removes it from B's account too.
    node = next(item for item in await _nearby(clients.web, USER_B) if item["id"] == str(event["id"]))
    saved = await clients.web.put(
        f"/api/v1/community/saved-nodes/event/{event['id']}", headers=USER_B, json={"snapshot": node}
    )
    assert saved.status_code == 200, saved.text
    deleted = await clients.web.delete(path, headers=USER_A)
    assert deleted.status_code == 204
    me_b = (await clients.android.get("/api/v1/community/me", headers=USER_B)).json()
    assert me_b["saved_nodes"] == []
    gone = await clients.web.get(path, headers=USER_A)
    assert gone.status_code == 404


# ---------------------------------------------------------------------------
# Save and RSVP
# ---------------------------------------------------------------------------


async def test_save_and_unsave_are_idempotent(clients):
    event = await _create(clients.web, USER_A, "Savable")
    node = next(item for item in await _nearby(clients.web, USER_B) if item["id"] == str(event["id"]))
    path = f"/api/v1/community/saved-nodes/event/{event['id']}"
    # A client cannot rewrite what a Lyo event says by saving a forged copy.
    forged = {**node, "title": "Forged title"}
    for _ in range(2):
        response = await clients.web.put(path, headers=USER_B, json={"snapshot": forged})
        assert response.status_code == 200, response.text
        assert response.json()["title"] == "Savable"
    me = (await clients.ios.get("/api/v1/community/me", headers=USER_B)).json()
    assert [item["key"] for item in me["saved_nodes"]] == [f"event:{event['id']}"]
    for _ in range(2):
        response = await clients.android.delete(path, headers=USER_B)
        assert response.status_code == 204
    me = (await clients.ios.get("/api/v1/community/me", headers=USER_B)).json()
    assert me["saved_nodes"] == []


async def test_saving_a_missing_event_is_404(clients):
    snapshot = {"key": "event:999", "kind": "event", "category": "event", "id": "999", "title": "Ghost"}
    response = await clients.web.put(
        "/api/v1/community/saved-nodes/event/999", headers=USER_A, json={"snapshot": snapshot}
    )
    assert response.status_code == 404


async def test_rsvp_going_interested_and_clear(clients):
    event = await _create(clients.web, USER_A, "RSVP me", max_attendees=2)
    rsvp = f"/api/v1/community/events/{event['id']}/rsvp"

    interested = await clients.web.put(rsvp, headers=USER_B, json={"status": "interested"})
    assert interested.status_code == 200, interested.text
    body = interested.json()
    assert body["rsvp_status"] == "interested"
    assert body["interested_count"] == 1
    assert body["going_count"] == 1  # the organizer

    going = await clients.web.put(rsvp, headers=USER_B, json={"status": "going"})
    assert going.json()["rsvp_status"] == "going"
    again = await clients.web.put(rsvp, headers=USER_B, json={"status": "going"})
    assert again.status_code == 200
    assert again.json()["going_count"] == 2
    assert again.json()["is_full"] is True

    full = await clients.web.put(rsvp, headers=USER_C, json={"status": "going"})
    assert full.status_code == 409
    # Interest never takes a seat.
    watching = await clients.web.put(rsvp, headers=USER_C, json={"status": "interested"})
    assert watching.status_code == 200

    for _ in range(2):
        cleared = await clients.web.delete(rsvp, headers=USER_B)
        assert cleared.status_code == 204
    node = next(item for item in await _nearby(clients.web, USER_B) if item["id"] == str(event["id"]))
    assert node["rsvp_status"] is None
    assert node["is_attending"] is False

    # Legacy attend endpoints are idempotent and share the same rows.
    for _ in range(2):
        attend = await clients.ios.post(f"/api/v1/community/events/{event['id']}/attend", headers=USER_B)
        assert attend.status_code == 201, attend.text
    for _ in range(2):
        leave = await clients.ios.delete(f"/api/v1/community/events/{event['id']}/attend", headers=USER_B)
        assert leave.status_code == 204


async def test_past_and_cancelled_events_leave_discovery(clients):
    now = datetime.utcnow()
    past = await _insert_event(
        clients.db, title="Yesterday's lecture", start_time=now - timedelta(days=1, hours=2),
        end_time=now - timedelta(days=1),
    )
    live = await _insert_event(
        clients.db, title="Happening now", start_time=now - timedelta(minutes=30),
        end_time=now + timedelta(minutes=30),
    )
    cancelled = await _create(clients.web, USER_A, "Called off")
    patched = await clients.web.patch(
        f"/api/v1/community/events/{cancelled['id']}", headers=USER_A, json={"status": "cancelled"}
    )
    assert patched.status_code == 200, patched.text

    titles = {item["title"]: item for item in await _nearby(clients.web, USER_B)}
    assert "Yesterday's lecture" not in titles
    assert "Called off" not in titles
    assert titles["Happening now"]["lifecycle"] == "live"

    detail = await clients.web.get(f"/api/v1/community/nodes/event/{past.id}", headers=USER_B)
    assert detail.status_code == 200, detail.text
    assert detail.json()["node"]["lifecycle"] == "past"
    detail = await clients.web.get(f"/api/v1/community/nodes/event/{cancelled['id']}", headers=USER_B)
    assert detail.json()["node"]["lifecycle"] == "cancelled"

    for event_id in (past.id, cancelled["id"]):
        rsvp = await clients.web.put(
            f"/api/v1/community/events/{event_id}/rsvp", headers=USER_B, json={"status": "going"}
        )
        assert rsvp.status_code == 409, rsvp.text
    assert live.id


# ---------------------------------------------------------------------------
# Visibility, moderation, and multiple users
# ---------------------------------------------------------------------------


async def test_visibility_rules(clients):
    public = await _create(clients.web, USER_A, "Public talk")
    unlisted = await _create(clients.web, USER_A, "Unlisted meetup", visibility="unlisted")
    private = await _create(clients.web, USER_A, "Private session", visibility="private")

    mine = {item["title"] for item in await _nearby(clients.web, USER_A)}
    assert mine == {"Public talk", "Unlisted meetup", "Private session"}

    theirs = {item["title"] for item in await _nearby(clients.android, USER_B)}
    assert theirs == {"Public talk"}

    listed = {event["title"] for event in (await clients.android.get("/api/v1/community/events", headers=USER_B)).json()}
    assert listed == {"Public talk"}

    assert (await clients.android.get(f"/api/v1/community/events/{public['id']}", headers=USER_B)).status_code == 200
    assert (await clients.android.get(f"/api/v1/community/events/{unlisted['id']}", headers=USER_B)).status_code == 200
    assert (await clients.android.get(f"/api/v1/community/events/{private['id']}", headers=USER_B)).status_code == 404
    assert (await clients.android.get(f"/api/v1/community/nodes/event/{private['id']}", headers=USER_B)).status_code == 404


async def test_meeting_links_only_reach_attendees(clients):
    event = await _create(
        clients.web, USER_A, "Hybrid lab", is_online=True, meeting_url="https://meet.example.com/lab"
    )
    stranger = next(item for item in await _nearby(clients.web, USER_B) if item["id"] == str(event["id"]))
    assert stranger["meeting_url"] is None
    assert stranger["attendance_mode"] == "hybrid"
    await clients.web.put(f"/api/v1/community/events/{event['id']}/rsvp", headers=USER_B, json={"status": "going"})
    attendee = next(item for item in await _nearby(clients.web, USER_B) if item["id"] == str(event["id"]))
    assert attendee["meeting_url"] == "https://meet.example.com/lab"


async def test_reporting_hides_an_event_after_repeated_reports(clients):
    event = await _create(clients.web, USER_A, "Spammy")
    path = f"/api/v1/community/events/{event['id']}/report"

    own = await clients.web.post(path, headers=USER_A, json={"reason": "spam"})
    assert own.status_code == 400

    first = await clients.web.post(path, headers=USER_B, json={"reason": "spam", "description": "<b>ads</b>"})
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "received"
    repeat = await clients.web.post(path, headers=USER_B, json={"reason": "spam"})
    assert repeat.json()["status"] == "already_reported"

    await clients.web.post(path, headers=USER_C, json={"reason": "not-a-reason"})
    still_visible = {item["title"] for item in await _nearby(clients.web, USER_D)}
    assert "Spammy" in still_visible
    await clients.web.post(path, headers=USER_D, json={"reason": "misinformation"})

    hidden_for_others = {item["title"] for item in await _nearby(clients.web, USER_D)}
    assert "Spammy" not in hidden_for_others
    organizer_view = {item["title"] for item in await _nearby(clients.web, USER_A)}
    assert "Spammy" in organizer_view


async def test_second_user_never_inherits_first_users_state(clients):
    event = await _create(clients.web, USER_A, "A's workshop")
    node = next(item for item in await _nearby(clients.web, USER_A) if item["id"] == str(event["id"]))
    await clients.web.put(
        f"/api/v1/community/saved-nodes/event/{event['id']}", headers=USER_A, json={"snapshot": node}
    )
    b_view = next(item for item in await _nearby(clients.ios, USER_B) if item["id"] == str(event["id"]))
    assert b_view["is_saved"] is False
    assert b_view["rsvp_status"] is None
    assert b_view["is_owner"] is False
    me_b = (await clients.ios.get("/api/v1/community/me", headers=USER_B)).json()
    assert me_b["saved_nodes"] == [] and me_b["hosting"] == [] and me_b["going"] == []
    patch = await clients.ios.patch(
        f"/api/v1/community/events/{event['id']}", headers=USER_B, json={"title": "Mine now"}
    )
    assert patch.status_code == 403


async def test_account_state_is_identical_on_every_device(clients):
    """The cross-device scenario: web acts, iOS and Android agree, Android changes, web agrees."""
    other = await _create(clients.android, USER_B, "Other host's event")
    to_save = await _create(clients.android, USER_B, "Saved on web")

    # On web, User A creates an event, saves one, and marks another interested.
    created = await _create(clients.web, USER_A, "Created on web")
    node = next(item for item in await _nearby(clients.web, USER_A) if item["id"] == str(to_save["id"]))
    save = await clients.web.put(
        f"/api/v1/community/saved-nodes/event/{to_save['id']}", headers=USER_A, json={"snapshot": node}
    )
    assert save.status_code == 200
    interested = await clients.web.put(
        f"/api/v1/community/events/{other['id']}/rsvp", headers=USER_A, json={"status": "interested"}
    )
    assert interested.status_code == 200

    def summary(body: dict) -> dict:
        return {
            "saved": sorted(item["key"] for item in body["saved_nodes"]),
            "hosting": sorted(item["id"] for item in body["hosting"]),
            "interested": sorted(item["id"] for item in body["interested"]),
            "going": sorted(item["id"] for item in body["going"]),
        }

    states = {}
    for name in ("web", "ios", "android"):
        response = await getattr(clients, name).get("/api/v1/community/me", headers=USER_A)
        assert response.status_code == 200, response.text
        states[name] = summary(response.json())
    assert states["web"] == states["ios"] == states["android"] == {
        "saved": [f"event:{to_save['id']}"],
        "hosting": [str(created["id"])],
        "interested": [str(other["id"])],
        "going": [],
    }

    # Android changes the RSVP; web sees it on its next refresh.
    changed = await clients.android.put(
        f"/api/v1/community/events/{other['id']}/rsvp", headers=USER_A, json={"status": "going"}
    )
    assert changed.status_code == 200
    web_state = summary((await clients.web.get("/api/v1/community/me", headers=USER_A)).json())
    assert web_state["going"] == [str(other["id"])]
    assert web_state["interested"] == []
    web_node = next(item for item in await _nearby(clients.web, USER_A) if item["id"] == str(other["id"]))
    assert web_node["rsvp_status"] == "going"


# ---------------------------------------------------------------------------
# Search and filters
# ---------------------------------------------------------------------------


async def test_topic_search_matches_meaning_not_substrings(clients):
    await _create(clients.web, USER_A, "Spanish Conversation Class", event_type="class")
    await _create(clients.web, USER_A, "Calculus Class", event_type="class")
    await _create(clients.web, USER_A, "Saturday Robotics Workshop")
    await _create(clients.web, USER_A, "SAT Math Bootcamp")

    async def titles(query: str) -> set[str]:
        return {item["title"] for item in await _nearby(clients.web, USER_A, q=query)}

    assert await titles("Spanish classes") == {"Spanish Conversation Class"}
    assert await titles("SAT prep") == {"SAT Math Bootcamp"}
    # "classes" means class-like learning: classes and hands-on workshops.
    assert await titles("classes") == {
        "Spanish Conversation Class", "Calculus Class",
        "Saturday Robotics Workshop", "SAT Math Bootcamp",
    }
    assert await titles("calculus") == {"Calculus Class"}
    assert await titles("robot workshop") == {"Saturday Robotics Workshop"}


async def test_filters_combine(clients):
    now = datetime.now(timezone.utc)
    later_today = now + timedelta(minutes=30)
    await _create(
        clients.web, USER_A, "Tonight free",
        start_time=_iso_z(later_today), end_time=_iso_z(later_today + timedelta(hours=1)),
    )
    await _create(clients.web, USER_A, "Paid next week", days=5, price_type="paid", price_amount=20)
    await _create(clients.web, USER_A, "Free next month", days=20)
    group = await clients.web.post(
        "/api/v1/community/study-groups",
        headers=USER_A,
        json={"name": "Library study pod", "privacy": "public", "latitude": 40.713, "longitude": -74.005},
    )
    assert group.status_code == 201

    async def titles(**params) -> set[str]:
        return {item["title"] for item in await _nearby(clients.web, USER_B, tz="UTC", **params)}

    assert await titles(free_only=True) == {"Tonight free", "Free next month", "Library study pod"}
    assert await titles(when="week") == {"Tonight free", "Paid next week"}
    assert await titles(when="week", free_only=True) == {"Tonight free"}
    # Undated items stay when their category is explicitly requested.
    assert await titles(when="week", categories="study_group,workshop") == {
        "Tonight free", "Paid next week", "Library study pod",
    }
    today = await titles(when="today")
    _, day_end = day_window(timezone.utc)
    if to_naive_utc(later_today) < day_end:
        assert today == {"Tonight free"}


async def test_educational_places_are_parsed_and_filtered(clients, monkeypatch):
    elements = [
        {"type": "node", "id": 1, "lat": 40.7131, "lon": -74.0051,
         "tags": {"amenity": "library", "name": "Midtown Library", "opening_hours": "Mo-Fr 09:00-20:00",
                  "website": "nypl.org", "phone": "+1 212 555 0100", "addr:housenumber": "455",
                  "addr:street": "5th Ave", "addr:city": "New York"}},
        {"type": "way", "id": 2, "center": {"lat": 40.7140, "lon": -74.0060},
         "tags": {"amenity": "university", "name": "City University"}},
        {"type": "node", "id": 3, "lat": 40.7150, "lon": -74.0070,
         "tags": {"amenity": "language_school", "name": "Idiomas Center", "fee": "yes"}},
        {"type": "node", "id": 4, "lat": 40.7150, "lon": -74.0070,
         "tags": {"amenity": "school", "name": "P.S. 1"}},  # K-12 is not public learning space
        {"type": "node", "id": 5, "lat": 999, "lon": 0, "tags": {"amenity": "library", "name": "Bad"}},
        "not-an-element",
    ]
    monkeypatch.setenv("COMMUNITY_OVERPASS_URL", "https://overpass.test/api")

    async def fake_overpass(self, endpoint, query):
        return elements

    monkeypatch.setattr(LearningAroundService, "_overpass", fake_overpass)

    async def places(**params) -> dict:
        items = await _nearby(clients.web, USER_A, include_institutions=True, **params)
        return {item["title"]: item for item in items}

    everything = await places()
    assert set(everything) == {"Midtown Library", "City University", "Idiomas Center"}
    library = everything["Midtown Library"]
    assert library["opening_hours"] == "Mo-Fr 09:00-20:00"
    assert library["website_url"] == "https://nypl.org"
    assert library["address"] == "455 5th Ave, New York"
    assert library["is_free"] is True
    assert library["relevance"]

    schools = await places(categories="educational_center", place_types="university,college")
    assert set(schools) == {"City University"}
    free = await places(free_only=True)
    assert set(free) == {"Midtown Library"}

    detail = await clients.web.get(f"/api/v1/community/nodes/institution/{library['id']}", headers=USER_A)
    assert detail.status_code == 200, detail.text
    assert detail.json()["node"]["title"] == "Midtown Library"
    assert any(item["title"] == "City University" for item in detail.json()["related"])
    # Without the viewer's location, related items carry no misleading distance.
    assert all(item["distance_km"] is None for item in detail.json()["related"])
    near_me = await clients.web.get(
        f"/api/v1/community/nodes/institution/{library['id']}", headers=USER_A, params=NYC
    )
    university = next(item for item in near_me.json()["related"] if item["title"] == "City University")
    assert 0 < university["distance_km"] < 1


async def test_place_provider_outage_is_reported_not_fatal(clients, monkeypatch):
    monkeypatch.setenv("COMMUNITY_OVERPASS_URL", "https://overpass.test/api")

    async def down(self, endpoint, query):
        return None

    monkeypatch.setattr(LearningAroundService, "_overpass", down)
    await _create(clients.web, USER_A, "Still here")
    response = await clients.web.get(
        "/api/v1/community/nearby", headers=USER_A, params={**NYC, "radius_km": 5}
    )
    assert response.status_code == 200
    assert response.json()["degraded_sources"] == ["places"]
    assert [item["title"] for item in response.json()["items"]] == ["Still here"]


async def test_search_resolve_distinguishes_places_and_topics(clients, monkeypatch):
    bronx = PlaceSuggestion(name="The Bronx", label="The Bronx, New York", kind="borough",
                            latitude=40.8448, longitude=-73.8648, radius_km=8.0, is_area=True)
    studio = PlaceSuggestion(name="Yoga Vida", label="Yoga Vida", kind="venue",
                             latitude=40.7, longitude=-74.0, radius_km=2.0, is_area=False)

    async def fake_geocode(text, latitude=None, longitude=None, limit=5):
        lowered = text.lower()
        if "bronx" in lowered:
            return [bronx]
        if "yoga" in lowered:
            return [studio]
        return []

    monkeypatch.setattr(geocoding, "geocode", fake_geocode)

    async def resolve(query: str) -> dict:
        response = await clients.web.get(
            "/api/v1/community/search/resolve", headers=USER_A, params={"q": query, **NYC}
        )
        assert response.status_code == 200, response.text
        return response.json()

    place = await resolve("Bronx")
    assert place["intent"] == "place" and place["place"]["name"] == "The Bronx"
    topic = await resolve("Spanish classes")
    assert topic["intent"] == "topic" and topic["terms"] == ["spanish"]
    assert "class" in topic["categories"]
    mixed = await resolve("coding workshop in the Bronx")
    assert mixed["intent"] == "mixed" and mixed["topic"] == "coding workshop"
    assert (await resolve("yoga"))["intent"] == "topic"
    assert (await resolve("zzqx"))["intent"] == "topic"


def test_query_intent_classification():
    assert classify("Queens").kind == "place"
    assert classify("10451").kind == "place"
    assert classify("SW1A 1AA").kind == "place"
    assert classify("libraries").kind == "topic"
    assert classify("study group").kind == "topic"
    assert classify("coding workshop near Brooklyn").place_text == "Brooklyn"
    topic = parse_topic("libraries")
    assert topic.categories == frozenset({LearningNodeCategory.LIBRARY})
    assert topic.matches(LearningNodeCategory.LIBRARY, "Brooklyn Public")
    assert not parse_topic("sat").matches(LearningNodeCategory.EVENT, "Saturday meetup")
    assert parse_topic("calc").matches(LearningNodeCategory.CLASS, "Calculus review")


def test_photon_payload_parsing():
    payload = {
        "features": [
            {"geometry": {"coordinates": [-73.86, 40.84]},
             "properties": {"name": "The Bronx", "osm_value": "borough", "state": "New York",
                            "extent": [-73.93, 40.92, -73.76, 40.78]}},
            {"geometry": {"coordinates": [-73.9, 40.8]},
             "properties": {"postcode": "10451", "type": "other"}},
            {"geometry": {"coordinates": ["bad"]}, "properties": {"name": "Broken"}},
        ]
    }
    places = geocoding.parse_photon(payload)
    assert [place.name for place in places] == ["The Bronx", "10451"]
    assert places[0].is_area and 5 <= places[0].radius_km <= 15
    assert places[1].kind == "postcode" and places[1].is_area
    assert geocoding.parse_photon({"unexpected": True}) == []


def test_time_and_text_helpers():
    aware = datetime(2026, 9, 26, 18, 0, tzinfo=timezone(timedelta(hours=-4)))
    assert to_naive_utc(aware) == datetime(2026, 9, 26, 22, 0)
    assert as_utc(datetime(2026, 9, 26, 22, 0)).tzinfo == timezone.utc
    assert plain_text("a < b & c") == "a < b & c"
    assert plain_text("&lt;script&gt;x&lt;/script&gt;") == "x"
    with pytest.raises(ValueError):
        safe_web_url("javascript:alert(1)")
    assert safe_web_url("https://lyoai.app/x") == "https://lyoai.app/x"


async def test_analytics_accepts_known_events_and_drops_location(clients, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="lyo_app.community.routes")
    ok = await clients.web.post(
        "/api/v1/community/analytics/events",
        headers=USER_A,
        json={
            "name": "community_filter_selected",
            "platform": "web",
            "properties": {"filter": "free", "latitude": 40.7, "user_location": "home"},
        },
    )
    assert ok.status_code == 204, ok.text
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "community_filter_selected" in logged
    assert "40.7" not in logged and "home" not in logged
    unknown = await clients.web.post(
        "/api/v1/community/analytics/events", headers=USER_A, json={"name": "anything_else"}
    )
    assert unknown.status_code == 422
