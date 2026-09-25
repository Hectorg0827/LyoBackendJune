"""Private-event invitations: links, direct invites, and the guest list.

A private event is invisible to everyone but its host until the host lets
someone in, by an invite link or by name. These tests drive the real router
as two or three different accounts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from lyo_app.auth.jwt_auth import get_current_user as jwt_current_user
from lyo_app.auth.models import User
from lyo_app.auth.routes import get_current_user
from lyo_app.community.learning_around import LearningAroundService
from lyo_app.community.models import (
    CommunityEventGuest,
    CommunityEventInvite,
    EventAttendance,
)
from lyo_app.community.routes import router as community_router
from lyo_app.core.database import get_db
from lyo_app.routers.search import router as search_router

HOST = {"X-Test-User": "101"}
GUEST = {"X-Test-User": "202"}
STRANGER = {"X-Test-User": "303"}
NYC = {"lat": 40.7128, "lng": -74.0060}
BASE = "/api/v1/community"


@pytest.fixture(autouse=True)
def _no_external_providers(monkeypatch):
    monkeypatch.setenv("COMMUNITY_OVERPASS_URL", "")
    monkeypatch.setenv("COMMUNITY_GEOCODER_URL", "")
    monkeypatch.setenv("COMMUNITY_WEB_URL", "https://lyoai.app")
    LearningAroundService._poi_cache.clear()
    LearningAroundService._place_index.clear()


@pytest_asyncio.fixture
async def api(db_session):
    for user_id, username, first in ((101, "host", "Hana"), (202, "guest", "Gabe"), (303, "stranger", "Sam")):
        db_session.add(
            User(
                id=user_id,
                email=f"{username}@lyoai.app",
                username=username,
                hashed_password="x",
                first_name=first,
                last_name="Tester",
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
    await db_session.commit()

    app = FastAPI()
    app.include_router(community_router, prefix=BASE)
    app.include_router(search_router, prefix="/api/v1")

    async def override_get_db():
        yield db_session

    async def override_current_user(x_test_user: int = Header(101)):
        return SimpleNamespace(id=x_test_user)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[jwt_current_user] = override_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(client=client, db=db_session)


def _message(response) -> str:
    """The learner-facing reason, from FastAPI's shape or the app's envelope."""
    body = response.json()
    return body.get("detail") or body["error"]["message"]


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _private_event(client: AsyncClient, title: str = "Private robotics lab", **overrides) -> dict:
    start = datetime.now(timezone.utc) + timedelta(days=2)
    payload = {
        "title": title,
        "event_type": "workshop",
        "location": "Midtown Library",
        "latitude": 40.7130,
        "longitude": -74.0050,
        "start_time": _iso_z(start),
        "end_time": _iso_z(start + timedelta(hours=2)),
        "timezone": "America/New_York",
        "visibility": "private",
    }
    payload.update(overrides)
    response = await client.post(f"{BASE}/events", headers=HOST, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _link(client: AsyncClient, event_id: int, **options) -> dict:
    response = await client.post(f"{BASE}/events/{event_id}/invites", headers=HOST, json=options or None)
    assert response.status_code == 201, response.text
    return response.json()


async def _nearby_keys(client: AsyncClient, headers: dict) -> set[str]:
    response = await client.get(
        f"{BASE}/nearby",
        headers=headers,
        params={**NYC, "radius_km": 10, "include_institutions": False},
    )
    assert response.status_code == 200, response.text
    return {item["key"] for item in response.json()["items"]}


@pytest.mark.asyncio
async def test_invite_link_lets_a_guest_into_a_private_event(api):
    client = api.client
    event = await _private_event(client)
    key = f"event:{event['id']}"

    # Before an invite: invisible to everyone but the host.
    assert (await client.get(f"{BASE}/nodes/event/{event['id']}", headers=GUEST)).status_code == 404
    assert key not in await _nearby_keys(client, GUEST)
    assert key in await _nearby_keys(client, HOST)

    link = await _link(client, event["id"])
    assert link["url"] == f"https://lyoai.app/community/invite/{link['token']}"
    assert link["active"] is True and link["use_count"] == 0
    assert len(link["token"]) >= 40

    preview = await client.get(f"{BASE}/invites/{link['token']}", headers=GUEST)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["status"] == "valid" and body["title"] == "Private robotics lab"
    assert body["already_guest"] is False and body["is_host"] is False
    assert body["host"]["name"] == "Hana Tester"

    accepted = await client.post(f"{BASE}/invites/{link['token']}/accept", headers=GUEST)
    assert accepted.status_code == 200, accepted.text
    node = accepted.json()
    assert node["key"] == key and node["is_invited"] is True and node["rsvp_status"] is None

    # Now the guest can open it, find it on the map, and RSVP to it.
    assert (await client.get(f"{BASE}/nodes/event/{event['id']}", headers=GUEST)).status_code == 200
    assert key in await _nearby_keys(client, GUEST)
    me = (await client.get(f"{BASE}/me", headers=GUEST)).json()
    assert [n["key"] for n in me["invited"]] == [key]

    rsvp = await client.put(f"{BASE}/events/{event['id']}/rsvp", headers=GUEST, json={"status": "going"})
    assert rsvp.status_code == 200, rsvp.text
    me = (await client.get(f"{BASE}/me", headers=GUEST)).json()
    assert me["invited"] == [] and [n["key"] for n in me["going"]] == [key]

    # Accepting again (another device) changes nothing.
    again = await client.post(f"{BASE}/invites/{link['token']}/accept", headers=GUEST)
    assert again.status_code == 200
    listing = (await client.get(f"{BASE}/events/{event['id']}/invites", headers=HOST)).json()
    assert listing["links"][0]["use_count"] == 1
    assert [(g["user"]["id"], g["source"], g["rsvp_status"]) for g in listing["guests"]] == [
        (202, "link", "going")
    ]

    # Still hidden from someone who was never invited.
    assert (await client.get(f"{BASE}/nodes/event/{event['id']}", headers=STRANGER)).status_code == 404
    assert key not in await _nearby_keys(client, STRANGER)


@pytest.mark.asyncio
async def test_revoked_expired_and_used_up_links_stop_working(api):
    client = api.client
    event = await _private_event(client)

    single = await _link(client, event["id"], max_uses=1)
    assert (await client.post(f"{BASE}/invites/{single['token']}/accept", headers=GUEST)).status_code == 200
    used_up = await client.post(f"{BASE}/invites/{single['token']}/accept", headers=STRANGER)
    assert used_up.status_code == 409
    assert "used as many times" in _message(used_up)
    preview = (await client.get(f"{BASE}/invites/{single['token']}", headers=STRANGER)).json()
    assert preview["status"] == "used_up"

    revoked = await _link(client, event["id"])
    gone = await client.delete(f"{BASE}/events/{event['id']}/invites/{revoked['id']}", headers=HOST)
    assert gone.status_code == 204
    refused = await client.post(f"{BASE}/invites/{revoked['token']}/accept", headers=STRANGER)
    assert refused.status_code == 409 and "turned off" in _message(refused)

    expired = await _link(client, event["id"])
    row = (
        await api.db.execute(select(CommunityEventInvite).where(CommunityEventInvite.id == expired["id"]))
    ).scalar_one()
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    await api.db.commit()
    late = await client.post(f"{BASE}/invites/{expired['token']}/accept", headers=STRANGER)
    assert late.status_code == 409 and "expired" in _message(late)

    # The guest who joined through the first link keeps their access.
    assert (await client.get(f"{BASE}/nodes/event/{event['id']}", headers=GUEST)).status_code == 200
    listing = (await client.get(f"{BASE}/events/{event['id']}/invites", headers=HOST)).json()
    assert [link["active"] for link in listing["links"]] == [False, False, False]


@pytest.mark.asyncio
async def test_only_the_host_manages_invitations(api):
    client = api.client
    event = await _private_event(client)
    link = await _link(client, event["id"])

    assert (await client.post(f"{BASE}/events/{event['id']}/invites", headers=GUEST)).status_code == 403
    assert (await client.get(f"{BASE}/events/{event['id']}/invites", headers=GUEST)).status_code == 403
    assert (
        await client.delete(f"{BASE}/events/{event['id']}/invites/{link['id']}", headers=GUEST)
    ).status_code == 403
    assert (
        await client.post(f"{BASE}/events/{event['id']}/guests", headers=GUEST, json={"user_id": 303})
    ).status_code == 403
    assert (await client.post(f"{BASE}/events/999999/invites", headers=HOST)).status_code == 404
    assert (await client.get(f"{BASE}/invites/{'x' * 43}", headers=GUEST)).status_code == 404
    assert (await client.post(f"{BASE}/invites/{'x' * 43}/accept", headers=GUEST)).status_code == 404


@pytest.mark.asyncio
async def test_direct_invite_notifies_and_removal_takes_access_away(api):
    from lyo_app.routers.notifications import Notification

    client = api.client
    event = await _private_event(client, title="Private chemistry night")
    key = f"event:{event['id']}"

    invited = await client.post(f"{BASE}/events/{event['id']}/guests", headers=HOST, json={"user_id": 202})
    assert invited.status_code == 201, invited.text
    assert invited.json()["user"]["name"] == "Gabe Tester" and invited.json()["source"] == "direct"
    # Inviting the same person twice is harmless and does not notify twice.
    assert (
        await client.post(f"{BASE}/events/{event['id']}/guests", headers=HOST, json={"user_id": 202})
    ).status_code == 201
    notes = (
        await api.db.execute(select(Notification).where(Notification.user_id == 202))
    ).scalars().all()
    assert [(n.type, n.target_id) for n in notes] == [("event_invite", str(event["id"]))]
    assert "Private chemistry night" in notes[0].body

    me = (await client.get(f"{BASE}/me", headers=GUEST)).json()
    assert [n["key"] for n in me["invited"]] == [key]
    assert (
        await client.put(f"{BASE}/events/{event['id']}/rsvp", headers=GUEST, json={"status": "interested"})
    ).status_code == 200

    assert (
        await client.post(f"{BASE}/events/{event['id']}/guests", headers=HOST, json={"user_id": 101})
    ).status_code == 409
    assert (
        await client.post(f"{BASE}/events/{event['id']}/guests", headers=HOST, json={"user_id": 99999})
    ).status_code == 404

    removed = await client.delete(f"{BASE}/events/{event['id']}/guests/202", headers=HOST)
    assert removed.status_code == 204
    assert (await client.get(f"{BASE}/nodes/event/{event['id']}", headers=GUEST)).status_code == 404
    rsvps = (
        await api.db.execute(select(EventAttendance).where(EventAttendance.user_id == 202))
    ).scalars().all()
    assert rsvps == []
    me = (await client.get(f"{BASE}/me", headers=GUEST)).json()
    assert me["invited"] == [] and me["interested"] == []
    assert (await client.delete(f"{BASE}/events/{event['id']}/guests/202", headers=HOST)).status_code == 404


@pytest.mark.asyncio
async def test_unlisted_events_join_the_guests_map_after_accepting(api):
    client = api.client
    event = await _private_event(client, title="Unlisted study hall", visibility="unlisted")
    key = f"event:{event['id']}"
    # Unlisted: anyone with the event link can open it, but it is not on the map.
    assert (await client.get(f"{BASE}/nodes/event/{event['id']}", headers=GUEST)).status_code == 200
    assert key not in await _nearby_keys(client, GUEST)
    link = await _link(client, event["id"])
    assert (await client.post(f"{BASE}/invites/{link['token']}/accept", headers=GUEST)).status_code == 200
    assert key in await _nearby_keys(client, GUEST)


@pytest.mark.asyncio
async def test_ended_or_cancelled_events_take_no_new_guests(api):
    client = api.client
    event = await _private_event(client)
    link = await _link(client, event["id"])
    cancelled = await client.patch(f"{BASE}/events/{event['id']}", headers=HOST, json={"status": "cancelled"})
    assert cancelled.status_code == 200, cancelled.text
    preview = (await client.get(f"{BASE}/invites/{link['token']}", headers=GUEST)).json()
    assert preview["status"] == "cancelled"
    refused = await client.post(f"{BASE}/invites/{link['token']}/accept", headers=GUEST)
    assert refused.status_code == 409
    assert (await client.post(f"{BASE}/events/{event['id']}/invites", headers=HOST)).status_code == 409


@pytest.mark.asyncio
async def test_deleting_an_event_removes_its_links_and_guests(api):
    client = api.client
    event = await _private_event(client)
    link = await _link(client, event["id"])
    assert (await client.post(f"{BASE}/invites/{link['token']}/accept", headers=GUEST)).status_code == 200
    assert (await client.delete(f"{BASE}/events/{event['id']}", headers=HOST)).status_code == 204
    invites = (await api.db.execute(select(CommunityEventInvite))).scalars().all()
    guests = (await api.db.execute(select(CommunityEventGuest))).scalars().all()
    assert invites == [] and guests == []
    assert (await client.get(f"{BASE}/invites/{link['token']}", headers=GUEST)).status_code == 404


@pytest.mark.asyncio
async def test_search_never_reveals_private_or_unlisted_events(api):
    client = api.client
    await _private_event(client, title="Secret origami circle")
    await _private_event(client, title="Hidden origami workshop", visibility="unlisted")
    await _private_event(client, title="Open origami meetup", visibility="public")

    def titles(response) -> list[str]:
        assert response.status_code == 200, response.text
        return sorted(event["title"] for event in response.json()["events"])

    stranger = await client.get("/api/v1/search", headers=STRANGER, params={"q": "origami", "type": "events"})
    assert titles(stranger) == ["Open origami meetup"]
    host = await client.get("/api/v1/search", headers=HOST, params={"q": "origami", "type": "events"})
    assert titles(host) == ["Hidden origami workshop", "Open origami meetup", "Secret origami circle"]
