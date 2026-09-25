"""One timezone convention for every Community timestamp.

Community tables store ``TIMESTAMP WITHOUT TIME ZONE`` values that mean UTC.
Clients send ISO-8601 instants with an offset (web ``toISOString()``, iOS
``.iso8601``, Android ``Instant.toString()``), and asyncpg refuses to bind an
offset-aware ``datetime`` to a naive column — that mismatch made every event
creation from every client a 500 on PostgreSQL while SQLite-backed tests
passed. So:

* anything going *into* the database passes through :func:`to_naive_utc`;
* anything going *out* to a client passes through :func:`as_utc`, so the JSON
  carries an explicit ``Z`` and no client guesses the zone (iOS's decoder
  rejects offset-less dates outright; web and Android read them as device
  local time, which shifted every event by the viewer's UTC offset).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Annotated, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, PlainSerializer


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Convert any datetime to the naive-UTC storage convention."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Attach UTC to a stored naive value (or normalize an aware one)."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_now() -> datetime:
    """Naive UTC "now", comparable with stored Community timestamps."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize_utc(value: Optional[datetime]) -> Optional[str]:
    normalized = as_utc(value)
    if normalized is None:
        return None
    # Whole seconds keep every client parser happy (iOS's ISO8601DateFormatter
    # is strict about fractional-second width) and events never need more.
    return normalized.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# Input side: whatever offset the client used, store naive UTC.
StoredUTCDateTime = Annotated[datetime, AfterValidator(to_naive_utc)]

# Output side: always emit an explicit UTC instant.
UTCDateTime = Annotated[
    datetime,
    PlainSerializer(_serialize_utc, return_type=Optional[str], when_used="json-unless-none"),
]


def resolve_zone(name: Optional[str]) -> tzinfo:
    """Return a timezone for "today" windows; unknown names fall back to UTC."""
    if not name:
        return timezone.utc
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return timezone.utc


def day_window(zone: tzinfo, now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Naive-UTC bounds of the viewer's current calendar day."""
    current = as_utc(now) if now else datetime.now(timezone.utc)
    local = current.astimezone(zone)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return to_naive_utc(start_local), to_naive_utc(end_local)


def week_window(zone: tzinfo, now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Naive-UTC bounds from the start of today through the next seven days."""
    start, _ = day_window(zone, now)
    return start, start + timedelta(days=7)
