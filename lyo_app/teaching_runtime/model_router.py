"""Model selection for the three-speed Lyo teaching loop.

This module intentionally contains no provider calls. It translates the
pedagogical policy's abstract tier into the providers already configured by
AIResilienceManager, keeping vendor choice replaceable and testable.
"""

from __future__ import annotations

from typing import List


def provider_order_for_tier(tier: str, *, has_media: bool = False) -> List[str]:
    """Return a bounded fallback order for one teaching turn.

    Multimodal turns use the same bounded fallback principle as text. Lyo
    normalizes images for OpenAI and extracts document text for its fallback,
    while Gemini can still consume the original bytes. No attachment should
    make the whole product depend on a single provider.
    """
    if has_media:
        return ["gpt-4o-mini", "gemini-2.5-flash", "gpt-4o"]

    normalized = (tier or "teaching").strip().lower()
    if normalized == "deliberation":
        return [
            "gemini-2.5-pro",
            "gpt-4o",
            "gemini-2.5-flash",
            "gpt-4o-mini",
        ]
    if normalized == "reflex":
        return ["gpt-4o-mini", "gemini-2.5-flash"]

    return ["gemini-2.5-flash", "gpt-4o-mini"]


def thinking_budget_for_tier(tier: str) -> int:
    """Bound hidden Gemini reasoning so everyday chat stays responsive.

    Gemini 2.5 Flash accepts 0 to disable thinking. Deliberation keeps dynamic
    thinking (-1), while teaching gets a small bounded budget.
    """
    normalized = (tier or "teaching").strip().lower()
    if normalized == "reflex":
        return 0
    if normalized == "deliberation":
        return -1
    return 256
