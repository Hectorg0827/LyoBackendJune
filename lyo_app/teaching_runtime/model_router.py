"""Model selection for the three-speed Lyo teaching loop.

This module intentionally contains no provider calls. It translates the
pedagogical policy's abstract tier into the providers already configured by
AIResilienceManager, keeping vendor choice replaceable and testable.
"""

from __future__ import annotations

from typing import List


def provider_order_for_tier(
    tier: str,
    *,
    has_media: bool = False,
    prefer_low_latency: bool = False,
) -> List[str]:
    """Return a bounded fallback order for one teaching turn.

    Multimodal turns use the same bounded fallback principle as text. Lyo
    normalizes images for OpenAI and extracts document text for its fallback,
    while Gemini can still consume the original bytes. No attachment should
    make the whole product depend on a single provider.
    """
    # Gemini credentials are configured in LYO staging; OpenAI may be absent.
    # Prefer the verified Gemini 3 models so both chat and teaching have a
    # genuine first-choice model plus an independent fallback.
    if has_media:
        return ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gpt-4o-mini", "gpt-4o"]

    normalized = (tier or "teaching").strip().lower()

    if prefer_low_latency or normalized == "reflex":
        return ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gpt-4o-mini", "gpt-4o"]

    if normalized == "deliberation":
        return ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gpt-4o", "gpt-4o-mini"]

    return ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gpt-4o-mini", "gpt-4o"]


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
