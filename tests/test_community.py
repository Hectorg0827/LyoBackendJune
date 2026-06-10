"""
End-to-end tests for the community feature (study groups, events, social posts).

Covers the lifecycle that previously 500'd across the board due to
route<->service method mismatches and missing model columns.
"""

import os
from datetime import datetime, timedelta

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long-xx")
# DATABASE_URL is pinned to a persistent temp-file SQLite by tests/conftest.py
# (the app's NullPool makes ":memory:" non-persistent across requests).

import asyncio
import pytest
from starlette.testclient import TestClient

B = "/community"


@pytest.fixture(scope="module")
def client():
    import lyo_app.enhanced_main as m
    from lyo_app.core.database import init_db
    asyncio.get_event_loop().run_until_complete(init_db())
    return TestClient(m.app, raise_server_exceptions=False)


def _auth(client, email, username, ip):
    client.post("/auth/register", json={
        "email": email, "username": username, "password": "SweepPass123!",
        "confirm_password": "SweepPass123!", "first_name": username})
    tok = client.post("/auth/login", json={
        "email": email, "password": "SweepPass123!"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "X-Forwarded-For": ip}


def test_community_groups_events_posts(client):
    wendy = _auth(client, "wa@x.com", "wcwendy", "10.30.0.1")
    will = _auth(client, "wb@x.com", "wcwill", "10.30.0.2")

    # study groups
    r = client.post(f"{B}/study-groups", headers=wendy, json={
        "name": "Algo Club", "description": "DSA study", "subject": "CS"})
    assert r.status_code in (200, 201), r.text
    gid = r.json()["id"]
    assert client.get(f"{B}/study-groups", headers=wendy).status_code == 200
    assert client.post(f"{B}/study-groups/{gid}/join", headers=will).status_code in (200, 201)
    members = client.get(f"{B}/study-groups/{gid}/members", headers=wendy)
    assert members.status_code == 200 and len(members.json()) >= 1
    assert client.get(f"{B}/my-groups", headers=will).status_code == 200

    # events
    start = (datetime.utcnow() + timedelta(days=2)).isoformat()
    end = (datetime.utcnow() + timedelta(days=2, hours=2)).isoformat()
    r = client.post(f"{B}/events", headers=wendy, json={
        "title": "Mock Interview Night", "description": "practice session",
        "event_type": "workshop", "start_time": start, "end_time": end, "location": "Online"})
    assert r.status_code in (200, 201), r.text
    eid = r.json()["id"]
    assert client.get(f"{B}/events", headers=wendy).status_code == 200
    assert client.post(f"{B}/events/{eid}/attend", headers=will).status_code in (200, 201)
    assert client.delete(f"{B}/events/{eid}/attend", headers=will).status_code in (200, 204)
    assert client.get(f"{B}/my-events", headers=wendy).status_code == 200
    assert client.get(f"{B}/stats", headers=wendy).status_code == 200

    # social posts
    r = client.post(f"{B}/posts", headers=wendy, json={
        "content": "Hello community!", "post_type": "text"})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    assert client.get(f"{B}/posts", headers=wendy).status_code == 200
    assert client.get(f"{B}/posts/{pid}", headers=will).status_code == 200
    assert client.post(f"{B}/posts/{pid}/like", headers=will).status_code == 200
    assert client.post(f"{B}/posts/{pid}/comments", headers=will,
                       json={"content": "Nice post!"}).status_code in (200, 201)
    assert client.get(f"{B}/posts/{pid}/comments", headers=wendy).status_code == 200
