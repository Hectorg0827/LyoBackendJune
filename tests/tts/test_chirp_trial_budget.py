"""The paid voice pilot must reserve before calling Google, or fail closed."""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from lyo_app.tts.service import TTSConfig, TTSService, TTSUnavailableError
from lyo_app.tts.trial_budget import (
    TTSTrialBudgetExceeded,
    RESERVE_MICRO_USD_PER_UTF8_BYTE,
    reserve_chirp_attempt,
)


class AtomicLedger:
    def __init__(self):
        self.total = 0
        self.lock = asyncio.Lock()
        self.calls = 0

    async def eval(self, script, keys, ledger_key, requested, limit):
        assert "INCRBY" in script and keys == 1
        assert ledger_key.startswith("lyo:tts:chirp:trial:")
        async with self.lock:
            self.calls += 1
            if self.total + int(requested) > int(limit):
                return -1
            self.total += int(requested)
            return self.total


@pytest.fixture
def guarded(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("TTS_CHIRP_TRIAL_ENABLED", "true")
    monkeypatch.setenv("TTS_CHIRP_TRIAL_LIMIT_USD", "0.001")
    return monkeypatch


@pytest.mark.asyncio
async def test_atomic_reservation_never_exceeds_ceiling(guarded):
    from lyo_app.core.redis_client import redis_client

    ledger = AtomicLedger()
    guarded.setattr(redis_client, "client", ledger)
    phrase = "A short phrase"
    results = await asyncio.gather(
        *(reserve_chirp_attempt(phrase) for _ in range(20)),
        return_exceptions=True,
    )
    accepted = sum(isinstance(result, int) for result in results)
    denied = sum(isinstance(result, TTSTrialBudgetExceeded) for result in results)
    assert accepted > 0 and denied > 0
    assert accepted + denied == len(results)
    assert ledger.total == accepted * len(phrase.encode("utf-8")) * RESERVE_MICRO_USD_PER_UTF8_BYTE
    assert ledger.total <= 1_000


@pytest.mark.asyncio
async def test_disabled_non_staging_and_oversized_limits_fail_closed(guarded):
    guarded.setenv("ENVIRONMENT", "production")
    with pytest.raises(TTSTrialBudgetExceeded, match="staging only"):
        await reserve_chirp_attempt("test")
    guarded.setenv("ENVIRONMENT", "staging")
    guarded.setenv("TTS_CHIRP_TRIAL_ENABLED", "false")
    with pytest.raises(TTSTrialBudgetExceeded, match="not enabled"):
        await reserve_chirp_attempt("test")
    guarded.setenv("TTS_CHIRP_TRIAL_ENABLED", "true")
    guarded.setenv("TTS_CHIRP_TRIAL_LIMIT_USD", "25")
    with pytest.raises(TTSTrialBudgetExceeded, match="at most"):
        await reserve_chirp_attempt("test")


@pytest.mark.asyncio
async def test_missing_or_failed_redis_blocks_provider_calls(guarded):
    from lyo_app.core.redis_client import redis_client

    guarded.setattr(redis_client, "client", None)
    with pytest.raises(TTSTrialBudgetExceeded, match="unavailable"):
        await reserve_chirp_attempt("test")
    ledger = AtomicLedger()
    ledger.eval = AsyncMock(side_effect=ConnectionError("offline"))
    guarded.setattr(redis_client, "client", ledger)
    with pytest.raises(TTSTrialBudgetExceeded, match="unavailable"):
        await reserve_chirp_attempt("test")


@pytest.mark.asyncio
async def test_no_provider_http_request_if_budget_cannot_reserve(tmp_path, guarded):
    from lyo_app.core.redis_client import redis_client

    guarded.setattr(redis_client, "client", None)
    guarded.setenv("TTS_CHIRP_TRIAL_LIMIT_USD", "1")
    service = TTSService(TTSConfig(
        provider="google", google_service_account_json='{"test": "only"}',
        cache_dir=str(tmp_path),
    ))
    service._google_access_token = AsyncMock(return_value="temporary-test-token")
    service._session = MagicMock()
    service._initialized = True
    with pytest.raises(TTSTrialBudgetExceeded, match="unavailable"):
        await service.synthesize("This should never reach Google.", language="en-US")
    service._session.post.assert_not_called()


@pytest.mark.asyncio
async def test_google_request_uses_oauth_bearer_and_cache_bypasses_second_charge(tmp_path, guarded):
    from lyo_app.core.redis_client import redis_client

    guarded.setenv("TTS_CHIRP_TRIAL_LIMIT_USD", "1")
    ledger = AtomicLedger()
    guarded.setattr(redis_client, "client", ledger)
    service = TTSService(TTSConfig(
        provider="google", google_service_account_json='{"test": "only"}',
        cache_dir=str(tmp_path),
    ))
    service._google_access_token = AsyncMock(return_value="temporary-test-token")
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={"audioContent": base64.b64encode(b"voice").decode()})
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.post.return_value = ctx
    service._session = session
    service._initialized = True

    first = await service.synthesize("One quarter is smaller than one third.", language="en-US")
    second = await service.synthesize("One quarter is smaller than one third.", language="en-US")
    assert first == second == b"voice"
    assert ledger.calls == 1
    assert session.post.call_count == 1
    args, kwargs = session.post.call_args
    assert args[0] == "https://texttospeech.googleapis.com/v1/text:synthesize"
    assert kwargs["headers"]["Authorization"] == "Bearer temporary-test-token"
    assert "temporary-test-token" not in args[0]


