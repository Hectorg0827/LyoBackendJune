"""ASGI contract tests for authenticated, goal-owned learning handoffs.

SQLAlchemy persistence and retry races are also covered in test_lyo_journeys.
These HTTP tests ensure the public router applies its actual response models,
dependency-based user scoping, and safe status codes.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.coach.journey_models import JourneyHandoff, LearningJourney
from lyo_app.coach.journeys import router as journey_router
from lyo_app.coach.models import LearningGoal


@pytest.mark.asyncio
async def test_asgi_journey_create_read_handoff_return_and_cross_user_isolation():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    actor = {"id": 7}
    app = FastAPI()
    app.include_router(journey_router, prefix="/api/v1/me/coach/journeys")

    async def current_user():
        return SimpleNamespace(id=actor["id"])

    async def db_provider():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = db_provider

    try:
        async with engine.begin() as conn:
            for table in (LearningGoal.__table__, LearningJourney.__table__, JourneyHandoff.__table__):
                await conn.run_sync(table.create)
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(LearningGoal(
                id="goal-exam", user_id=7, goal_type="test",
                title="Chemistry final", subject="Chemistry", status="active",
                desired_outcome={}, constraints={},
                source_surface="test_prep",
                source_ref_type="test_profile",
                source_ref_id="exam-7",
            ))
            await db.commit()

        root = "/api/v1/me/coach/journeys"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(root, json={
                "request_id": "start-journey-0001",
                "goal_id": "goal-exam",
                "origin_surface": "test_prep",
                "origin_ref": "exam-7",
                "context": {"test_profile_id": "exam-7"},
            })
            assert created.status_code == 201, created.text
            j = created.json()
            assert j["revision"] == 0
            assert j["context"]["test_profile_id"] == "exam-7"
            url = f"{root}/{j['id']}"
            handoff = await client.post(f"{url}/handoffs", json={
                "request_id": "handoff-lesson-0001",
                "expected_revision": 0,
                "target_surface": "classroom",
                "target_ref": "bonding",
                "context": {"concept_id": "bonding"},
            })
            assert handoff.status_code == 201, handoff.text
            assert handoff.json()["revision"] == 1

            returned = await client.post(f"{url}/handoffs", json={
                "request_id": "handoff-return-0001",
                "expected_revision": 1,
                "target_surface": "test_prep",
                "target_ref": "exam-7",
                "context": {},
            })
            assert returned.status_code == 201, returned.text

            state = await client.get(url)
            assert state.status_code == 200
            assert state.json()["active_surface"] == "test_prep"
            assert state.json()["context"]["test_profile_id"] == "exam-7"
            assert state.json()["context"]["concept_id"] == "bonding"

            events = await client.get(f"{url}/handoffs")
            assert events.status_code == 200
            assert [x["revision"] for x in events.json()] == [1, 2]

            reused = await client.post(f"{url}/handoffs", json={
                "request_id": "handoff-lesson-0001",
                "expected_revision": 0,
                "target_surface": "classroom",
                "target_ref": "bonding",
                "context": {"concept_id": "bonding"},
            })
            assert reused.status_code == 201
            assert reused.json()["id"] == handoff.json()["id"]

            actor["id"] = 8
            assert (await client.get(url)).status_code == 404
            assert (await client.get(f"{url}/handoffs")).status_code == 404
            assert (await client.post(f"{url}/handoffs", json={
                "request_id": "handoff-foreign-0001",
                "expected_revision": 2,
                "target_surface": "classroom",
                "context": {},
            })).status_code == 404
            assert (await client.get(root)).json() == []
            assert (await client.post(root, json={
                "request_id": "start-foreign-0001",
                "goal_id": "goal-exam",
                "origin_surface": "coach",
                "context": {},
            })).status_code == 404
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_asgi_rejects_invalid_payloads_before_storing_navigation():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    app = FastAPI()
    app.include_router(journey_router, prefix="/api/v1/me/coach/journeys")

    async def user():
        return SimpleNamespace(id=3)

    async def db_provider():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_db] = db_provider

    try:
        async with engine.begin() as conn:
            for table in (LearningGoal.__table__, LearningJourney.__table__, JourneyHandoff.__table__):
                await conn.run_sync(table.create)
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(LearningGoal(
                id="goal-a", user_id=3, goal_type="mastery", title="Music",
                status="active", desired_outcome={}, constraints={},
            ))
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            root = "/api/v1/me/coach/journeys"
            no_grade = await client.post(root, json={
                "request_id": "start-invalid-0001",
                "goal_id": "goal-a",
                "origin_surface": "chat",
                "context": {"new_mastery_score": 1},
            })
            assert no_grade.status_code == 422
            wrong_exam = await client.post(root, json={
                "request_id": "start-invalid-0002",
                "goal_id": "goal-a",
                "origin_surface": "chat",
                "context": {"test_profile_id": "someone-else"},
            })
            assert wrong_exam.status_code == 422
            assert (await client.get(root)).json() == []
    finally:
        await engine.dispose()
