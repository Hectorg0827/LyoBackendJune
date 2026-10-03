import json
import time
from types import SimpleNamespace

import pytest

from lyo_app.core.ai_resilience import (
    AIModelConfig,
    AIResilienceManager,
    CircuitBreaker,
    CircuitBreakerConfig,
)
from lyo_app.teaching_runtime.model_usage import (
    ModelUsage,
    bind_model_usage,
    capture_model_usage,
)


@pytest.mark.asyncio
async def test_usage_context_is_explicit_and_bounded():
    captured = []

    async def recorder(usage: ModelUsage):
        captured.append(usage)

    await capture_model_usage(
        model="outside",
        tokens_used=999,
        latency_ms=1,
    )
    assert captured == []

    with bind_model_usage(recorder):
        await capture_model_usage(
            model="gpt-4o-mini",
            tokens_used="123",
            latency_ms="456",
        )

    assert captured == [
        ModelUsage(
            model="gpt-4o-mini",
            tokens_used=123,
            latency_ms=456,
            cache_hit=False,
        )
    ]


@pytest.mark.asyncio
async def test_cached_response_records_zero_new_tokens():
    manager = AIResilienceManager()
    manager._initialized = True
    messages = [{"role": "user", "content": "hello"}]
    cache_key = f"chat:{hash(json.dumps(messages))}"
    manager.request_cache[cache_key] = {
        "timestamp": time.time(),
        "data": {
            "content": "Hi",
            "model_used": "gpt-4o-mini",
            # Historical response metadata must not be charged twice.
            "tokens_used": 80,
        },
    }

    captured = []

    async def recorder(usage: ModelUsage):
        captured.append(usage)

    with bind_model_usage(recorder):
        result = await manager.chat_completion(messages=messages, use_cache=True)

    assert result["content"] == "Hi"
    assert captured == [
        ModelUsage(
            model="gpt-4o-mini",
            tokens_used=0,
            latency_ms=0,
            cache_hit=True,
        )
    ]


@pytest.mark.asyncio
async def test_successful_provider_call_reports_tokens_and_canonical_model_key():
    manager = AIResilienceManager()
    manager._initialized = True
    manager.models = {
        "gpt-4o-mini": AIModelConfig(
            name="OpenAI GPT-4o mini",
            endpoint="openai",
            api_key="test-key-long-enough",
        )
    }
    manager.circuit_breakers = {
        "gpt-4o-mini": CircuitBreaker(CircuitBreakerConfig())
    }

    async def create(**_kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="A concise answer")
                )
            ],
            usage=SimpleNamespace(total_tokens=137),
        )

    manager.openai_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )
    )

    captured = []

    async def recorder(usage: ModelUsage):
        captured.append(usage)

    with bind_model_usage(recorder):
        result = await manager.chat_completion(
            messages=[{"role": "user", "content": "Explain this"}],
            provider_order=["gpt-4o-mini"],
            use_cache=False,
        )

    assert result["model_used"] == "gpt-4o-mini"
    assert result["tokens_used"] == 137
    assert result["latency_ms"] >= 0
    assert len(captured) == 1
    assert captured[0].model == "gpt-4o-mini"
    assert captured[0].tokens_used == 137
    assert captured[0].cache_hit is False
