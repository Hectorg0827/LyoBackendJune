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
    if has_media:
        return ["gpt-4o-mini", "gemini-2.5-flash", "gpt-4o"]

    normalized = (tier or "teaching").strip().lower()

    # Live voice uses the same model prompt, memory and teaching contract as
    # text Chat. Only provider ordering changes: start with the lowest-latency
    # configured provider so spoken turn-taking does not pay an avoidable
    # failed/slow first attempt. Deliberation still starts with the stronger
    # OpenAI model rather than silently downgrading reasoning quality.
    if prefer_low_latency:
        if normalized == "deliberation":
            return ["gpt-4o", "gpt-4o-mini", "gemini-2.5-pro", "gemini-2.5-flash"]
        return ["gpt-4o-mini", "gpt-4o", "gemini-2.5-flash"]

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
