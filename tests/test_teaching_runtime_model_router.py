from lyo_app.teaching_runtime.model_router import provider_order_for_tier


def test_reflex_prefers_fast_models():
    order = provider_order_for_tier("reflex")
    assert order[0] == "gpt-4o-mini"
    assert "gpt-4o" not in order
    assert "gemini-2.5-pro" not in order


def test_teaching_uses_normal_low_latency_fallbacks():
    assert provider_order_for_tier("teaching") == [
        "gemini-2.5-flash",
        "gpt-4o-mini",
    ]


def test_deliberation_spends_stronger_model_before_fast_fallback():
    order = provider_order_for_tier("deliberation")
    assert order[:2] == ["gemini-2.5-pro", "gpt-4o"]
    assert order[-2:] == ["gemini-2.5-flash", "gpt-4o-mini"]


def test_media_never_routes_to_text_only_models():
    assert provider_order_for_tier("deliberation", has_media=True) == [
        "gemini-2.5-flash"
    ]


def test_unknown_tier_fails_safe_to_teaching():
    assert provider_order_for_tier("future-tier") == provider_order_for_tier("teaching")
