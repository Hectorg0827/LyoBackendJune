"""Evidence checks shared by live-search providers and both Chat executors.

Retrieving a URL now does not make its contents current. Weather must cover
the requested day and location; news needs a recent publication date.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from .freshness import contextual_lookup_text


LIVE_SEARCH_UNAVAILABLE = (
    "I couldn't verify current information for this request. "
    "Please try again in a moment."
)
WEB_BACKGROUND_NOTICE = (
    "I couldn't verify web sources for this answer. "
    "The following is background information from the model's knowledge, "
    "which may be out of date.\n\n"
)
WEATHER_LOCATION_REQUIRED = "Which city or location should I check the weather for?"
_WEATHER = re.compile(r"\b(weather|forecast|clima|pron[oó]stico)\b", re.I)
_NEWS = re.compile(r"\b(news|headlines?|trending|noticias|titulares|actualidad)\b", re.I)
_RECENCY = re.compile(
    r"\b(today|tonight|yesterday|tomorrow|latest|recent|current(?:ly)?|"
    r"right now|real[- ]?time|live|hoy|ayer|mañana|ahora|últim[oa]s?|"
    r"score|stock price|share price|exchange rate)\b", re.I,
)
_DAILY_RECENCY = re.compile(
    r"\b(today|tonight|yesterday|tomorrow|this morning|this afternoon|"
    r"right now|real[- ]?time|live|hoy|ayer|mañana|ahora|"
    r"scores?|standings|stock prices?|share prices?|market prices?|exchange rates?|"
    r"(?:bitcoin|btc|ethereum|eth|gold|oil) (?:price|value)|"
    r"(?:price|value) of (?:bitcoin|btc|ethereum|eth|gold|oil)|traffic|open now)\b", re.I,
)
_MONTHS = {
    name: i for i, names in enumerate((
        ("january", "jan", "enero"), ("february", "feb", "febrero"),
        ("march", "mar", "marzo"), ("april", "apr", "abril"),
        ("may", "mayo"), ("june", "jun", "junio"),
        ("july", "jul", "julio"), ("august", "aug", "agosto"),
        ("september", "sep", "sept", "septiembre"),
        ("october", "oct", "octubre"), ("november", "nov", "noviembre"),
        ("december", "dec", "diciembre"),
    ), 1) for name in names
}
_MONTH_PATTERN = "|".join(_MONTHS)


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(str(value))
            except (ValueError, TypeError, OverflowError):
                return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _dates_in(text: str, reference: date) -> list[date]:
    candidates = []
    for year, month, day in re.findall(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text):
        candidates.append((int(year), int(month), int(day)))
    for month, day, year in re.findall(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", text):
        candidates.append((int(year), int(month), int(day)))
    for month, day, year in re.findall(
        rf"\b({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?\b",
        text, re.I,
    ):
        candidates.append((int(year or reference.year), _MONTHS[month.lower()], int(day)))
    for day, month, year in re.findall(
        rf"\b(\d{{1,2}})\s+(?:de\s+)?({_MONTH_PATTERN})(?:\s+(?:de\s+)?(20\d{{2}}))?\b",
        text, re.I,
    ):
        candidates.append((int(year or reference.year), _MONTHS[month.lower()], int(day)))
    result = []
    for parts in candidates:
        try:
            result.append(date(*parts))
        except ValueError:
            continue
    return result


def _normalize(text: str) -> str:
    return " ".join("".join(
        c for c in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(c)
    ).split())


def _location(text: str) -> str:
    # The last location in a follow-up overrides the earlier city.
    matches = re.findall(
        r"\b(?:in|for|at|en|para|what about|how about)\s+([^\n?]+?)"
        r"(?=\b(?:in|for|at|en|para)\s+|[\n?]|$)", text, re.I,
    )
    if not matches:
        prefix = re.match(r"^([\w ,.-]+?)\s+(?:weather|forecast|clima)\b", text, re.I)
        if prefix and not re.search(r"\b(what|how|the|today|tomorrow|give|show|check)\b", prefix.group(1), re.I):
            return prefix.group(1).strip()
        return ""
    for value in reversed(matches):
        value = re.split(
            r"\b(?:today|tonight|tomorrow|yesterday|right now|hoy|mañana|ayer|on|weather|forecast)\b",
            value, maxsplit=1, flags=re.I,
        )[0].strip(" ,.!:")
        if value and not re.match(rf"^(?:20\d{{2}}|\d{{1,2}}[/-]|(?:{_MONTH_PATTERN})\s+\d)", value, re.I):
            return value
    return ""


@dataclass(frozen=True)
class LiveSearchRequest:
    query: str
    now: datetime
    topic: str
    target_day: date
    current: bool
    location: str

    @property
    def needs_location(self) -> bool:
        return self.topic == "weather" and not self.location

    @property
    def provider_query(self) -> str:
        if not self.current:
            return self.query
        if self.topic == "general" and not _DAILY_RECENCY.search(self.query):
            return (
                f"{self.query}\nAs of local date: {self.now.date().isoformat()}. "
                "Find relevant authoritative web evidence, including official "
                "documentation and product or organization pages when appropriate. "
                "Use current editions for changing facts; include publication or "
                "update dates when available. Historical background may be older."
            )
        return (
            f"{self.query}\nCurrent local date: {self.now.date().isoformat()}. "
            f"Requested date: {self.target_day.isoformat()}. "
            "Use current sources with explicit dates; exclude archived forecasts."
        )


def prepare_live_search(
    text: str,
    *,
    conversation_history: Optional[Sequence[dict]] = None,
    current_time_context: str = "",
) -> LiveSearchRequest:
    stamp = re.search(r"Current date/time:\s*([^\s]+)", current_time_context)
    now = _parse_time(stamp.group(1)) if stamp else None
    now = now or datetime.now(timezone.utc)
    query = contextual_lookup_text(text, conversation_history)
    topic = "weather" if _WEATHER.search(query) else "news" if _NEWS.search(query) else "general"
    day_text = text
    if query != text and not _RECENCY.search(text) and not _dates_in(text, now.date()):
        day_text = query
    requested_dates = _dates_in(day_text, now.date())
    target = requested_dates[-1] if requested_dates else now.date()
    if not requested_dates and re.search(r"\b(tomorrow|mañana)\b", day_text, re.I):
        target += timedelta(days=1)
    elif not requested_dates and re.search(r"\b(yesterday|ayer)\b", day_text, re.I):
        target -= timedelta(days=1)
    requested_year = re.search(r"\b(?:in|en)\s+(20\d{2})\b", day_text, re.I)
    historical = bool(
        re.search(r"\b(historical|history of|historia)\b", text, re.I)
        or (requested_year and int(requested_year.group(1)) < now.year)
        or (requested_dates and target < now.date() - timedelta(days=2))
    )
    location = _location(query) if topic in {"weather", "news"} else ""
    return LiveSearchRequest(query, now, topic, target, not historical, location)


def usable_search_results(output: Any, request: LiveSearchRequest) -> list[dict]:
    """Drop empty, undated-current, stale, and wrong-location evidence."""
    if not isinstance(output, list):
        return []
    usable = []
    seen = set()
    for item in output:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        try:
            parsed_url = urlparse(url)
        except ValueError:
            continue
        snippet = str(item.get("snippet") or item.get("content") or "").strip()
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or not snippet or url in seen:
            continue
        title = str(item.get("title") or url)
        published = _parse_time(item.get("published_at") or item.get("published_date"))
        raw_published = str(item.get("published_at") or item.get("published_date") or "")
        if raw_published and not published:
            continue
        publication_is_date = bool(re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw_published))
        if publication_is_date:
            publication_day = date.fromisoformat(raw_published)
            if request.current and publication_day > request.now.date():
                continue
            published = datetime.combine(publication_day, time.min, tzinfo=request.now.tzinfo)
        title_dates = _dates_in(f"{title} {url}", request.now.date())
        archive_dates = _dates_in(url, request.now.date())
        content_dates = _dates_in(snippet, request.now.date())
        if request.current and published and published > request.now + timedelta(minutes=10):
            continue
        if request.current and (
            request.topic == "news" or (request.topic == "general" and _DAILY_RECENCY.search(request.query))
        ):
            dated = published.astimezone(request.now.tzinfo).date() if published else max(title_dates + content_dates, default=None)
            if dated is None or not request.now.date() - timedelta(days=2) <= dated <= request.now.date():
                continue
            if (
                (request.topic == "general" and _DAILY_RECENCY.search(request.query))
                or
                request.target_day != request.now.date()
                or re.search(r"\b(today|tonight|hoy|this morning)\b", request.query, re.I)
            ) and dated != request.target_day:
                continue
            if title_dates and max(title_dates) < request.now.date() - timedelta(days=2):
                continue
            if archive_dates and max(archive_dates) < request.now.date() - timedelta(days=2):
                continue
        if request.current and request.topic == "weather":
            # Publication alone does not establish which forecast day is covered.
            if request.target_day not in title_dates + content_dates:
                continue
            if title_dates and request.target_day not in title_dates:
                continue
            if archive_dates and request.target_day not in archive_dates:
                continue
            if published and published < request.now - timedelta(days=2):
                continue
        if request.current and request.location:
            locations = {_normalize(request.location)}
            if locations & {"new york", "new york city", "nyc", "ny", "nueva york"}:
                locations.update({"new york", "nyc"})
            if locations & {"dominican republic", "dominixan republic", "republica dominicana"}:
                locations.update({"dominican republic", "republica dominicana"})
            haystack = _normalize(f"{title} {snippet}")
            if not any(re.search(rf"(?<!\w){re.escape(place)}(?!\w)", haystack) for place in locations):
                continue
        result = {
            **item, "title": title, "url": url, "snippet": snippet,
            "retrieved_at": request.now.isoformat(timespec="seconds"),
        }
        if published:
            result["published_at"] = raw_published if publication_is_date else published.isoformat(timespec="seconds")
        if request.topic == "weather" and request.current:
            result["forecast_date"] = request.target_day.isoformat()
        usable.append(result)
        seen.add(url)
    return usable


def source_descriptor(item: dict) -> dict:
    return {
        key: item[key] for key in (
            "title", "url", "provider", "published_at", "retrieved_at", "forecast_date"
        ) if item.get(key)
    }


def source_detail(source: dict) -> str:
    parts = ["Web source"]
    if source.get("forecast_date"):
        parts.append(f"Forecast for {source['forecast_date']}")
    if source.get("published_at"):
        parts.append(f"Published {source['published_at']}")
    if source.get("retrieved_at"):
        parts.append(f"Retrieved {source['retrieved_at']}")
    return " • ".join(parts)


def source_navigator(sources: Sequence[dict], block_id: str) -> list[dict]:
    items = [
        {
            "label": str(source.get("title") or source.get("name") or "Web source"),
            "detail": source_detail(source),
            "url": str(source["url"]),
        }
        for source in sources if isinstance(source, dict) and source.get("url")
    ]
    if not items:
        return []
    return [{
        "id": block_id, "schema_version": 1, "type": "interactive",
        "subtype": "sourceNavigator",
        "content": {"title": "Sources used", "items": items},
        "metadata": {"role": "grounding"},
    }]
