"""Serialize a learner's turns across production workers without a schema change."""

from contextlib import asynccontextmanager
from hashlib import blake2b

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@asynccontextmanager
async def learner_session(db, key: str):
    bind = getattr(db, "bind", None)
    if not isinstance(bind, AsyncEngine) or bind.dialect.name != "postgresql":
        # Local SQLite/test sessions are serialized by the engine's async lock.
        yield db
        return

    lock_key = int.from_bytes(blake2b(key.encode(), digest_size=8).digest(), "big", signed=True)
    # Own the connection for the whole turn. A session-level advisory lock
    # survives commits by existing evidence services; a transaction lock would
    # silently release early. This connection is never returned to the pool
    # while locked. No learner text or credentials form the SQL statement.
    async with bind.connect() as connection:
        await connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        await connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": lock_key})
        await connection.commit()
        try:
            async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                yield session
        finally:
            await connection.rollback()
            try:
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                await connection.commit()
            except BaseException:
                # A cancelled/broken connection must not re-enter the pool
                # carrying a session lock. Closing it releases PostgreSQL locks.
                await connection.invalidate()
                raise
