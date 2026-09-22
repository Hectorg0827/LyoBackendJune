"""Shared, deterministic Test Prep scheduling and continuation rules."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def local_day_bounds(zone, now=None):
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(zone))
    start = datetime.combine(local.date(), time.min, ZoneInfo(zone))
    end = datetime.combine(local.date() + timedelta(days=1), time.min, ZoneInfo(zone))
    return tuple(d.astimezone(timezone.utc).replace(tzinfo=None) for d in (start, end))


def normalize_schedule(items, profile, now=None):
    """Validate every generated session before any database write; no empty plans."""
    now = now or datetime.now(timezone.utc)
    zone = ZoneInfo((profile.workflow_state or {}).get("timezone", "UTC"))
    valid = []
    daily = {}
    topics = {str(t["name"]).strip().casefold(): str(t["name"]).strip() for t in profile.topics}
    for item in items:
        when = datetime.fromisoformat(item["scheduled_at"].replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=zone)
        local = when.astimezone(zone)
        minutes = int(item["duration_minutes"])
        topic = str(item["topic"]).strip()
        kind = item["session_type"]
        if topic.casefold() not in topics:
            raise ValueError("Session topic is not in the saved test profile")
        topic = topics[topic.casefold()]
        if not topic or len(topic) > 200 or kind not in {"learn", "practice", "review", "mock_test"}:
            raise ValueError("Invalid study activity")
        if when <= now or local.date() > profile.test_date or not 5 <= minutes <= profile.daily_minutes_available:
            raise ValueError("Session outside the learner's availability")
        if (profile.test_date - local.date()).days < 2:
            kind = "review"
        key = local.date()
        daily[key] = daily.get(key, 0) + minutes
        if daily[key] > profile.daily_minutes_available:
            raise ValueError("Daily study budget exceeded")
        valid.append({"scheduled_at": when.astimezone(timezone.utc).replace(tzinfo=None),
                      "duration_minutes": minutes, "topic": topic, "session_type": kind})
    if not valid:
        raise ValueError("Planner returned no sessions")
    weeks = {}
    for day in daily:
        week = (day - now.astimezone(zone).date()).days // 7
        weeks[week] = weeks.get(week, 0) + 1
    if any(count > profile.study_days_per_week for count in weeks.values()):
        raise ValueError("Weekly study availability exceeded")
    valid.sort(key=lambda row: row["scheduled_at"])
    for previous, following in zip(valid, valid[1:]):
        if previous["scheduled_at"] + timedelta(minutes=previous["duration_minutes"]) > following["scheduled_at"]:
            raise ValueError("Study sessions overlap")
    return valid


def profile_ready(profile):
    state = profile.workflow_state or {}
    return (bool(profile.subject.strip()) and profile.subject != "Pending Test"
            and "test_date" in state.get("known_fields", [])
            and bool(profile.topics) and "daily_minutes_available" in state.get("known_fields", []))


def baseline_schedule(profile, now=None):
    """A real, bounded schedule when the model cannot produce valid dates."""
    now = now or datetime.now(timezone.utc)
    zone = ZoneInfo((profile.workflow_state or {}).get("timezone", "UTC"))
    today = now.astimezone(zone).date()
    topics = sorted(profile.topics, key=lambda t: float(t.get("confidence", 5)))
    if not topics or profile.test_date < today:
        raise ValueError("No remaining time or topics")
    sessions = []
    kinds = ["learn", "learn", "practice", "learn", "review", "learn", "practice", "learn"]
    mock_used = False
    for offset in range(min((profile.test_date - today).days + 1, 366)):
        if offset % 7 >= profile.study_days_per_week:
            continue
        day = today + timedelta(days=offset)
        when = datetime.combine(day, time(18), zone)
        if when <= now:
            when = (now + timedelta(minutes=10)).astimezone(zone)
        if when.date() != day:
            continue
        remaining = (profile.test_date - day).days
        kind = kinds[len(sessions) % len(kinds)]
        if remaining < 2:
            kind = "review"
        elif remaining <= 7 and len(sessions) > 1 and not mock_used:
            kind = "mock_test"
            mock_used = True
        sessions.append({"scheduled_at": when.isoformat(), "duration_minutes": profile.daily_minutes_available,
                         "topic": topics[len(sessions) % len(topics)]["name"], "session_type": kind})
    return normalize_schedule(sessions, profile, now)


def evening_before(scheduled_at, zone):
    """20:00 on the preceding local day, stored as naive UTC like sessions."""
    local = scheduled_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(zone))
    evening = datetime.combine(local.date() - timedelta(days=1), time(20), ZoneInfo(zone))
    return evening.astimezone(timezone.utc).replace(tzinfo=None)
