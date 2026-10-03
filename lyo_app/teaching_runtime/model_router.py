"""Model selection for the three-speed Lyo teaching loop.

This module intentionally contains no provider calls. It translates the
pedagogical policy's abstract tier into the providers already configured by
AIResilienceManager, keeping vendor choice replaceable and testable.
"""

from __future__ import annotations

from typing import List


def provider_order_for_tier(tier: str, *, has_media: bool = False) -> List[str]:
    """Return a bounded fallback order for one teaching turn.

    Multimodal chat currently has one configured model whose declared
    capability includes multimodal input, so it remains on that safe path.
    Text-only deliberation can spend a stronger model; ordinary and reflex
    turns prefer the lower-latency/cost models.
    """
    if has_media:
        return ["gemini-2.5-flash"]

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
