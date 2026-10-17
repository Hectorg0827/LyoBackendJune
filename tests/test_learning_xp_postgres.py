"""PostgreSQL row-lock acceptance for concurrent verified-event retries.

Creates only a disposable schema in the localhost CI database. Never points at
Railway or a production database and never enables PostgreSQL extensions.
"""
import asyncio
import os
import uuid

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from lyo_app.auth.models import User
from lyo_app.core.database import Base
from lyo_app.events.models import EventType, LearningEvent
from lyo_app.events.processor import _award_verified_learning_xp
from lyo_app.gamification.models import Achievement, UserAchievement, UserXP, UserLevel, Streak
from lyo_app.tenants.models import Organization


@pytest.mark.asyncio
async def test_concurrent_checkpoint_retries_keep_ledger_level_and_streak_consistent():
    value = os.getenv("COMMUNITY_POSTGRES_URL")
    if not value:
        pytest.skip("Requires the isolated PostgreSQL CI service")
    url = make_url(value)
    if url.host not in ("localhost", "127.0.0.1") or url.username != "testuser":
        pytest.fail("Concurrent XP acceptance requires the localhost CI testuser database")
    url = url.set(drivername="postgresql+asyncpg")
    admin = create_async_engine(url, poolclass=NullPool)
    schema = "launch_xp_" + uuid.uuid4().hex
    engine = create_async_engine(url, poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        tables = [model.__table__ for model in (
            Organization, User, LearningEvent, Achievement, UserAchievement, UserXP, UserLevel, Streak,
        )]
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
        async with sessions() as db:
            db.add(Organization(id=1, name="XP concurrency test", slug="xp-concurrency"))
            user = User(username="concurrency-test", email="concurrency@example.test", hashed_password="not-a-login")
            db.add(user)
            await db.flush()
            user_id = user.id
            events = [LearningEvent(user_id=user_id, event_type=EventType.CLASSROOM_DEMONSTRATION,
                source_surface="classroom", measurable_outcome=1.0, evidence_confidence=0.9) for _ in range(2)]
            db.add_all(events)
            await db.commit()
            first, second = [event.id for event in events]

        async def award(event_id):
            async with sessions() as db:
                event = await db.get(LearningEvent, event_id)
                return await _award_verified_learning_xp(db, event)

        # Retry the same checkpoint while a second distinct checkpoint arrives.
        results = await asyncio.gather(award(first), award(first), award(second))
        assert sorted(results) == [False, True, True]
        async with sessions() as db:
            ledger = (await db.execute(select(UserXP).where(UserXP.user_id == user_id))).scalars().all()
            level = (await db.execute(select(UserLevel).where(UserLevel.user_id == user_id))).scalar_one()
            streak = (await db.execute(select(Streak).where(Streak.user_id == user_id))).scalar_one()
            assert len(ledger) == 2
            assert {row.context_id for row in ledger} == {first, second}
            assert sum(row.xp_earned for row in ledger) == level.total_xp == 40
            assert streak.current_count == streak.longest_count == 1
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()
