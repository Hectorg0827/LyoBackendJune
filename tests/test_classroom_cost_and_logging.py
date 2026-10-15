"""Regression checks for Classroom token costs and safe logging.

These tests intentionally do not weaken grading, schema, or mastery gates.
"""
from pathlib import Path

from lyo_app.ai_classroom.adaptive_teaching import (
    Evaluation, LearningPlan, bounded_teaching_history, compact_classroom_contract,
)
from lyo_app.core.ai_resilience import safe_provider_error_reason


def test_prompt_compaction_preserves_schema_constraints_and_semantic_descriptions():
    original = LearningPlan.model_json_schema()
    compact = compact_classroom_contract(original)
    assert compact["properties"].keys() == original["properties"].keys()
    assert compact.get("required") == original.get("required")
    assert compact.get("$defs", {}).keys() == original.get("$defs", {}).keys()
    assert len(str(compact)) < len(str(original))
    assert "title" not in compact
    # Do not remove semantics from descriptions, nor constraints such as enums.
    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                yield (k, v)
                yield from walk(v)
        elif isinstance(value, list):
            for v in value:
                yield from walk(v)
    old_constraints = [(k, v) for k, v in walk(original)
                       if k in {"enum", "required", "minItems", "maxItems",
                                "minimum", "maximum", "$ref"}]
    new_constraints = [(k, v) for k, v in walk(compact)
                       if k in {"enum", "required", "minItems", "maxItems",
                                "minimum", "maximum", "$ref"}]
    assert new_constraints == old_constraints
    assert compact_classroom_contract(Evaluation.model_json_schema())["required"] == (
        Evaluation.model_json_schema()["required"]
    )


def test_bounded_recent_teaching_history_retains_order_and_never_changes_source():
    original = [f"step-{i}-" + ("long " * 600) for i in range(9)]
    compact = bounded_teaching_history(original, keep=3, chars=70)
    assert len(compact) == 3
    assert all(len(v) <= 70 for v in compact)
    assert [s.split("-")[1] for s in compact] == ["6", "7", "8"]
    assert len(original) == 9
    assert len(original[0]) > 70


def test_provider_error_classification_never_repeats_sensitive_provider_text():
    secret = "sensitive-learner-answer-XYZ"
    checks = [
        (f"API returned 429: Quota exceeded for metric: daily {secret}", "quota_exhausted"),
        (f"API returned 429: rate limit {secret}", "rate_limited"),
        (f"API returned 503: busy {secret}", "provider_overloaded"),
        (f"API returned 401: {secret}", "provider_auth_rejected"),
        (f"API returned 404: {secret}", "model_unavailable"),
        (f"TimeoutError: {secret}", "provider_timeout"),
    ]
    for error, category in checks:
        result = safe_provider_error_reason(error)
        assert result == category
        assert secret not in result


def test_backend_uvicorn_entrypoints_do_not_log_legacy_query_jwts():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (root / "lyo_app" / "enhanced_main.py").read_text(encoding="utf-8")
    resilience = (root / "lyo_app" / "core" / "ai_resilience.py").read_text(encoding="utf-8")
    assert "--no-access-log" in dockerfile
    assert "--log-level warning" in dockerfile
    assert 'log_level="warning"' in entrypoint
    assert "access_log=False" in entrypoint
    assert 'ALL PROVIDERS FAILED for' not in resilience
    assert "Request for '{message_str" not in resilience
    config = (root / "lyo_app" / "core" / "structured_logging.py").read_text(encoding="utf-8")
    assert 'logging.getLogger("uvicorn.error").setLevel(logging.WARNING)' in config
    assert 'logging.getLogger("uvicorn.protocols.websockets").setLevel(logging.WARNING)' in config
