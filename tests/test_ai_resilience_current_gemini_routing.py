"""Ensure current Gemini Flash routing remains available to real staging providers.

The 2026-10-14 provider-backed Classroom validation found that the API key
was valid but Gemini 2.5 Flash returned 404 for new accounts. The Google API
response explicitly recommended Gemini 3.8 Flash.
"""
from types import SimpleNamespace

import pytest

from lyo_app.core.ai_resilience import AIResilienceManager


def _manager(latest_key="staging-fixture-not-an-api-key"):
    mgr = AIResilienceManager.__new__(AIResilienceManager)
    mgr.models = {
        "gemini-2.5-flash": SimpleNamespace(api_key="legacy"),
        "gemini-3.6-flash": SimpleNamespace(api_key="legacy"),
        "gemini-3.7-flash": SimpleNamespace(api_key="legacy"),
        "gemini-3.8-flash": SimpleNamespace(api_key=latest_key),
        "gemini-2.5-pro": SimpleNamespace(api_key="legacy"),
        "gpt-4o-mini": SimpleNamespace(api_key=""),
    }
    return mgr


def test_legacy_flash_fallbacks_use_current_gemini_and_preserve_openai_precedence():
    mgr = _manager()
    assert mgr._normalize_supported_provider_order([
        "gpt-4o-mini", "gemini-2.5-flash", "gemini-3.6-flash",
    ]) == ["gpt-4o-mini", "gemini-3.8-flash"]


def test_explicit_current_flash_and_pro_remain_distinct():
    mgr = _manager()
    assert mgr._normalize_supported_provider_order([
        "gemini-3.7-flash", "gemini-3.8-flash", "gemini-2.5-pro",
    ]) == ["gemini-3.8-flash", "gemini-2.5-pro"]


def test_without_a_configured_current_provider_do_not_fabricate_availability():
    mgr = _manager(latest_key="")
    assert mgr._normalize_supported_provider_order([
        "gemini-2.5-flash", "gemini-3.6-flash",
    ]) == ["gemini-2.5-flash", "gemini-3.6-flash"]


class _TransparentBreaker:
    async def call(self, action):
        return await action()


async def _completed_request(behaviors):
    from unittest.mock import AsyncMock

    manager = _manager()
    manager.circuit_breakers = {"gemini-3.8-flash": _TransparentBreaker()}
    manager._make_api_call_with_messages = AsyncMock(side_effect=behaviors)
    messages = [{"role": "user", "content": "Explain photosynthesis"}]
    return manager, messages


@pytest.mark.asyncio
async def test_transient_503_then_429_are_retried_inside_one_circuit_breaker_attempt(monkeypatch):
    observed_sleeps = []

    async def fake_sleep(seconds):
        observed_sleeps.append(seconds)

    monkeypatch.setattr("lyo_app.core.ai_resilience.asyncio.sleep", fake_sleep)
    mgr, messages = await _completed_request([
        RuntimeError("API returned 503: provider overloaded"),
        RuntimeError("API returned 429: rate limit"),
        {"content": "A real lesson", "model_used": "gemini-3.8-flash"},
    ])
    response = await mgr._call_model_with_messages(
        "gemini-3.8-flash", mgr.models["gemini-3.8-flash"], messages, 0.2, 256,
    )
    assert response["content"] == "A real lesson"
    assert mgr._make_api_call_with_messages.await_count == 3
    assert observed_sleeps == [0.4, 0.8]


@pytest.mark.asyncio
async def test_terminal_404_is_not_retried(monkeypatch):
    async def fake_sleep(_):
        raise AssertionError("404 must not sleep or retry")

    monkeypatch.setattr("lyo_app.core.ai_resilience.asyncio.sleep", fake_sleep)
    mgr, messages = await _completed_request(
        [RuntimeError("API returned 404: model retired")]
    )
    with pytest.raises(RuntimeError, match="404"):
        await mgr._call_model_with_messages(
            "gemini-3.8-flash", mgr.models["gemini-3.8-flash"], messages, 0.2, 256,
        )
    assert mgr._make_api_call_with_messages.await_count == 1


@pytest.mark.asyncio
async def test_daily_request_quota_429_never_sleeps_or_retries(monkeypatch):
    async def fake_sleep(_):
        raise AssertionError("Daily Google quota exhaustion cannot recover by retrying")

    monkeypatch.setattr("lyo_app.core.ai_resilience.asyncio.sleep", fake_sleep)
    error = RuntimeError(
        "API returned 429: Quota exceeded for metric: "
        "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
        "limit: 20, model: gemini-3.8-flash. Please retry in 23h."
    )
    mgr, messages = await _completed_request([error])
    with pytest.raises(RuntimeError, match="Quota exceeded"):
        await mgr._call_model_with_messages(
            "gemini-3.8-flash", mgr.models["gemini-3.8-flash"], messages, 0.2, 256,
        )
    assert mgr._make_api_call_with_messages.await_count == 1
