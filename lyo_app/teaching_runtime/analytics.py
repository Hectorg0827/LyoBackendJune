"""Empirical Learning OS outcome analytics.

Turns the immutable LearningEvent stream into product measurements without
trusting client-reported mastery. Only metrics supported by durable data are
calculated. Model cost remains explicitly unavailable until model usage can be
linked to the same durable session/outcome identity.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.events.evidence import evidence_rank, normalize_evidence_kind
from lyo_app.events.models import LearningEvent


_RETENTION_TARGETS = {"retention", "retrieval"}
_MEANINGFUL_TARGETS = {
    "recognition", "explanation", "application", "transfer", "retention"
}


def _safe_metadata(event: Any) -> Mapping[str, Any]:
    value = getattr(event, "metadata_json", None)
    return value if isinstance(value, Mapping) else {}


def _intervention(event: Any) -> Mapping[str, Any]:
    raw = _safe_metadata(event).get("teaching_intervention")
    return raw if isinstance(raw, Mapping) else {}


def _normalized_target(event: Any) -> Optional[str]:
    raw = _intervention(event).get("target_evidence_type")
    if raw in _RETENTION_TARGETS:
        return "retention"
    normalized = normalize_evidence_kind(str(raw)) if raw else None
    if normalized:
        return normalized
    evidence = normalize_evidence_kind(getattr(event, "evidence_type", None))
    return evidence if evidence in _MEANINGFUL_TARGETS else None


def _is_attempt(event: Any) -> bool:
    return bool(
        getattr(event, "concept_id", None)
        and getattr(event, "measurable_outcome", None) is not None
    )


def _succeeded(event: Any) -> bool:
    try:
        return float(getattr(event, "measurable_outcome", 0.0) or 0.0) >= 0.5
    except (TypeError, ValueError):
        return False


def _response_seconds(event: Any) -> Optional[float]:
    raw = _safe_metadata(event).get("response_time_seconds")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if 0.0 < value < 3600.0 else None


def _session_key(event: Any) -> Optional[str]:
    metadata = _safe_metadata(event)
    for name in ("session_id", "conversation_id"):
        value = metadata.get(name)
        if value:
            surface = getattr(event, "source_surface", None) or "unknown"
            return f"{surface}:{str(value)[:128]}"
    return None


def _rate(successes: int, attempts: int) -> Optional[float]:
    return round(successes / attempts, 4) if attempts else None


def _event_time(event: Any) -> datetime:
    timestamp = getattr(event, "timestamp", None)
    return timestamp if isinstance(timestamp, datetime) else datetime.min


def _concept_key(event: Any) -> tuple[Any, str]:
    return (
        getattr(event, "user_id", None),
        str(getattr(event, "concept_id", "") or ""),
    )


def aggregate_learning_os_events(
    events: Iterable[Any],
    *,
    since: datetime,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Aggregate evidence/intervention outcomes for one reporting window.

    Input may include lookback rows before since so continuity, retention gaps
    and rung gains have a valid baseline. Only rows at or after since contribute
    to reported attempts.
    """
    now = now or datetime.utcnow()
    ordered = sorted(
        [event for event in events if _is_attempt(event)],
        key=_event_time,
    )
    window = [event for event in ordered if _event_time(event) >= since]

    action_groups: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {
            "attempts": 0,
            "successes": 0,
            "hinted": 0,
            "hint_free_successes": 0,
        }
    )
    attributed = 0
    hint_groups = {
        "hint_free": {"attempts": 0, "successes": 0},
        "hinted": {"attempts": 0, "successes": 0},
    }

    transfer_attempts = transfer_successes = transfer_unaided_successes = 0
    retention = {
        "1d": {"attempts": 0, "successes": 0},
        "7d": {"attempts": 0, "successes": 0},
        "30d": {"attempts": 0, "successes": 0},
    }
    remediation_candidates = remediation_repairs = 0
    repair_hours: list[float] = []

    cross = {
        "attempts": 0,
        "successes": 0,
        "retention_attempts": 0,
        "retention_successes": 0,
    }
    same = {"attempts": 0, "successes": 0}
    transitions: dict[str, dict[str, int]] = defaultdict(
        lambda: {"attempts": 0, "successes": 0}
    )

    timed_attempts = 0
    timed_seconds = 0.0
    timed_rung_gain = 0

    strongest_rank: dict[tuple[Any, str], int] = {}
    previous_event: dict[tuple[Any, str], Any] = {}
    previous_positive: dict[tuple[Any, str], Any] = {}
    previous_failure: dict[tuple[Any, str], Any] = {}

    sessions: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "attempts": 0,
            "successes": 0,
            "high_rung_successes": 0,
            "response_seconds": 0.0,
        }
    )

    for event in ordered:
        key = _concept_key(event)
        event_time = _event_time(event)
        in_window = event_time >= since
        success = _succeeded(event)
        target = _normalized_target(event)
        intervention = _intervention(event)
        actual_kind = normalize_evidence_kind(getattr(event, "evidence_type", None))
        current_rank = evidence_rank(actual_kind)
        prior = previous_event.get(key)
        prior_positive = previous_positive.get(key)
        prior_failure = previous_failure.get(key)
        prior_rank = strongest_rank.get(key, 0)

        if in_window:
            hints = max(0, int(getattr(event, "hints_used", 0) or 0))
            hint_key = "hinted" if hints else "hint_free"
            hint_groups[hint_key]["attempts"] += 1
            hint_groups[hint_key]["successes"] += int(success)

            action = str(intervention.get("action") or "unattributed")
            instrument = str(intervention.get("preferred_instrument") or "none")
            target_label = target or "unknown"
            group = action_groups[(action, instrument, target_label)]
            group["attempts"] += 1
            group["successes"] += int(success)
            group["hinted"] += int(hints > 0)
            group["hint_free_successes"] += int(success and hints == 0)
            attributed += int(bool(intervention.get("action")))

            if target == "transfer":
                transfer_attempts += 1
                transfer_successes += int(success)
                transfer_unaided_successes += int(success and hints == 0)

            if target == "retention" and prior_positive is not None:
                gap = event_time - _event_time(prior_positive)
                for label, days in (("1d", 1), ("7d", 7), ("30d", 30)):
                    if gap >= timedelta(days=days):
                        retention[label]["attempts"] += 1
                        retention[label]["successes"] += int(success)

            if intervention.get("action") == "remediate" and prior_failure is not None:
                gap = event_time - _event_time(prior_failure)
                if timedelta(0) <= gap <= timedelta(days=7):
                    remediation_candidates += 1
                    repaired = (
                        success
                        and current_rank >= evidence_rank("application")
                    )
                    remediation_repairs += int(repaired)
                    if repaired:
                        repair_hours.append(gap.total_seconds() / 3600.0)

            if prior is not None:
                old_surface = getattr(prior, "source_surface", None) or "unknown"
                new_surface = getattr(event, "source_surface", None) or "unknown"
                if old_surface != new_surface:
                    cross["attempts"] += 1
                    cross["successes"] += int(success)
                    if target == "retention":
                        cross["retention_attempts"] += 1
                        cross["retention_successes"] += int(success)
                    transition = transitions[f"{old_surface}->{new_surface}"]
                    transition["attempts"] += 1
                    transition["successes"] += int(success)
                else:
                    same["attempts"] += 1
                    same["successes"] += int(success)

            seconds = _response_seconds(event)
            if seconds is not None:
                timed_attempts += 1
                timed_seconds += seconds
                if success and current_rank > prior_rank:
                    timed_rung_gain += current_rank - prior_rank

            session_key = _session_key(event)
            if session_key:
                session = sessions[session_key]
                session["attempts"] += 1
                session["successes"] += int(success)
                session["high_rung_successes"] += int(
                    success and current_rank >= evidence_rank("application")
                )
                seconds = _response_seconds(event)
                if seconds is not None:
                    session["response_seconds"] += seconds

        if success and current_rank >= 0:
            strongest_rank[key] = max(prior_rank, current_rank)
            previous_positive[key] = event
        if not success:
            previous_failure[key] = event
        previous_event[key] = event

    action_rows = []
    for (action, instrument, target), values in sorted(action_groups.items()):
        unhinted_attempts = max(values["attempts"] - values["hinted"], 0)
        action_rows.append(
            {
                "action": action,
                "instrument": instrument,
                "target_evidence": target,
                **values,
                "success_rate": _rate(values["successes"], values["attempts"]),
                "hint_free_success_rate": _rate(
                    values["hint_free_successes"], unhinted_attempts
                ),
            }
        )

    for values in hint_groups.values():
        values["success_rate"] = _rate(values["successes"], values["attempts"])
    for values in retention.values():
        values["success_rate"] = _rate(values["successes"], values["attempts"])

    transition_rows = []
    for name, values in sorted(transitions.items()):
        transition_rows.append(
            {
                "transition": name,
                **values,
                "success_rate": _rate(values["successes"], values["attempts"]),
            }
        )

    session_rows = list(sessions.values())
    successful_sessions = sum(
        1 for value in session_rows if value["high_rung_successes"] > 0
    )
    total_sessions = len(session_rows)
    minutes = timed_seconds / 60.0

    return {
        "generated_at": now.isoformat(),
        "window_start": since.isoformat(),
        "evidence_attempts": len(window),
        "intervention_attribution": {
            "attributed_attempts": attributed,
            "coverage_rate": _rate(attributed, len(window)),
        },
        "intervention_outcomes": action_rows,
        "remediation": {
            "eligible_followups": remediation_candidates,
            "repaired": remediation_repairs,
            "repair_rate": _rate(remediation_repairs, remediation_candidates),
            "median_time_to_repair_hours": (
                round(sorted(repair_hours)[len(repair_hours) // 2], 2)
                if repair_hours
                else None
            ),
        },
        "transfer": {
            "attempts": transfer_attempts,
            "successes": transfer_successes,
            "success_rate": _rate(transfer_successes, transfer_attempts),
            "unaided_successes": transfer_unaided_successes,
            "unaided_success_rate": _rate(
                transfer_unaided_successes, transfer_attempts
            ),
        },
        "retention": retention,
        "hint_dependency": hint_groups,
        "cross_surface_continuity": {
            "cross_surface": {
                **cross,
                "success_rate": _rate(cross["successes"], cross["attempts"]),
                "retention_success_rate": _rate(
                    cross["retention_successes"], cross["retention_attempts"]
                ),
            },
            "same_surface": {
                **same,
                "success_rate": _rate(same["successes"], same["attempts"]),
            },
            "transitions": transition_rows,
        },
        "learning_gain_per_active_minute": {
            "timed_attempts": timed_attempts,
            "timing_coverage_rate": _rate(timed_attempts, len(window)),
            "active_response_minutes": round(minutes, 3),
            "new_evidence_rungs": timed_rung_gain,
            "rungs_per_active_minute": (
                round(timed_rung_gain / minutes, 4) if minutes > 0 else None
            ),
        },
        "sessions": {
            "identified_sessions": total_sessions,
            "successful_sessions": successful_sessions,
            "success_rate": _rate(successful_sessions, total_sessions),
        },
        "model_cost_per_successful_session": {
            "available": False,
            "reason": (
                "Model token/cost usage is not yet durably linked to the same "
                "session identity as learner evidence; no cost estimate is fabricated."
            ),
        },
    }


async def load_learning_os_analytics(
    db: AsyncSession,
    *,
    days: int = 30,
    user_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Load a bounded event window and return Learning OS outcome analytics."""
    now = now or datetime.utcnow()
    days = max(1, min(int(days), 90))
    since = now - timedelta(days=days)
    lookback = since - timedelta(days=31)

    query = select(LearningEvent).where(
        LearningEvent.timestamp >= lookback,
        LearningEvent.measurable_outcome.is_not(None),
        LearningEvent.concept_id.is_not(None),
    )
    if user_id is not None:
        query = query.where(LearningEvent.user_id == int(user_id))

    result = await db.execute(query.order_by(LearningEvent.timestamp.asc()))
    rows = list(result.scalars().all())
    return aggregate_learning_os_events(rows, since=since, now=now)
