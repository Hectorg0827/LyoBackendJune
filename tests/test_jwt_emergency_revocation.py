import time

import pytest

from lyo_app.auth import jwt_auth
from lyo_app.core.problems import AuthenticationProblem


def access_token(jti="test-affected-token"):
    return jwt_auth.create_access_token("42", {"jti": jti})


@pytest.fixture(autouse=True)
def reset_jwt_cache(monkeypatch):
    monkeypatch.setenv("JWT_REVOKED_JTIS", "")
    jwt_auth.jwt_cache._cache.clear()
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
    token = access_token()
    await jwt_auth.verify_token_async(token)
    jwt_auth.jwt_cache._cache[token]["data"]["exp"] = time.time() - 1
    with pytest.raises(AuthenticationProblem, match="expired"):
        await jwt_auth.verify_token_async(token)
