from lyo_app.teaching_runtime.model_router import provider_order_for_tier, thinking_budget_for_tier


def test_reflex_prefers_fast_models():
    order = provider_order_for_tier("reflex")
    assert order[0] == "gpt-4o-mini"
    assert "gpt-4o" not in order
    assert "gemini-3.6-flash" not in order


def test_teaching_uses_normal_low_latency_fallbacks():
    assert provider_order_for_tier("teaching") == [
        "gemini-3.8-flash",
        "gpt-4o-mini",
    ]


def test_deliberation_spends_stronger_model_before_fast_fallback():
    order = provider_order_for_tier("deliberation")
    assert order[:2] == ["gemini-3.8-flash", "gpt-4o"]
    assert order[-2:] == ["gemini-3.6-flash", "gpt-4o-mini"]


def test_media_has_redundant_multimodal_provider_fallbacks():
    assert provider_order_for_tier("deliberation", has_media=True) == [
        "gpt-4o-mini",
        "gemini-3.8-flash",
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
        "gpt-4o-mini",
        "gpt-4o",
        "gemini-3.8-flash",
    ]


def test_voice_deliberation_keeps_strong_model_first():
    order = provider_order_for_tier("deliberation", prefer_low_latency=True)
    assert order[0] == "gpt-4o"
    assert "gemini-3.6-flash" in order

 
def test_all_teaching_tiers_avoid_restricted_gemini_25_models():
    for tier in ("reflex", "teaching", "deliberation", "unknown"):
        for has_media in (False, True):
            for prefer_low_latency in (False, True):
                order = provider_order_for_tier(
                    tier, has_media=has_media,
                    prefer_low_latency=prefer_low_latency,
                )
                assert "gemini-3.8-flash" in order
                assert all(not model.startswith("gemini-2.5") for model in order)
