"""Startup hygiene for retired optional AI surfaces.

These assertions keep production boot quiet without disabling the current
multimodal or request-optimization paths. They intentionally pin absence of the
two retired route probes that previously emitted warnings on every boot.
"""

from pathlib import Path


def test_retired_vision_route_is_not_probed_at_startup():
    source = Path("lyo_app/enhanced_main.py").read_text(encoding="utf-8")

    assert "lyo_app.ai_study.vision_routes" not in source
    # The current Lyo 2.0 stream still owns multimodal input.
    stream = Path("lyo_app/api/v1/stream_lyo2.py").read_text(encoding="utf-8")
    assert "MultimodalRouter" in stream
    assert "load_media_attachments" in stream


def test_retired_optimization_management_router_is_not_mounted():
    source = Path("lyo_app/ai_agents/routes.py").read_text(encoding="utf-8")

    assert "setup_optimization_routes" not in source
    # Request optimization remains an active runtime dependency.
    stream = Path("lyo_app/api/v1/stream_lyo2.py").read_text(encoding="utf-8")
    assert "ai_performance_optimizer" in stream
    assert "optimize_request" in stream
