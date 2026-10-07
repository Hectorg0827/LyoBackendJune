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
from typing import Optional, Sequence
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
    r"news|headlines?|trending|noticias|titulares|actualidad|"
    r"hoy|ayer|mañana|ahora|actualmente|últim[oa]s?|recientes?|"
    r"score|standings|schedule|weather|forecast|traffic|"
    r"clima|pronóstico|pronostico|"
    r"stock price|share price|market price|exchange rate|price today|"
    r"president|prime minister|ceo|governor|mayor|election|polls?|"
    r"release date|availability|in stock|open now|hours today"
    r")\b",
    re.IGNORECASE,
)

_EXPLICIT_SEARCH = re.compile(
    r"\b(search|look(?:\s+\w+){0,3}\s+up|lookup|browse|check online|check the web|web search|find online)\b",
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


_FOLLOW_UP = re.compile(
    r"^(?:what about|how about|and\b|again\b|try again\b|update\b|"
    r"are you sure|that (?:is|was)|that's|same\b|y en\b|otra vez\b)",
    re.IGNORECASE,
)

_SEARCH_CAPABILITY = re.compile(
    r"^(?:(?:but|bit)\s+)?(?:how (?:can|do) you|do you have|can you access)\b",
    re.IGNORECASE,
)


def live_search_capability_response(text: str) -> Optional[str]:
    normalized = (text or "").strip()
    if (
        _SEARCH_CAPABILITY.search(normalized)
        and re.search(r"\b(weather|news|internet|browse|live|real[- ]?time)\b", normalized, re.I)
        and not re.search(r"\b(tell me|give me|show me|temperature|headlines)\b", normalized, re.I)
    ):
        return (
            "I can try a live search for news, weather, and other current information. "
            "I'll only present it as current when the lookup returns supporting "
            "sources for the requested place and date."
        )
    return None


def contextual_lookup_text(text: str, history: Optional[Sequence[dict]] = None) -> str:
    """Resolve short lookup follow-ups from user turns, never old AI claims."""
    normalized = (text or "").strip()
    turns = list(history or [])[-8:]
    awaiting_location = bool(
        turns and turns[-1].get("role") == "assistant"
        and re.search(r"which city or location.*weather", str(turns[-1].get("content") or ""), re.I)
        and len(normalized.split()) <= 8
        and not _FACTUAL_SHAPE.search(normalized)
    )
    if (not _FOLLOW_UP.search(normalized) and not awaiting_location) or len(normalized.split()) > 18:
        return normalized
    for turn in reversed(turns):
        if turn.get("role") != "user":
            continue
        previous = str(turn.get("content") or "").strip()
        if not previous or _FOLLOW_UP.search(previous):
            continue
        if _EXPLICIT_CURRENT.search(previous) and not _WORKFLOW_OR_CREATIVE.search(previous):
            follow_up = f"weather in {normalized}" if awaiting_location else normalized
            return f"{previous}\nFollow-up request: {follow_up}"
        # Do not inherit a weather/news lookup across a subject change.
        break
    return normalized


def decide_freshness(
    text: str, conversation_history: Optional[Sequence[dict]] = None
) -> FreshnessDecision:
    normalized = (text or "").strip()
    if not normalized:
        return FreshnessDecision(FreshnessMode.NONE, "empty")

    if live_search_capability_response(normalized):
        return FreshnessDecision(FreshnessMode.NONE, "search_capability_question")

    if re.fullmatch(
        r"(?:what is (?:the )?(?:weather|news|forecasting)|"
        r"how do weather forecasts work|define (?:weather|news))\??",
        normalized, re.I,
    ):
        return FreshnessDecision(FreshnessMode.NONE, "stable_definition")

    if _EXPLICIT_SEARCH.search(normalized):
        return FreshnessDecision(FreshnessMode.REQUIRE, "explicit_search")

    if _EXPLICIT_CURRENT.search(normalized):
        return FreshnessDecision(FreshnessMode.REQUIRE, "time_sensitive")

    if _WORKFLOW_OR_CREATIVE.search(normalized):
        return FreshnessDecision(FreshnessMode.NONE, "workflow_or_creative")

    if contextual_lookup_text(normalized, conversation_history) != normalized:
        return FreshnessDecision(FreshnessMode.REQUIRE, "current_lookup_follow_up")

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