def test_provider_health_reflects_paid_trial_flag(tmp_path, guarded):
    service = TTSService(TTSConfig(
        provider="google", google_service_account_json='{"test": "only"}',
        cache_dir=str(tmp_path),
    ))
    assert service.provider_available
    guarded.setenv("TTS_CHIRP_TRIAL_ENABLED", "false")
    assert not service.provider_available


@pytest.mark.asyncio
async def test_google_oauth_refreshes_once_and_caches_short_lived_token(tmp_path, guarded, monkeypatch):
    from google.oauth2 import service_account

    guarded.setenv("TTS_CHIRP_TRIAL_LIMIT_USD", "1")
    cred = MagicMock(valid=False, token=None)

    def refresh(_request):
        cred.token = "short-lived-token"
        cred.valid = True

    cred.refresh.side_effect = refresh
    from_info = MagicMock(return_value=cred)
    monkeypatch.setattr(service_account.Credentials, "from_service_account_info", from_info)
    service = TTSService(TTSConfig(
        provider="google", google_service_account_json='{"type": "service_account"}',
        cache_dir=str(tmp_path),
    ))

    assert await asyncio.gather(service._google_access_token(), service._google_access_token()) == [
        "short-lived-token", "short-lived-token",
    ]
    assert cred.refresh.call_count == 1
    assert from_info.call_count == 1
    assert from_info.call_args.kwargs["scopes"] == [
        "https://www.googleapis.com/auth/cloud-platform"
    ]


@pytest.mark.asyncio
async def test_bad_google_service_account_never_exposes_secret(tmp_path, guarded):
    guarded.setenv("TTS_CHIRP_TRIAL_LIMIT_USD", "1")
    service = TTSService(TTSConfig(
        provider="google", google_service_account_json="not-valid-json-secret",
        cache_dir=str(tmp_path),
    ))
    with pytest.raises(TTSUnavailableError) as error:
        await service._google_access_token()
    assert str(error.value) == "Google TTS authentication unavailable"
    assert error.value.__cause__ is None
    assert "not-valid-json-secret" not in repr(service.config)


@pytest.mark.asyncio
async def test_no_google_network_or_budget_reservation_without_oauth(tmp_path, guarded):
    from lyo_app.core.redis_client import redis_client

    ledger = AtomicLedger()
    guarded.setattr(redis_client, "client", ledger)
    guarded.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    service = TTSService(TTSConfig(provider="google", cache_dir=str(tmp_path)))
    service._session = MagicMock()
    service._initialized = True
    with pytest.raises(TTSUnavailableError, match="unavailable"):
        await service.synthesize("Voice demo text", language="en-US")
    service._session.post.assert_not_called()
    assert ledger.calls == 0
