"""Ensure current Gemini Flash routing remains available to real staging providers.

The 2026-10-14 provider-backed Classroom validation found that the API key
was valid but Gemini 2.5 Flash returned 404 for new accounts. The Google API
response explicitly recommended Gemini 3.8 Flash.
"""
from types import SimpleNamespace

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
