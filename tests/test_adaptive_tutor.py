"""
Adaptive-tutor wiring tests (7-pillar parity + leapfrog wedges).

These assert the *wiring/structure* of the adaptive tutor — that the learner
model reaches the tutoring path, difficulty adapts to mastery, etc. They do not
assert LLM output quality (that needs live API keys; validated on staging).

Each test boots the real app on the shared temp-file DB from conftest.py.
"""

import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long-xx")

import asyncio
import pytest
from starlette.testclient import TestClient


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
    body = client.post("/auth/login", json={
        "email": email, "password": "SweepPass123!"}).json()
    return {"Authorization": f"Bearer {body['access_token']}", "X-Forwarded-For": ip}, body["user"]["id"]


async def _seed_learner(uid, *, affect="frustrated", masteries=None):
    """Seed a LearnerState + LearnerMastery rows for a user."""
    from lyo_app.core.database import AsyncSessionLocal
    from lyo_app.personalization.models import LearnerState, LearnerMastery, AffectState
    async with AsyncSessionLocal() as db:
        db.add(LearnerState(
            user_id=uid, current_affect=AffectState(affect),
            fatigue_level=0.4, focus_level=0.6, reading_level=9,
            preferred_pace="moderate",
        ))
        for skill_id, level in (masteries or {}).items():
            db.add(LearnerMastery(user_id=uid, skill_id=skill_id, mastery_level=level))
        await db.commit()


# ---------------------------------------------------------------- Pillar A
def test_build_prompt_context_returns_learner_profile_without_greenlet(client):
    """The keystone: the learner model assembles into a prompt block safely."""
    _, uid = _auth(client, "at_a@x.com", "at_alice", "10.70.0.1")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, affect="frustrated",
        masteries={"linear_equations": 0.85, "quadratics": 0.2, "fractions": 0.5},
    ))

    async def _build():
        from lyo_app.core.database import AsyncSessionLocal
        from lyo_app.personalization.service import personalization_engine
        async with AsyncSessionLocal() as db:
            return await personalization_engine.build_prompt_context(
                db, str(uid), current_skill="quadratics")

    ctx = asyncio.get_event_loop().run_until_complete(_build())
    assert ctx, "expected a non-empty learner context"
    assert "quadratics" in ctx                 # struggling skill surfaced
    assert "linear_equations" in ctx           # mastered skill surfaced
    assert "frustrated" in ctx                 # affect surfaced
    assert "mastery" in ctx.lower()            # readiness line present


def test_greeting_injects_learner_context(client):
    """GET /chat/greeting reports context_used=True once the learner has state."""
    headers, uid = _auth(client, "at_g@x.com", "at_greet", "10.70.0.2")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, masteries={"quadratics": 0.2}))
    r = client.get("/api/v1/chat/greeting", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json().get("context_used") is True


# ---------------------------------------------------------------- Pillar C / Wedge 3 (emotional)
def test_coaching_directive_varies_by_affect():
    """The emotional layer maps affect -> an explicit tutoring instruction."""
    from lyo_app.personalization.service import personalization_engine as pe
    frustrated = pe.coaching_directive("frustrated", fatigue=0.2)
    bored = pe.coaching_directive("bored", fatigue=0.2)
    flow = pe.coaching_directive("flow", fatigue=0.2)
    assert "encourag" in frustrated.lower() and "worked example" in frustrated.lower()
    assert "concise" in bored.lower()
    assert "momentum" in flow.lower()
    assert frustrated != bored != flow
    # fatigue rider appends a break suggestion
    tired = pe.coaching_directive("engaged", fatigue=0.85)
    assert "break" in tired.lower()


def test_coaching_directive_injected_into_prompt_context(client):
    """A frustrated learner's context must carry the coaching directive."""
    _, uid = _auth(client, "at_e@x.com", "at_emo", "10.70.0.4")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, affect="frustrated", masteries={"quadratics": 0.2}))

    async def _build():
        from lyo_app.core.database import AsyncSessionLocal
        from lyo_app.personalization.service import personalization_engine
        async with AsyncSessionLocal() as db:
            return await personalization_engine.build_prompt_context(db, str(uid))

    ctx = asyncio.get_event_loop().run_until_complete(_build())
    assert "Coaching directive:" in ctx


# ---------------------------------------------------------------- Wedge 1 (identity)
def test_learning_identity_endpoint(client):
    """GET /api/v1/me/identity composes mastery + memory + goals + arc, no 500."""
    headers, uid = _auth(client, "at_i@x.com", "at_ident", "10.70.0.5")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, affect="engaged",
        masteries={"linear_equations": 0.9, "quadratics": 0.2, "fractions": 0.55}))
    r = client.get("/api/v1/me/identity", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # The durable identity surface: heatmap + strengths/gaps + arc always present,
    # even if memory/goals subsystems are empty for a fresh user.
    assert "mastery_heatmap" in body
    assert "strengths" in body and "weaknesses" in body
    assert "active_goals" in body and isinstance(body["active_goals"], list)
    assert "learning_arc" in body
    assert "summary" in body["learning_arc"]
    assert body["learning_arc"]["skills_mastered"] >= 1  # linear_equations mastered


def test_chat_endpoint_personalization_path_no_500(client):
    """POST /chat runs the re-enabled personalization path without 500.

    (No API key in tests -> the AI layer returns a graceful fallback, but the
    personalization wiring must not raise.)
    """
    headers, uid = _auth(client, "at_c@x.com", "at_chat", "10.70.0.3")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, masteries={"quadratics": 0.2}))
    r = client.post("/api/v1/chat", headers=headers,
                    json={"message": "Help me understand quadratics"})
    assert r.status_code == 200, r.text
