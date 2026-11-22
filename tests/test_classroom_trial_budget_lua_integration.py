"""Execute the *actual* Classroom reservation Lua against ephemeral local Redis.

This test deliberately NEVER points to, reads, deletes or modifies the
production/staging Classroom ledger. CI injects a local Redis 8 service.
"""
import asyncio
import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from lyo_app.ai_classroom.trial_budget import _RESERVE_LUA

LOCAL_TEST_URL = os.getenv("LYO_QA_LOCAL_REDIS_URL", "")
allowed_hosts = {"localhost", "127.0.0.1", "::1"}
if LOCAL_TEST_URL and urlsplit(LOCAL_TEST_URL).hostname not in allowed_hosts:
    raise RuntimeError("Atomic Lua QA refuses non-local Redis endpoints")


@pytest.mark.asyncio
async def test_actual_redis_lua_rejects_deleted_expiring_and_corrupt_history():
    if not LOCAL_TEST_URL:
        pytest.skip("Requires explicitly local CI Redis instance")
    import redis.asyncio as redis

    conn = redis.from_url(LOCAL_TEST_URL, decode_responses=True)
    # Always use a distinct QA-only namespace, never the real reservation key.
    key = "qa:lyo:classroom:atomic:" + uuid4().hex
    try:
        ceiling = 70_000_000
        assert await conn.ping()
        assert await conn.eval(_RESERVE_LUA, 1, key, 10_000, ceiling) == -3
        assert await conn.exists(key) == 0  # Missing never starts over at zero.

        await conn.set(key, "123000")
        assert await conn.ttl(key) == -1
        assert await conn.eval(_RESERVE_LUA, 1, key, 1000, ceiling) == 124000

        # Deleting history after successful reservations still fails closed.
        await conn.delete(key)
        assert await conn.eval(_RESERVE_LUA, 1, key, 1000, ceiling) == -3
        assert await conn.exists(key) == 0

        await conn.set(key, "100", ex=60)
        assert await conn.eval(_RESERVE_LUA, 1, key, 1000, ceiling) == -3
        assert await conn.get(key) == "100"

        for invalid in ("oops", "-1", "1.5", "70000001"):
            await conn.set(key, invalid)
            assert await conn.eval(_RESERVE_LUA, 1, key, 1000, ceiling) == -2
            assert await conn.get(key) == invalid

        await conn.set(key, str(ceiling - 2000))
        outcomes = await asyncio.gather(
            *(conn.eval(_RESERVE_LUA, 1, key, 1000, ceiling)
              for _ in range(12))
        )
        assert sorted(outcomes).count(-1) == 10
        assert sorted(value for value in outcomes if value >= 0) == [
            ceiling - 1000, ceiling
        ]
        assert await conn.get(key) == str(ceiling)
        assert await conn.ttl(key) == -1
    finally:
        await conn.delete(key)  # Only a unique, synthetic QA key.
        await conn.aclose()
