"""The $10 classroom trial is a real, cross-worker pre-request guard."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.trial_budget import (
    ClassroomTrialBudgetExceeded,
    reserve_classroom_attempt,
    reserve_micro_usd,
)
from lyo_app.core.ai_resilience import AIModelConfig, AIResilienceManager, CircuitBreaker, CircuitBreakerConfig


class AtomicRedisLedger:
    """An in-memory simulation of the installed Redis Lua script's atomicity."""

    def __init__(self):
        self.total = 0
        self.lock = asyncio.Lock()
        self.calls = 0

    async def eval(self, script, number_of_keys, key, requested, limit):
        assert "INCRBY" in script and number_of_keys == 1
        assert key.startswith("lyo:classroom:trial:")
        async with self.lock:
            self.calls += 1
            if self.total + int(requested) > int(limit):
                return -1
            self.total += int(requested)
            return self.total


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("CLASSROOM_AI_TRIAL_ENABLED", "1")
    monkeypatch.setenv("CLASSROOM_AI_TRIAL_LIMIT_USD", "0.01")
    return monkeypatch


@pytest.mark.asyncio
async def test_atomic_concurrent_requests_never_exceed_limit(trial):
    from lyo_app.core.redis_client import redis_client

    ledger = AtomicRedisLedger()
    trial.setattr(redis_client, "client", ledger)
    requests = [reserve_classroom_attempt("gpt-4o-mini", [{"role": "user", "content": "A"}],
                                          100, None) for _ in range(50)]
    results = await asyncio.gather(*requests, return_exceptions=True)
    accepted = sum(isinstance(value, int) for value in results)
    denied = sum(isinstance(value, ClassroomTrialBudgetExceeded) for value in results)
    reservation = reserve_micro_usd("gpt-4o-mini", [{"role": "user", "content": "A"}], 100)
    assert accepted > 0 and denied > 0 and accepted + denied == len(results)
    assert ledger.total == accepted * reservation <= 10_000


@pytest.mark.asyncio
async def test_missing_or_failing_redis_fails_closed(trial):
    from lyo_app.core.redis_client import redis_client

    trial.setattr(redis_client, "client", None)
    with pytest.raises(ClassroomTrialBudgetExceeded, match="unavailable"):
        await reserve_classroom_attempt("gpt-4o-mini", [], 100, None)

    ledger = AtomicRedisLedger()
    ledger.eval = AsyncMock(side_effect=ConnectionError("redis disconnected"))
    trial.setattr(redis_client, "client", ledger)
    with pytest.raises(ClassroomTrialBudgetExceeded, match="unavailable"):
        await reserve_classroom_attempt("gpt-4o-mini", [], 100, None)


@pytest.mark.asyncio
async def test_fallback_attempts_are_reserved_separately_and_stop_at_ceiling(trial):
    from lyo_app.core.redis_client import redis_client

    ledger = AtomicRedisLedger()
    trial.setattr(redis_client, "client", ledger)
    manager = AIResilienceManager()
    manager._initialized = True
    manager.models = {
        name: AIModelConfig(name=name, endpoint="gemini-mock", api_key="fake-key")
        for name in ("gemini-3.6-flash", "gemini-3.7-flash")
    }
    manager.circuit_breakers = {
        name: CircuitBreaker(CircuitBreakerConfig()) for name in manager.models
    }
    actual_provider_calls = []

    async def mocked_provider(model_name, *_args, **_kwargs):
        actual_provider_calls.append(model_name)
        if model_name == "gemini-3.6-flash":
            raise RuntimeError("ambiguous provider timeout")
        return {"model_used": model_name, "content": "ok", "tokens_used": 1}

    trial.setattr(manager, "_call_model_with_messages", mocked_provider)
    msg = [{"role": "user", "content": "Explain fractions"}]
    expected = (reserve_micro_usd("gemini-3.6-flash", msg, 100) +
                reserve_micro_usd("gemini-3.7-flash", msg, 100))
    assert expected < 10_000
    result = await manager.chat_completion(messages=msg, max_tokens=100, use_cache=False,
                                            provider_order=list(manager.models),
                                            classroom_trial_budget=True)
    assert result["content"] == "ok"
    assert actual_provider_calls == list(manager.models)
    assert ledger.total == expected  # Also accounts for the failed first attempt.

    # A smaller ceiling now denies before another provider call, not afterwards.
    trial.setenv("CLASSROOM_AI_TRIAL_LIMIT_USD", str(ledger.total / 1_000_000))
    with pytest.raises(ClassroomTrialBudgetExceeded, match="exhausted"):
        await manager.chat_completion(messages=msg, max_tokens=100, use_cache=False,
                                      provider_order=list(manager.models),
                                      classroom_trial_budget=True)
    assert actual_provider_calls == list(manager.models)


@pytest.mark.asyncio
async def test_trial_requires_explicit_staging_configuration(trial):
    trial.setenv("ENVIRONMENT", "production")
    with pytest.raises(ClassroomTrialBudgetExceeded, match="staging only"):
        await reserve_classroom_attempt("gpt-4o-mini", [], 100, None)
    trial.setenv("ENVIRONMENT", "staging")
    trial.setenv("CLASSROOM_AI_TRIAL_LIMIT_USD", "100.00")
    with pytest.raises(ClassroomTrialBudgetExceeded, match="at most"):
        await reserve_classroom_attempt("gpt-4o-mini", [], 100, None)
