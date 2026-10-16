"""Regression coverage for reset security and Railway deployment configuration."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from lyo_app.auth import reset_routes as reset
from lyo_app.auth import jwt_auth


@pytest.mark.asyncio
async def test_reset_rate_limit_is_shared_and_fails_closed(monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(side_effect=[1, 5, 6]))
    monkeypatch.setattr(reset.redis_client, "client", redis)
    await reset._enforce_reset_limit("192.0.2.9")
    await reset._enforce_reset_limit("192.0.2.9")
    with pytest.raises(HTTPException) as exhausted:
        await reset._enforce_reset_limit("192.0.2.9")
    assert exhausted.value.status_code == 429
    assert redis.eval.await_count == 3
    assert redis.eval.await_args.args[2] == "pwd-reset:192.0.2.9"
    monkeypatch.setattr(reset.redis_client, "client", None)
    with pytest.raises(HTTPException) as unavailable:
        await reset._enforce_reset_limit("192.0.2.9")
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_redis_failures_cannot_disable_reset_throttle(monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(side_effect=ConnectionError("offline")))
    monkeypatch.setattr(reset.redis_client, "client", redis)
    with pytest.raises(HTTPException) as outage:
        await reset._enforce_reset_limit("192.0.2.9")
    assert outage.value.status_code == 503


@pytest.mark.asyncio
async def test_access_jwt_invalidated_after_epoch_bump_even_if_cached(monkeypatch):
    state = {"version": 0}
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.side_effect = lambda: state["version"]
    session.execute = AsyncMock(return_value=result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr("lyo_app.core.database.AsyncSessionLocal", lambda: cm)
    old = jwt_auth.create_access_token("51", auth_version=0)
    assert (await jwt_auth.verify_token_async(old)).user_id == "51"
    state["version"] = 1
    with pytest.raises(Exception, match="revoked"):
        await jwt_auth.verify_token_async(old)
    new = jwt_auth.create_access_token("51", auth_version=1)
    assert (await jwt_auth.verify_token_async(new)).user_id == "51"


def test_railway_deployment_sender_and_proxy_hardening():
    root = Path(__file__).resolve().parents[1]
    docker = (root / "Dockerfile").read_text()
    assert "forwarded-allow-ips='*'" not in docker
    assert "TRUSTED_PROXY_IPS:-127.0.0.1" in docker
    for script in ("set_railway_vars.sh", "deploy_to_railway.sh"):
        text = (root / script).read_text()
        assert "SMTP_FROM_EMAIL" in text
        assert 'if [ -n "${RESEND_API_KEY:-}" ]' in text

def test_refresh_jwt_widens_beyond_legacy_column_limit():
    from sqlalchemy import Text
    from lyo_app.auth.models import RefreshToken
    token = jwt_auth.create_refresh_token("12345678901234", auth_version=42)
    assert len(token) > 255  # A real token must not fail at DB insert.
    assert isinstance(RefreshToken.__table__.c.token.type, Text)


@pytest.mark.asyncio
async def test_migrated_postgres_refresh_token_column_is_unbounded():
    import os
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.getenv("COMMUNITY_POSTGRES_URL")
    if not url:
        pytest.skip("PostgreSQL acceptance test only runs in backend CI")
    engine = create_async_engine(url.replace("postgresql://", "postgresql+asyncpg://", 1))
    try:
        async with engine.connect() as conn:
            row = (await conn.execute(text("""
                SELECT data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = 'refresh_tokens' AND column_name = 'token'
            """))).one()
        assert row.data_type == "text"
        assert row.character_maximum_length is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_shared_redis_limit_with_two_independent_clients(monkeypatch):
    import os
    import secrets
    import redis.asyncio as redis_async

    url = os.getenv("REDIS_URL")
    if not url:
        pytest.skip("A Redis container is required for integration validation")
    first = redis_async.from_url(url)
    second = redis_async.from_url(url)
    peer = "ci-" + secrets.token_hex(12)
    key = "pwd-reset:" + peer
    try:
        assert await first.ping()
        monkeypatch.setattr(reset.redis_client, "client", first)
        for _ in range(3):
            await reset._enforce_reset_limit(peer)
        monkeypatch.setattr(reset.redis_client, "client", second)
        for _ in range(2):
            await reset._enforce_reset_limit(peer)
        with pytest.raises(HTTPException) as denied:
            await reset._enforce_reset_limit(peer)
        assert denied.value.status_code == 429
        assert 0 < await second.ttl(key) <= 3600
    finally:
        await first.delete(key)
        await first.aclose()
        await second.aclose()


@pytest.mark.asyncio
async def test_existing_legacy_refresh_table_is_widened_during_startup():
    from lyo_app.core.database import _ensure_refresh_tokens_table

    connection = MagicMock()
    connection.run_sync = AsyncMock(return_value=(True, True))
    connection.execute = AsyncMock()
    await _ensure_refresh_tokens_table(connection)
    connection.execute.assert_awaited_once()
    sql = str(connection.execute.await_args.args[0])
    assert "ALTER TABLE refresh_tokens ALTER COLUMN token TYPE TEXT" in sql


@pytest.mark.asyncio
async def test_already_wide_refresh_table_skips_ddl():
    from lyo_app.core.database import _ensure_refresh_tokens_table

    connection = MagicMock()
    connection.run_sync = AsyncMock(return_value=(True, False))
    connection.execute = AsyncMock()
    await _ensure_refresh_tokens_table(connection)
    connection.execute.assert_not_awaited()
