"""Freshness routing for low-latency chat.

Current questions require evidence. Ordinary informational questions also
get a shared web lookup, with a disclosed background-only fallback when
retrieval fails. Casual, creative and local tasks do not need a lookup.
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
    r"yesterday|tomorrow|right now|current|currently|latest|most recent|recent|recently|"
    r"this (?:week|month|year)|as of|new (?:information|research|discoveries|"
    r"developments|features|versions?|releases?|products?|updates?)|"
    r"breaking|live|real[- ]?time|up[- ]?to[- ]?date|"
    r"news|headlines?|trending|noticias|titulares|actualidad|"
    r"hoy|ayer|mañana|ahora|actualmente|últim[oa]s?|recientes?|"
    r"score|standings|schedule|weather|forecast|traffic|"
    r"clima|pronóstico|pronostico|"
    r"stock price|share price|market price|exchange rate|price today|"
    r"president|prime minister|ceo|governor|mayor|election|polls?|"
    r"release date|availability|in stock|open now|hours today|"
    r"pricing|prices?|specifications?|specs|software versions?|"
    r"laws?|regulations?|visa requirements|entry requirements"
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
    r"i have (?:a )?(?:test|exam)|prepare me for|"
    r"redacta|reescribe|traduce|resume|resumir|poema"
    r")\b",
    re.IGNORECASE,
)

_SUPPLIED_SOURCE = re.compile(
    r"\b(attached|attachment|uploaded|pasted|provided|this (?:article|document|file|text)|"
    r"(?:article|document|text) (?:below|above)|adjunt[oa]|subid[oa]|este (?:artículo|documento|texto))\b",
    re.I,
)
_WEB_REQUEST = re.compile(
    r"\b(online|web|internet|browse|look(?:\s+\w+){0,3}\s+up|"
    r"verify|fact[- ]?check|verifica|busca en internet)\b", re.I,
)
_TEMPORAL_LOOKUP = re.compile(
    r"\b(today|tonight|yesterday|tomorrow|current(?:ly)?|latest|most recent|recent(?:ly)?|"
    r"breaking|live|real[- ]?time|up[- ]?to[- ]?date|right now|"
    r"hoy|ayer|mañana|ahora|actualmente|últim[oa]s?|recientes?)\b", re.I,
)

_FACTUAL_SHAPE = re.compile(
    r"^(?:who|what|when|where|which|how many|how much|is|are|does|do|did|can)\b",
    re.IGNORECASE,
)

_INFORMATIONAL = re.compile(
    r"^(?:tell me about|give me (?:information|details)|explain|describe|"
    r"help me understand|learn about|information (?:on|about)|research|"
    r"compare|recommend|cuéntame|explica|información sobre)\b", re.I,
)

_LOCAL_CONTEXT = re.compile(
    r"\b(?:my (?:notes|files?|documents?|preferences?|profile|conversation)|"
    r"(?:I|we) (?:said|told you|tell you|discussed|talked about|attached|uploaded)|"
    r"(?:this|our|the previous) conversation|"
    r"attached (?:file|document|image|(?:news )?article)|uploaded (?:file|document|image))\b", re.I,
)

_RECENT_INTENT = re.compile(
    r"\b(today|tonight|yesterday|tomorrow|this (?:week|month|year)|"
    r"current|currently|latest|recent|recently|live|new (?:research|information|"
    r"developments|updates|discoveries)|hoy|ahora|últim[oa]s?|recientes?)\b", re.I,
)


_CASUAL = re.compile(
    r"^(?:hi|hey|hello|hola|thanks|thank you|gracias|"
    r"how are you|what can you do|can you help me|cómo estás)[?!. ]*$", re.I,
)


_FOLLOW_UP = re.compile(
    r"^(?:what about|how about|and\b|again\b|try again\b|update\b|"
    r"are you sure|that (?:is|was)|that's|same\b|y en\b|otra vez\b)",
    re.IGNORECASE,
)

_SEARCH_CAPABILITY = re.compile(
    r"^(?:(?:but|bit)\s+)?(?:how (?:can|do) you|do you have|"
    r"can you (?:access|search|browse|get)|are you (?:limited|confined)|"
    r"is your (?:information|knowledge)|what is your (?:knowledge|training))\b",
    re.IGNORECASE,
)


def live_search_capability_response(text: str) -> Optional[str]:
    normalized = (text or "").strip()
    if (
        _SEARCH_CAPABILITY.search(normalized)
        and re.search(r"\b(weather|news|internet|browse|live|real[- ]?time|"
                      r"(?:new|updated|external|current) information|web|online|training data)\b", normalized, re.I)
        and not re.search(r"\b(tell me|give me|show me|temperature|headlines)\b", normalized, re.I)
    ):
        return (
            "I can try a web search for information across topics, beyond the model's "
            "training data. I'll use supporting sources and check dates when they "
            "matter. If a lookup fails, I'll say what I couldn't verify."
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
        if (
            (_EXPLICIT_CURRENT.search(previous) or _FACTUAL_SHAPE.search(previous)
             or _INFORMATIONAL.search(previous) or "?" in previous)
            and not _WORKFLOW_OR_CREATIVE.search(previous)
            and not _LOCAL_CONTEXT.search(previous)
        ):
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

    if _CASUAL.fullmatch(normalized):
        return FreshnessDecision(FreshnessMode.NONE, "casual")

    if live_search_capability_response(normalized):
        return FreshnessDecision(FreshnessMode.NONE, "search_capability_question")

    if re.fullmatch(r"(?:how are you|what['’]?s up|who are you|what can you do|how can you help me)[?.!]*", normalized, re.I):
        return FreshnessDecision(FreshnessMode.NONE, "casual_or_capability")

    if (_LOCAL_CONTEXT.search(normalized) or _SUPPLIED_SOURCE.search(normalized)) and not _WEB_REQUEST.search(normalized):
        return FreshnessDecision(FreshnessMode.NONE, "conversation_or_document_context")

    arithmetic_text = re.sub(
        r"^(?:please\s+)?(?:(?:just|simply|only)\s+)?(?:answer|calculate|compute)\s*:\s*",
        "", normalized, flags=re.I,
    )
    if re.fullmatch(r"(?:what is\s+)?[\d\s()+*/.%-]+(?:\s*[+=×÷-]\s*[\d\s()+*/.%-]+)+\??", arithmetic_text, re.I):
        return FreshnessDecision(FreshnessMode.NONE, "arithmetic")

    if re.fullmatch(
        r"(?:what is (?:the )?(?:weather|news|forecasting)|"
        r"how do weather forecasts work|define (?:weather|news))\??",
        normalized, re.I,
    ):
        return FreshnessDecision(FreshnessMode.NONE, "stable_definition")

    if _EXPLICIT_SEARCH.search(normalized) or _WEB_REQUEST.search(normalized):
        return FreshnessDecision(FreshnessMode.REQUIRE, "explicit_search")

    if _WORKFLOW_OR_CREATIVE.search(normalized) and not (_RECENT_INTENT.search(normalized) or _TEMPORAL_LOOKUP.search(normalized)):
        return FreshnessDecision(FreshnessMode.NONE, "workflow_or_creative")

    if _EXPLICIT_CURRENT.search(normalized):
        return FreshnessDecision(FreshnessMode.REQUIRE, "time_sensitive")

    if re.search(rf"\b(?:in|for|as of|en)\s+{datetime.now(timezone.utc).year}\b", normalized, re.I):
        return FreshnessDecision(FreshnessMode.REQUIRE, "current_year_information")

    if _WORKFLOW_OR_CREATIVE.search(normalized):
        return FreshnessDecision(FreshnessMode.NONE, "workflow_or_creative")

    lookup = contextual_lookup_text(normalized, conversation_history)
    if lookup != normalized:
        mode = FreshnessMode.REQUIRE if _EXPLICIT_CURRENT.search(lookup) else FreshnessMode.ALLOW
        return FreshnessDecision(mode, "informational_lookup_follow_up")

    if "?" in normalized or _FACTUAL_SHAPE.search(normalized) or _INFORMATIONAL.search(normalized):
        return FreshnessDecision(FreshnessMode.ALLOW, "informational_web_lookup")

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
