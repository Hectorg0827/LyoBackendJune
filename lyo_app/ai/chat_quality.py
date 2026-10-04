"""Deterministic Chat-quality gate.

This is deliberately model-free: it protects the product-control contract
before live model-quality evaluation runs. A change that makes a direct
question become a quiz, lets a stale file hijack an unrelated lesson, or sends
simple chat back through the planner fails CI immediately.

Live empirical answer-quality evaluation can layer on top of this gate without
making core interaction correctness depend on an external model in CI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from lyo_app.ai.chat_intelligence import (
    InteractionMode,
    derive_interaction_contract,
)
from lyo_app.ai.schemas.lyo2 import Intent


@dataclass(frozen=True)
class ChatQualityScenario:
    name: str
    text: str
    expected_mode: InteractionMode
    expected_intent: Optional[Intent]
    answer_first: bool
    fast_lane: bool
    allow_assessment: bool
    has_media: bool = False
    has_current_media: bool = False


DEFAULT_CHAT_QUALITY_SCENARIOS: tuple[ChatQualityScenario, ...] = (
    ChatQualityScenario(
        "direct factual answer",
        "What is photosynthesis?",
        InteractionMode.ANSWER,
        Intent.EXPLAIN,
        True,
        True,
        False,
    ),
    ChatQualityScenario(
        "direct explanation",
        "Explain gravity",
        InteractionMode.EXPLAIN,
        Intent.EXPLAIN,
        True,
        True,
        False,
    ),
    ChatQualityScenario(
        "explicit teaching",
        "Teach me fractions",
        InteractionMode.TEACH,
        Intent.EXPLAIN,
        False,
        False,
        True,
    ),
    ChatQualityScenario(
        "explicit quiz",
        "Quiz me on fractions",
        InteractionMode.QUIZ,
        Intent.QUIZ,
        False,
        False,
        True,
    ),
    ChatQualityScenario(
        "course creation",
        "Create a course on geometry",
        InteractionMode.CREATE,
        Intent.COURSE,
        False,
        False,
        False,
    ),
    ChatQualityScenario(
        "test prep",
        "I have a test Friday",
        InteractionMode.TEST_PREP,
        Intent.TEST_PREP,
        False,
        False,
        True,
    ),
    ChatQualityScenario(
        "attached direct analysis",
        "what is this?",
        InteractionMode.ANALYZE,
        Intent.EXPLAIN,
        True,
        True,
        False,
        has_media=True,
        has_current_media=True,
    ),
    ChatQualityScenario(
        "attached summary",
        "summarize this document",
        InteractionMode.SUMMARIZE,
        Intent.SUMMARIZE_NOTES,
        True,
        True,
        False,
        has_media=True,
        has_current_media=True,
    ),
    ChatQualityScenario(
        "attachment to classroom",
        "Teach this",
        InteractionMode.TEACH,
        Intent.COURSE,
        False,
        False,
        True,
        has_media=True,
        has_current_media=False,
    ),
    ChatQualityScenario(
        "attachment to test prep",
        "Use this for Test Prep",
        InteractionMode.TEST_PREP,
        Intent.TEST_PREP,
        False,
        False,
        True,
        has_media=True,
        has_current_media=False,
    ),
    ChatQualityScenario(
        "stale attachment isolation",
        "Teach me fractions",
        InteractionMode.TEACH,
        Intent.EXPLAIN,
        False,
        False,
        True,
        has_media=True,
        has_current_media=False,
    ),
    ChatQualityScenario(
        "comparison workspace",
        "Compare mitosis vs meiosis",
        InteractionMode.COMPARE,
        Intent.EXPLAIN,
        True,
        True,
        False,
    ),
)


def evaluate_chat_quality_gate(
    scenarios: tuple[ChatQualityScenario, ...] = DEFAULT_CHAT_QUALITY_SCENARIOS,
) -> Dict[str, Any]:
    failures: List[Dict[str, Any]] = []
    for case in scenarios:
        contract = derive_interaction_contract(
            case.text,
            has_media=case.has_media,
            has_current_media=case.has_current_media,
        )
        observed = {
            "mode": contract.mode,
            "intent": contract.router_intent,
            "answer_first": contract.answer_first,
            "fast_lane": contract.fast_lane,
            "allow_assessment": contract.allow_assessment,
        }
        expected = {
            "mode": case.expected_mode,
            "intent": case.expected_intent,
            "answer_first": case.answer_first,
            "fast_lane": case.fast_lane,
            "allow_assessment": case.allow_assessment,
        }
        mismatches = {
            key: {
                "expected": getattr(expected[key], "value", expected[key]),
                "observed": getattr(observed[key], "value", observed[key]),
            }
            for key in expected
            if observed[key] != expected[key]
        }
        if mismatches:
            failures.append({"name": case.name, "mismatches": mismatches})

    total = len(scenarios)
    passed = total - len(failures)
    return {
        "total": total,
        "passed": passed,
        "failed": len(failures),
        "score": (passed / total) if total else 1.0,
        "failures": failures,
    }
