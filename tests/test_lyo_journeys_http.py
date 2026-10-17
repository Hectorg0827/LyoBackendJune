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


@pytest.mark.asyncio
async def test_asgi_study_session_round_trip_is_scoped_and_persistent():
    """Exercise the public authenticated contract with actual scheduled session rows.

    These are deliberately database-owned fixtures, not a fake exam question or
    model-generated grade. Each HTTP request obtains a new database session.
    """
    from datetime import date, datetime, timedelta

    from lyo_app.study_plans.models import StudyPlan, StudySession, TestProfile

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
            for table in (
                LearningGoal.__table__, TestProfile.__table__, StudyPlan.__table__,
                StudySession.__table__, LearningJourney.__table__, JourneyHandoff.__table__,
            ):
                await conn.run_sync(table.create)

        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add(LearningGoal(
                id="goal-exam-7", user_id=7, goal_type="test",
                title="Biology final", subject="Biology", status="active",
                desired_outcome={}, constraints={},
                source_ref_type="test_profile", source_ref_id="exam-7",
            ))
            for exam_id, owner in (("exam-7", 7), ("exam-other", 7), ("exam-foreign", 8)):
                db.add(TestProfile(
                    id=exam_id, user_id=owner, subject="Biology",
                    test_date=date.today() + timedelta(days=12),
                ))
                db.add(StudyPlan(id="plan-" + exam_id, test_profile_id=exam_id, user_id=owner))
                db.add(StudySession(
                    id="session-" + exam_id, user_id=owner,
                    study_plan_id="plan-" + exam_id, topic="Cell structure",
                    session_type="practice", scheduled_at=datetime.utcnow(),
                    duration_minutes=15,
                ))
            await db.commit()

        root = "/api/v1/me/coach/journeys"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            def start_payload(session_id):
                return {
                    "request_id": "session-start-" + session_id,
                    "goal_id": "goal-exam-7",
                    "origin_surface": "test_prep",
                    "origin_ref": "exam-7",
                    "context": {
                        "test_profile_id": "exam-7",
                        "study_session_id": session_id,
                    },
                }

            for wrong in ("session-exam-other", "session-exam-foreign", "session-missing"):
                rejection = await client.post(root, json=start_payload(wrong))
                assert rejection.status_code == 422, rejection.text

            started = await client.post(root, json=start_payload("session-exam-7"))
            assert started.status_code == 201, started.text
            journey = started.json()
            assert journey["revision"] == 0
            assert journey["context"]["study_session_id"] == "session-exam-7"
            url = f"{root}/{journey['id']}"

            duplicate = await client.post(root, json=start_payload("session-exam-7"))
            assert duplicate.status_code == 201
            assert duplicate.json()["id"] == journey["id"]

            entered = await client.post(f"{url}/handoffs", json={
                "request_id": "session-enter-classroom",
                "expected_revision": 0,
                "target_surface": "classroom",
                "target_ref": "cell-structure",
                "context": {"concept_id": "cell-structure"},
            })
            assert entered.status_code == 201, entered.text
            assert entered.json()["context"]["study_session_id"] == "session-exam-7"

            # This HTTP GET reads through a new AsyncSession, after the commit.
            reloaded = await client.get(url)
            assert reloaded.status_code == 200
            assert reloaded.json()["active_surface"] == "classroom"
            assert reloaded.json()["revision"] == 1
            assert reloaded.json()["context"]["test_profile_id"] == "exam-7"
            assert reloaded.json()["context"]["study_session_id"] == "session-exam-7"

            invalid_switch = await client.post(f"{url}/handoffs", json={
                "request_id": "session-switch-foreign",
                "expected_revision": 1,
                "target_surface": "test_prep",
                "target_ref": "exam-7",
                "context": {"study_session_id": "session-exam-foreign"},
            })
            assert invalid_switch.status_code == 422
            assert (await client.get(url)).json()["revision"] == 1

            returned = await client.post(f"{url}/handoffs", json={
                "request_id": "session-return-test-prep",
                "expected_revision": 1,
                "target_surface": "test_prep",
                "target_ref": "exam-7",
            })
            assert returned.status_code == 201, returned.text
            assert returned.json()["context"]["study_session_id"] == "session-exam-7"

            after_reload = await client.get(url)
            assert after_reload.json()["active_surface"] == "test_prep"
            assert after_reload.json()["revision"] == 2
            assert after_reload.json()["context"]["test_profile_id"] == "exam-7"
            assert after_reload.json()["context"]["study_session_id"] == "session-exam-7"

            history = await client.get(f"{url}/handoffs")
            assert history.status_code == 200
            assert [e["revision"] for e in history.json()] == [1, 2]

            actor["id"] = 8
            assert (await client.get(url)).status_code == 404
            assert (await client.get(f"{url}/handoffs")).status_code == 404

        # Navigation cannot silently mark practice complete or award a score.
        async with AsyncSession(engine, expire_on_commit=False) as db:
            from sqlalchemy import select

            row = (await db.execute(
                select(StudySession).where(StudySession.id == "session-exam-7")
            )).scalar_one()
            assert row.status == "scheduled"
            assert row.performance_score is None
    finally:
        await engine.dispose()
