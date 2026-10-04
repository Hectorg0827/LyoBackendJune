"""Freshness routing for low-latency chat.

The deterministic layer only handles obvious cases. For ordinary factual
questions it returns ALLOW, which means the model may invoke Google Search
itself if its knowledge could be stale. This avoids brittle keyword-only
search routing while keeping casual/creative turns off the paid search path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from zoneinfo import ZoneInfo


class FreshnessMode(str, Enum):
    NONE = "none"
    ALLOW = "allow"
    REQUIRE = "require"


@dataclass(frozen=True)
class FreshnessDecision:
    mode: FreshnessMode
    reason: str

    @property
    def google_search_enabled(self) -> bool:
        return self.mode is not FreshnessMode.NONE


_EXPLICIT_CURRENT = re.compile(
    r"\b("
    r"today|tonight|this morning|this afternoon|this evening|"
    r"yesterday|tomorrow|right now|currently|latest|most recent|recently|"
    r"breaking|live|real[- ]?time|up[- ]?to[- ]?date|"
    r"score|standings|schedule|weather|forecast|traffic|"
    r"stock price|share price|market price|exchange rate|price today|"
    r"president|prime minister|ceo|governor|mayor|election|polls?|"
    r"release date|availability|in stock|open now|hours today"
    r")\b",
    re.IGNORECASE,
)

_EXPLICIT_SEARCH = re.compile(
    r"\b(search|look up|lookup|browse|check online|check the web|web search|find online)\b",
    re.IGNORECASE,
)

_WORKFLOW_OR_CREATIVE = re.compile(
    r"\b("
    r"write|rewrite|draft|translate|summari[sz]e|brainstorm|poem|story|"
    r"roleplay|role-play|quiz me|flashcards?|course|study plan|"
    r"i have (?:a )?(?:test|exam)|prepare me for"
    r")\b",
    re.IGNORECASE,
)

_FACTUAL_SHAPE = re.compile(
    r"^(?:who|what|when|where|which|how many|how much|is|are|does|do|did|can)\b",
    re.IGNORECASE,
)


def decide_freshness(text: str) -> FreshnessDecision:
    normalized = (text or "").strip()
    if not normalized:
        return FreshnessDecision(FreshnessMode.NONE, "empty")

    if _EXPLICIT_SEARCH.search(normalized):
        return FreshnessDecision(FreshnessMode.REQUIRE, "explicit_search")

    if _EXPLICIT_CURRENT.search(normalized):
        return FreshnessDecision(FreshnessMode.REQUIRE, "time_sensitive")

    if _WORKFLOW_OR_CREATIVE.search(normalized):
        return FreshnessDecision(FreshnessMode.NONE, "workflow_or_creative")

    # The deterministic layer deliberately does not decide whether these need
    # the web. It merely makes Search available; Gemini decides whether to call
    # it based on the actual semantic request and its confidence/freshness.
    if "?" in normalized or _FACTUAL_SHAPE.search(normalized):
        return FreshnessDecision(FreshnessMode.ALLOW, "model_may_search")

    return FreshnessDecision(FreshnessMode.NONE, "no_freshness_signal")


def current_time_context(
    timezone_name: Optional[str],
    *,
    now: Optional[datetime] = None,
) -> str:
    """Return an authoritative timestamp for the model prompt.

    Bad or missing client zones fall back to UTC rather than failing a chat.
    """

    base = now or datetime.now(timezone.utc)
    try:
        zone = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    except Exception:
        zone = timezone.utc
    local = base.astimezone(zone)
    return (
        f"Current date/time: {local.isoformat(timespec='seconds')} "
        f"({getattr(zone, 'key', 'UTC')})."
    )
