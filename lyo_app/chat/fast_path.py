"""Deterministic eligibility for Lyo's low-latency chat lane."""

from __future__ import annotations

import re
from typing import Optional

from lyo_app.ai.schemas.lyo2 import Intent


_GREETING = re.compile(
    r"^(?:hi|hey|hello|hola|buenas|good (?:morning|afternoon|evening)|"
    r"thanks|thank you|gracias)[!. ]*$",
    re.IGNORECASE,
)

_HEAVY_WORKFLOW = re.compile(
    r"\b("
    r"course|quiz|flashcards?|study plan|test prep|exam prep|"
    r"i have (?:a )?(?:test|exam)|upload|attachment|"
    r"create|build|generate|schedule|calendar|remind me"
    r")\b",
    re.IGNORECASE,
)

_EXPLICIT_TEACHING = re.compile(
    r"\b(teach me|explain|help me understand|walk me through|lesson|tutor me)\b",
    re.IGNORECASE,
)


def fast_route_intent(
    text: str,
    *,
    has_media: bool = False,
    forced_intent: Optional[Intent] = None,
) -> Optional[Intent]:
    """Return a safe deterministic intent only for obvious ordinary chat.

    None means "use the existing LLM router." This is intentionally
    conservative: structured workflows and explicit teaching remain on the
    full Learning OS route.
    """

    if forced_intent is not None or has_media:
        return None

    value = (text or "").strip()
    if not value:
        return None

    if _GREETING.match(value):
        return Intent.GREETING

    if _HEAVY_WORKFLOW.search(value) or _EXPLICIT_TEACHING.search(value):
        return None

    # Long or multi-part requests deserve semantic routing even if they happen
    # to end in a question mark.
    if len(value) > 420 or value.count("?") > 2:
        return None

    if "?" in value:
        return Intent.CHAT

    # Short conversational follow-ups such as "go deeper" or "what about
    # Europe" should not pay for a routing model.
    if len(value.split()) <= 12:
        return Intent.CHAT

    return None
