"""
End-to-end tests for the collaborative-learning feature.

Exercises the full lifecycle (study groups, membership, peer interactions,
sessions, mentorship, assessment, analytics) against the booted app so the
engine and its route contract can't silently regress.
"""

import os
from datetime import datetime, timedelta

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long-xx")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import asyncio
import pytest
from starlette.testclient import TestClient

B = "/api/v1/collaboration"


@pytest.fixture(scope="module")
def client():
    import lyo_app.enhanced_main as m
    from lyo_app.core.database import init_db
    asyncio.get_event_loop().run_until_complete(init_db())
    return TestClient(m.app, raise_server_exceptions=False)


def _auth(client, email, username, ip):
    """Returns (headers, user_id). The shared test DB means user ids are not
    guaranteed to be 1/2, so callers must use the returned id."""
    client.post("/auth/register", json={
        "email": email, "username": username, "password": "SweepPass123!",
        "confirm_password": "SweepPass123!", "first_name": username})
    body = client.post("/auth/login", json={
        "email": email, "password": "SweepPass123!"}).json()
    uid = body["user"]["id"]
    return {"Authorization": f"Bearer {body['access_token']}", "X-Forwarded-For": ip}, uid


def test_collaboration_full_lifecycle(client):
    alice, alice_id = _auth(client, "ca@x.com", "calice", "10.20.0.1")
    bob, bob_id = _auth(client, "cb@x.com", "cbob", "10.20.0.2")

    # --- study groups ---
    r = client.post(f"{B}/groups", headers=alice, json={
        "title": "Python Crew", "subject_area": "Python",
        "collaboration_type": "study_group", "max_members": 5})
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    assert r.json()["current_member_count"] == 1

    assert client.get(f"{B}/groups", headers=alice).status_code == 200
    assert client.get(f"{B}/groups/{gid}", headers=alice).status_code == 200
    assert client.put(f"{B}/groups/{gid}", headers=alice,
                      json={"description": "updated"}).status_code == 200
    assert client.post(f"{B}/groups/{gid}/join", headers=bob).status_code == 200
    members = client.get(f"{B}/groups/{gid}/members", headers=alice)
    assert members.status_code == 200 and len(members.json()) == 2
    assert client.post(f"{B}/matching/recommendations", headers=bob,
                       json={"subject_areas": ["Python"]}).status_code == 200

    # --- interactions (group broadcast question has no recipient) ---
    r = client.post(f"{B}/interactions", headers=alice, json={
        "group_id": gid, "interaction_type": "question",
        "content": "How do decorators work in Python?", "context_skill_id": "py-dec"})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert client.get(f"{B}/interactions?group_id={gid}", headers=alice).status_code == 200
    assert client.post(f"{B}/interactions/{iid}/respond?response_content=They+wrap+functions",
                       headers=bob).status_code == 200
    assert client.post(f"{B}/interactions/{iid}/rate?helpfulness_rating=4.5&accuracy_rating=5.0",
                       headers=alice).status_code == 200

    # --- sessions ---
    start = (datetime.utcnow() + timedelta(days=1)).isoformat()
    end = (datetime.utcnow() + timedelta(days=1, hours=1)).isoformat()
    r = client.post(f"{B}/sessions", headers=alice, json={
        "group_id": gid, "title": "Decorators Workshop", "session_type": "study_session",
        "scheduled_start": start, "scheduled_end": end})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert client.post(f"{B}/sessions/{sid}/join", headers=bob).status_code == 200
    assert client.post(f"{B}/sessions/{sid}/start", headers=alice).status_code == 200
    assert client.post(f"{B}/sessions/{sid}/end", headers=alice).status_code == 200

    # --- mentorship ---
    r = client.post(f"{B}/mentorship", headers=bob, json={"mentor_id": alice_id, "skill_focus": ["Python"]})
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    assert r.json()["status"] == "pending"
    assert client.post(f"{B}/mentorship/{mid}/accept", headers=alice).status_code == 200
    assert client.post(f"{B}/mentorship/{mid}/complete", headers=alice).status_code == 200

    # --- assessment ---
    assert client.post(f"{B}/assessment", headers=alice, json={
        "assessee_id": bob_id, "skill_id": "py-dec", "assessment_context": "workshop",
        "skill_demonstration": "explained well", "mastery_rating": 0.8,
        "confidence_rating": 0.7}).status_code == 200
    assert client.get(f"{B}/assessment/received", headers=bob).status_code == 200
    assert client.get(f"{B}/assessment/given", headers=alice).status_code == 200

    # --- analytics ---
    assert client.get(f"{B}/analytics/personal", headers=alice).status_code == 200
    assert client.get(f"{B}/analytics/group/{gid}", headers=alice).status_code == 200
    assert client.get(f"{B}/leaderboard/contributors", headers=alice).status_code == 200
    assert client.get(f"{B}/insights/learning-network", headers=alice).status_code == 200


def test_collaboration_authorization(client):
    """Non-creator cannot update a group; non-member analytics is blocked."""
    alice, _ = _auth(client, "cc@x.com", "ccalice", "10.20.1.1")
    mallory, _ = _auth(client, "cm@x.com", "cmallory", "10.20.1.2")
    gid = client.post(f"{B}/groups", headers=alice, json={
        "title": "Private Crew", "subject_area": "Math",
        "collaboration_type": "study_group"}).json()["id"]
    assert client.put(f"{B}/groups/{gid}", headers=mallory,
                      json={"description": "hijack"}).status_code == 403
    assert client.get(f"{B}/analytics/group/{gid}", headers=mallory).status_code == 403
