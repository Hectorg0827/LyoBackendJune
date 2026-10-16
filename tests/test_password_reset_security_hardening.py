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
