import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from lyo_app.auth import jwt_auth
from lyo_app.core.problems import AuthenticationProblem


def access_token(jti="test-affected-token"):
    return jwt_auth.create_access_token("42", {"jti": jti})


@pytest.fixture(autouse=True)
def reset_jwt_cache(monkeypatch):
    monkeypatch.setenv("JWT_REVOKED_JTIS", "")
    jwt_auth.jwt_cache._cache.clear()
    # Password recovery now checks the persisted credential epoch every time.
    row = MagicMock()
    row.scalar_one_or_none.return_value = 0
    session = MagicMock()
    session.execute = AsyncMock(return_value=row)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr("lyo_app.core.database.AsyncSessionLocal", lambda: context)
    yield
    jwt_auth.jwt_cache._cache.clear()


@pytest.mark.asyncio
async def test_revoke_cached_access_token_without_revoking_other_sessions(monkeypatch):
    token = access_token()
    unaffected = access_token("test-unaffected-token")
    assert (await jwt_auth.verify_token_async(token)).user_id == "42"
    assert (await jwt_auth.verify_token_async(unaffected)).user_id == "42"
    monkeypatch.setenv("JWT_REVOKED_JTIS", "other-id, test-affected-token")
    with pytest.raises(AuthenticationProblem, match="revoked"):
        await jwt_auth.verify_token_async(token)
    assert jwt_auth.jwt_cache.get(token) is None
    assert (await jwt_auth.verify_token_async(unaffected)).user_id == "42"


@pytest.mark.asyncio
async def test_uncached_and_synchronous_verification_reject_revoked_token(monkeypatch):
    token = access_token()
    monkeypatch.setenv("JWT_REVOKED_JTIS", "test-affected-token")
    with pytest.raises(AuthenticationProblem, match="revoked"):
        await jwt_auth.verify_token_async(token)
    with pytest.raises(AuthenticationProblem, match="revoked"):
        jwt_auth.verify_token(token)


@pytest.mark.asyncio
async def test_cache_cannot_extend_token_expiry():
    token = jwt_auth.create_access_token("42", {"exp": int(time.time()) - 60})
    # A forged/stale cache entry cannot bypass the actual signed expiry.
    jwt_auth.jwt_cache.set(token, {"user_id": "42", "token_type": "access", "exp": time.time() + 3600})
    with pytest.raises(AuthenticationProblem, match="expired"):
        await jwt_auth.verify_token_async(token)
