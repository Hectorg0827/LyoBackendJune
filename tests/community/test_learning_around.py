"""Contract tests for map-first Community and cross-device account state."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest_asyncio
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient

from lyo_app.auth.routes import get_current_user
from lyo_app.community.routes import router as community_router
from lyo_app.core.database import get_db


ACCOUNT_ONE = {"X-Test-User": "101"}
ACCOUNT_TWO = {"X-Test-User": "202"}


@pytest_asyncio.fixture
async def community_clients(db_session):
    """Two platform clients sharing one backend database and account identity."""
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
        AsyncClient(transport=transport, base_url="http://ios") as ios,
        AsyncClient(transport=transport, base_url="http://android") as android,
    ):
        yield ios, android


async def test_nearby_returns_geolocated_user_learning_nodes(community_clients):
    ios, _ = community_clients
    group_response = await ios.post(
        "/api/v1/community/study-groups",
        headers=ACCOUNT_ONE,
        json={
            "name": "Brooklyn Biology Study Pod",
            "description": "Weekly human biology review",
            "privacy": "public",
            "location": "Brooklyn Public Library",
            "latitude": 40.6725,
            "longitude": -73.9682,
        },
    )
    assert group_response.status_code == 201, group_response.text

    start = datetime.utcnow() + timedelta(days=1)
    event_response = await ios.post(
        "/api/v1/community/events",
        headers=ACCOUNT_ONE,
        json={
            "title": "AI Beginners Workshop",
            "description": "Build a small classifier together",
            "event_type": "workshop",
            "location": "Central Library Lab",
            "latitude": 40.6730,
            "longitude": -73.9670,
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=2)).isoformat(),
            "timezone": "America/New_York",
        },
    )
    assert event_response.status_code == 201, event_response.text
    assert event_response.json()["latitude"] == 40.6730
    assert event_response.json()["longitude"] == -73.9670

    tutor_response = await ios.post(
        "/api/v1/community/lessons",
        headers=ACCOUNT_ONE,
        json={
            "title": "Biology Tutor Available",
            "description": "One-on-one exam preparation",
            "subject": "Biology",
            "price_per_hour": 25,
            "location": "Prospect Park",
            "latitude": 40.6710,
            "longitude": -73.9700,
        },
    )
    assert tutor_response.status_code == 201, tutor_response.text

    nearby = await ios.get(
        "/api/v1/community/nearby",
        headers=ACCOUNT_ONE,
        params={
            "lat": 40.6728,
            "lng": -73.9680,
            "radius_km": 5,
            "include_institutions": False,
        },
    )
    assert nearby.status_code == 200, nearby.text
    body = nearby.json()
    nodes = {node["title"]: node for node in body["items"]}

    assert nodes["Brooklyn Biology Study Pod"]["category"] == "study_group"
    assert nodes["Brooklyn Biology Study Pod"]["is_joined"] is True
    assert nodes["AI Beginners Workshop"]["category"] == "workshop"
    assert nodes["AI Beginners Workshop"]["is_attending"] is True
    assert nodes["AI Beginners Workshop"]["distance_km"] < 1
    assert nodes["Biology Tutor Available"]["category"] == "tutor"


async def test_saved_nodes_and_memberships_follow_account_not_device(
    community_clients,
):
    ios, android = community_clients
    start = datetime.utcnow() + timedelta(days=1)
    event_response = await ios.post(
        "/api/v1/community/events",
        headers=ACCOUNT_ONE,
        json={
            "title": "Cross-device Photography Class",
            "event_type": "lecture",
            "location": "Photo Lab",
            "latitude": 40.75,
            "longitude": -73.99,
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=1)).isoformat(),
            "timezone": "America/New_York",
        },
    )
    assert event_response.status_code == 201, event_response.text
    event_id = event_response.json()["id"]

    nearby = await ios.get(
        "/api/v1/community/nearby",
        headers=ACCOUNT_ONE,
        params={
            "lat": 40.75,
            "lng": -73.99,
            "radius_km": 2,
            "include_institutions": False,
        },
    )
    snapshot = next(
        node for node in nearby.json()["items"] if node["id"] == str(event_id)
    )
    save_response = await ios.put(
        f"/api/v1/community/saved-nodes/event/{event_id}",
        headers=ACCOUNT_ONE,
        json={"snapshot": snapshot},
    )
    assert save_response.status_code == 200, save_response.text
    assert save_response.json()["is_saved"] is True

    group_response = await ios.post(
        "/api/v1/community/study-groups",
        headers=ACCOUNT_ONE,
        json={
            "name": "Cross-device SAT Study Pod",
            "privacy": "public",
            "is_online": True,
        },
    )
    assert group_response.status_code == 201, group_response.text
    group_id = group_response.json()["id"]

    # A separate platform client reads the same server-owned state without
    # copying local preferences or caches.
    android_state = await android.get(
        "/api/v1/community/me",
        headers=ACCOUNT_ONE,
    )
    assert android_state.status_code == 200, android_state.text
    android_body = android_state.json()
    assert any(node["key"] == f"event:{event_id}" for node in android_body["saved_nodes"])
    assert any(event["id"] == event_id for event in android_body["attending_events"])
    assert any(group["id"] == group_id for group in android_body["joined_groups"])

    # A different account on either platform must not inherit those rows.
    other_state = await android.get(
        "/api/v1/community/me",
        headers=ACCOUNT_TWO,
    )
    assert other_state.status_code == 200, other_state.text
    assert other_state.json()["saved_nodes"] == []
    assert other_state.json()["attending_events"] == []
    assert other_state.json()["joined_groups"] == []


async def test_saved_node_identity_cannot_be_spoofed(community_clients):
    ios, _ = community_clients
    snapshot = {
        "key": "event:1",
        "kind": "event",
        "category": "event",
        "id": "1",
        "title": "Identity test",
        "is_online": False,
        "is_joined": False,
        "is_attending": False,
        "is_saved": False,
        "source": "lyo",
    }
    response = await ios.put(
        "/api/v1/community/saved-nodes/study_group/1",
        headers=ACCOUNT_ONE,
        json={"snapshot": snapshot},
    )
    assert response.status_code == 400
