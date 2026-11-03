from lyo_app.teaching_runtime.model_router import provider_order_for_tier, thinking_budget_for_tier


def test_reflex_prefers_configured_gemini_fast_models():
    order = provider_order_for_tier("reflex")
    assert order[:2] == ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
    assert "gemini-2.5-flash" not in order


def test_teaching_uses_reliable_gemini_fallbacks():
    assert provider_order_for_tier("teaching") == [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gpt-4o-mini",
        "gpt-4o",
    ]


def test_deliberation_prefers_verified_stronger_model():
    order = provider_order_for_tier("deliberation")
    assert order[:2] == ["gemini-3.6-flash", "gemini-3.5-flash-lite"]
    assert order[-2:] == ["gpt-4o", "gpt-4o-mini"]


def test_media_has_redundant_multimodal_provider_fallbacks():
    assert provider_order_for_tier("deliberation", has_media=True) == [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gpt-4o-mini",
        "gpt-4o",
    ]


def test_unknown_tier_fails_safe_to_teaching():
    assert provider_order_for_tier("future-tier") == provider_order_for_tier("teaching")


def test_thinking_budget_matches_latency_tier():
    assert thinking_budget_for_tier("reflex") == 0
    assert thinking_budget_for_tier("teaching") == 256
    assert thinking_budget_for_tier("deliberation") == -1


def test_voice_prefers_low_latency_provider_without_changing_contract_tier():
    assert provider_order_for_tier("teaching", prefer_low_latency=True) == [
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gpt-4o-mini",
        "gpt-4o",
    ]


def test_voice_deliberation_uses_low_latency_gemini_fallbacks():
    order = provider_order_for_tier("deliberation", prefer_low_latency=True)
    assert order[:2] == ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
