"""Deterministic Chat adapter for the Lyo Coach control plane.

Coach answers are derived from structured goals and canonical evidence. This
module intentionally performs no model call: "what should I study now?" should
feel instant and should not be reinterpreted by a probabilistic router.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import TodayCoachView
from .service import build_today_view


_COACH_REQUEST_RE = re.compile(
    r"\b(?:"
    r"what should i (?:study|work on|do next)|"
    r"what do i need to work on|"
    r"what(?:'s| is) my mission(?: today)?|"
    r"my mission today|"
    r"how ready am i|am i ready|show me my readiness"
    r")\b",
    re.IGNORECASE,
)
_TIME_ONLY_COACH_RE = re.compile(
    r"^\s*i have (?:\d{1,3}\s*(?:min|mins|minutes)|half an hour|an hour|one hour)"
    r"(?:\s*[,;:-]?\s*(?:what should i (?:study|work on|do next)|what now))?"
    r"\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_MINUTES_RE = re.compile(r"\b(\d{1,3})\s*(?:minutes?|mins?|min)\b", re.IGNORECASE)

_ACTION_LABELS = {
    "diagnose": "Quick check",
    "remediate": "Repair the gap",
    "guide": "Guided practice",
    "check_application": "Apply it",
    "check_transfer": "Challenge",
    "review": "Retrieve it",
    "advance": "Light review",
}


def is_coach_request(text: str) -> bool:
    """Return True only for explicit next-best-study/readiness requests."""

    value = (text or "").strip()
    return bool(_COACH_REQUEST_RE.search(value) or _TIME_ONLY_COACH_RE.fullmatch(value))


def requested_minutes(text: str) -> Optional[int]:
    """Extract an explicit learner time budget and clamp unsafe extremes."""

    value = (text or "").strip().lower()
    if "half an hour" in value:
        return 30
    if "an hour" in value or "one hour" in value:
        return 60
    match = _MINUTES_RE.search(value)
    if not match:
        return None
    return max(5, min(180, int(match.group(1))))


def format_coach_answer(view: TodayCoachView, *, budget_minutes: Optional[int] = None) -> str:
    """Human-readable companion to the structured coach_mission SSE event."""

    if not view.active_goals:
        return (
            "You do not have an active learning goal yet. Tell me about a test, "
            "assignment, course, certification, or skill you want to master and "
            "I will turn it into a goal."
        )

    lines = [view.coach_note]
    primary_id = view.primary_goal_id
    readiness = view.readiness.get(primary_id) if primary_id else None
    if readiness is not None:
        label = {
            "ready": "Ready",
            "getting_there": "Getting there",
            "not_ready": "Not ready yet",
        }.get(readiness.readiness_level, "Readiness unavailable")
        lines.append(
            f"Readiness: {label}. "
            f"{readiness.assessed_skills}/{readiness.total_skills} required skills assessed."
        )

    if not view.mission:
        return "\n\n".join(lines)

    if budget_minutes is not None:
        lines.append(
            f"I used your {budget_minutes}-minute limit and kept the mission within it."
        )

    mission_lines = [f"Today's mission ({view.total_minutes} min):"]
    for index, item in enumerate(view.mission, start=1):
        action = _ACTION_LABELS.get(item.action, "Study")
        mission_lines.append(
            f"{index}. {item.title} — {action}, {item.estimated_minutes} min"
        )
    lines.append("\n".join(mission_lines))
    return "\n\n".join(lines)


async def process_coach_turn(
    db: AsyncSession,
    user_id: int,
    text: str,
) -> Tuple[TodayCoachView, str, Optional[int]]:
    """Build an evidence-driven mission for Chat with no LLM call."""

    budget = requested_minutes(text)
    view = await build_today_view(
        db,
        user_id,
        minute_cap_override=budget,
    )
    answer = format_coach_answer(view, budget_minutes=budget)
    return view, answer, budget
