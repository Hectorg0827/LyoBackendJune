"""Production PostgreSQL locking, using independent sessions and temporary schema.

Backend CI provides DATABASE_URL. Local runs without PostgreSQL skip only this
module; a missing database in CI is a failure rather than a false green gate.
"""
import asyncio
import os
import uuid
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lyo_app.auth.models import User
from lyo_app.study_plans.models import TestProfile as Profile, StudyPlan, StudySession, SessionReminder, PlanEvent
from lyo_app.study_plans.routes import NewTestStart, prep_state, start_new_test


@pytest.fixture
async def postgres_sessions(db_session):
    # db_session registers the application's related mappers, not the PG data.
    raw_url = os.getenv("TEST_PREP_POSTGRES_URL") or os.getenv("DATABASE_URL", "")
    if not raw_url.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://")):
        if os.getenv("CI"):
            pytest.fail("Multi-exam PostgreSQL release gate requires DATABASE_URL")
        pytest.skip("PostgreSQL URL is not configured")
    url = make_url(raw_url.replace("postgres://", "postgresql://", 1)).set(drivername="postgresql+asyncpg")
    schema = "testprep_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    engine = None
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
        async with engine.begin() as connection:
            await connection.run_sync(Profile.metadata.create_all, tables=[
                User.__table__, Profile.__table__, StudyPlan.__table__, StudySession.__table__,
                SessionReminder.__table__, PlanEvent.__table__,
            ])
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        if engine:
            await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def users(factory, count=1):
    async with factory() as db:
        rows = [User(email=f"learner-{i}@example.test", username=f"learner-{i}", hashed_password="unused")
                for i in range(count)]
        db.add_all(rows)
        await db.commit()
        return [SimpleNamespace(id=row.id) for row in rows]


async def simultaneous_starts(factory, attempts):
    gate = asyncio.Event()

    async def start(user, request_id):
        async with factory() as db:
            await gate.wait()
            return await start_new_test(NewTestStart(request_id=request_id), user, db)

    tasks = [asyncio.create_task(start(*attempt)) for attempt in attempts]
    gate.set()
    return await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_concurrent_same_request_creates_exactly_one_exam(postgres_sessions):
    user = (await users(postgres_sessions))[0]
    results = await simultaneous_starts(postgres_sessions, [(user, "same-key-12345678")] * 6)
    assert sum(row["created"] for row in results) == 1
    assert len({row["profile_id"] for row in results}) == 1
    async with postgres_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Profile)) == 1


@pytest.mark.asyncio
async def test_concurrent_different_requests_create_distinct_exams(postgres_sessions):
    user = (await users(postgres_sessions))[0]
    results = await simultaneous_starts(postgres_sessions, [(user, f"distinct-key-{i:08d}") for i in range(3)])
    assert all(row["created"] for row in results)
    assert len({row["profile_id"] for row in results}) == 3


@pytest.mark.asyncio
async def test_same_request_key_is_scoped_to_its_owner(postgres_sessions):
    owners = await users(postgres_sessions, 2)
    results = await simultaneous_starts(postgres_sessions, [(user, "shared-key-12345678") for user in owners])
    assert all(row["created"] for row in results)
    assert results[0]["profile_id"] != results[1]["profile_id"]
    async with postgres_sessions() as db:
        profiles = (await db.execute(select(Profile))).scalars().all()
        assert {profile.user_id for profile in profiles} == {user.id for user in owners}


@pytest.mark.asyncio
async def test_start_and_retry_preserve_schedule_reminders_and_scores(postgres_sessions):
    user = (await users(postgres_sessions))[0]
    async with postgres_sessions() as db:
        profile = Profile(user_id=user.id, subject="Algebra", test_date=date.today() + timedelta(days=14),
                          intake_complete=True, intake_transcript=[{"role": "user", "content": "Algebra"}])
        db.add(profile)
        await db.flush()
        plan = StudyPlan(user_id=user.id, test_profile_id=profile.id, status="active", total_sessions=2)
        db.add(plan)
        await db.flush()
        completed = StudySession(user_id=user.id, study_plan_id=plan.id, topic="Equations",
            scheduled_at=datetime.utcnow() - timedelta(days=1), duration_minutes=20,
            session_type="practice", status="completed", performance_score=0.8)
        scheduled = StudySession(user_id=user.id, study_plan_id=plan.id, topic="Graphs",
            scheduled_at=datetime.utcnow() + timedelta(days=1), duration_minutes=25,
            session_type="learn", status="scheduled")
        db.add_all([completed, scheduled])
        await db.flush()
        reminder = SessionReminder(user_id=user.id, session_id=scheduled.id,
            fire_at=datetime.utcnow() + timedelta(hours=1), reminder_type="thirty_min", status="pending")
        db.add(reminder)
        await db.commit()
        old_id, plan_id, reminder_id = profile.id, plan.id, reminder.id
        times = {row.id: row.scheduled_at for row in [completed, scheduled]}

    await simultaneous_starts(postgres_sessions, [(user, "preserve-key-12345678")] * 3)
    async with postgres_sessions() as db:
        state = await prep_state(user, db, old_id)
        assert state["plan"].id == plan_id and state["plan"].status == "active"
        assert {row.id: row.scheduled_at for row in state["sessions"]} == times
        saved = {row.id: row for row in state["sessions"]}
        assert saved[completed.id].status == "completed"
        assert float(saved[completed.id].performance_score) == 0.8
        assert saved[scheduled.id].status == "scheduled"
        assert (await db.get(SessionReminder, reminder_id)).status == "pending"
