from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from lyo_app.api.v1 import learning_os_analytics as analytics_routes
from lyo_app.teaching_runtime.analytics import aggregate_learning_os_events


def event(
    when,
    *,
    user_id=42,
    concept="fractions",
    correct=True,
    kind="application",
    surface="chat",
    action=None,
    instrument=None,
    target=None,
    hints=0,
    seconds=None,
    session=None,
    misconception=None,
):
    intervention = {}
    if action:
        intervention["action"] = action
    if instrument:
        intervention["preferred_instrument"] = instrument
    if target:
        intervention["target_evidence_type"] = target
    metadata = {}
    if intervention:
        metadata["teaching_intervention"] = intervention
    if seconds is not None:
        metadata["response_time_seconds"] = seconds
    if session is not None:
        metadata["session_id" if surface == "classroom" else "conversation_id"] = session
    return SimpleNamespace(
        user_id=user_id,
        concept_id=concept,
        measurable_outcome=1.0 if correct else 0.0,
        evidence_type=kind if correct else "exposure",
        source_surface=surface,
        hints_used=hints,
        misconception=misconception,
        metadata_json=metadata,
        timestamp=when,
    )


def usage_event(
    when,
    *,
    user_id=42,
    surface="chat",
    session="chat-1",
    model="gpt-4o-mini",
    tokens=100,
    cache_hit=False,
):
    return SimpleNamespace(
        user_id=user_id,
        concept_id=None,
        measurable_outcome=None,
        evidence_type=None,
        source_surface=surface,
        hints_used=0,
        misconception=None,
        metadata_json={
            "event_kind": "model_usage",
            "session_id": session,
            "model": model,
            "tokens_used": tokens,
            "latency_ms": 250,
            "cache_hit": cache_hit,
        },
        timestamp=when,
    )


def test_empirical_report_measures_repair_transfer_retention_and_continuity():
    start = datetime(2026, 9, 1, 12, 0, 0)
    rows = [
        event(
            start,
            correct=False,
            kind="exposure",
            surface="chat",
            action="check_application",
            target="application",
            seconds=20,
            session="chat-1",
            misconception="compares denominators directly",
        ),
        event(
            start + timedelta(hours=2),
            correct=True,
            kind="application",
            surface="classroom",
            action="remediate",
            instrument="worked_example",
            target="application",
            seconds=30,
            session="class-1",
        ),
        event(
            start + timedelta(days=1),
            correct=True,
            kind="transfer",
            surface="classroom",
            action="check_transfer",
            instrument="novel_scenario",
            target="transfer",
            seconds=20,
            session="class-1",
        ),
        event(
            start + timedelta(days=9),
            correct=True,
            kind="retention",
            surface="chat",
            action="review",
            instrument="retrieval",
            target="retention",
            seconds=10,
            session="chat-2",
        ),
    ]

    report = aggregate_learning_os_events(
        rows,
        since=start,
        now=start + timedelta(days=10),
    )

    assert report["evidence_attempts"] == 4
    assert report["intervention_attribution"]["coverage_rate"] == 1.0

    assert report["remediation"]["eligible_followups"] == 1
    assert report["remediation"]["repaired"] == 1
    assert report["remediation"]["repair_rate"] == 1.0

    assert report["transfer"]["attempts"] == 1
    assert report["transfer"]["success_rate"] == 1.0
    assert report["transfer"]["unaided_success_rate"] == 1.0

    assert report["retention"]["1d"]["attempts"] == 1
    assert report["retention"]["7d"]["attempts"] == 1
    assert report["retention"]["30d"]["attempts"] == 0
    assert report["retention"]["7d"]["success_rate"] == 1.0

    cross = report["cross_surface_continuity"]["cross_surface"]
    same = report["cross_surface_continuity"]["same_surface"]
    assert cross["attempts"] == 2
    assert cross["success_rate"] == 1.0
    assert same["attempts"] == 1
    assert same["success_rate"] == 1.0

    gain = report["learning_gain_per_active_minute"]
    assert gain["timed_attempts"] == 4
    assert gain["timing_coverage_rate"] == 1.0
    assert gain["new_evidence_rungs"] == 5
    assert gain["active_response_minutes"] == 1.333
    assert gain["rungs_per_active_minute"] == 3.75

    assert report["sessions"]["identified_sessions"] == 3
    assert report["sessions"]["successful_sessions"] == 2
    assert report["sessions"]["success_rate"] == 0.6667
    assert report["model_usage"]["tokens"] == 0
    assert report["model_usage"]["tokens_per_successful_session"] == 0.0
    assert report["model_cost_per_successful_session"]["available"] is False


def test_model_usage_is_joined_to_learning_sessions_without_inventing_cost():
    start = datetime(2026, 9, 1, 12, 0, 0)
    rows = [
        event(
            start,
            correct=True,
            kind="application",
            surface="chat",
            action="guide",
            target="application",
            session="chat-1",
        ),
        event(
            start + timedelta(minutes=3),
            concept="ratios",
            correct=False,
            kind="application",
            surface="classroom",
            action="check_application",
            target="application",
            session="class-1",
        ),
        usage_event(
            start + timedelta(seconds=1),
            surface="chat",
            session="chat-1",
            model="gpt-4o-mini",
            tokens=120,
        ),
        usage_event(
            start + timedelta(minutes=2),
            surface="chat",
            session="chat-1",
            model="gpt-4o-mini",
            tokens=0,
            cache_hit=True,
        ),
        usage_event(
            start + timedelta(minutes=3, seconds=1),
            surface="classroom",
            session="class-1",
            model="gemini-2.5-flash",
            tokens=180,
        ),
    ]

    report = aggregate_learning_os_events(rows, since=start)

    usage = report["model_usage"]
    assert usage["calls"] == 3
    assert usage["tokens"] == 300
    assert usage["cache_hits"] == 1
    assert usage["linked_learning_sessions"] == 2
    assert usage["session_attribution_rate"] == 1.0
    # Efficiency denominator is successful learning sessions, while the
    # numerator includes spend on both successful and unsuccessful sessions.
    assert usage["tokens_per_successful_session"] == 300.0
    assert usage["by_model"] == [
        {"model": "gemini-2.5-flash", "calls": 1, "tokens": 180},
        {"model": "gpt-4o-mini", "calls": 2, "tokens": 120},
    ]
    assert report["model_cost_per_successful_session"]["available"] is False
    assert "prices are not versioned" in report["model_cost_per_successful_session"]["reason"]


def test_model_usage_outside_an_evidence_session_stays_visible_but_unlinked():
    start = datetime(2026, 9, 1, 12, 0, 0)
    rows = [
        event(start, session="chat-1"),
        usage_event(
            start + timedelta(seconds=1),
            session="chat-other",
            tokens=75,
        ),
    ]

    report = aggregate_learning_os_events(rows, since=start)
    usage = report["model_usage"]
    assert usage["tokens"] == 75
    assert usage["sessions_with_usage"] == 1
    assert usage["linked_learning_sessions"] == 0
    assert usage["session_attribution_rate"] == 0.0
    assert usage["linked_tokens"] == 0
    assert usage["tokens_per_successful_session"] == 0.0


def test_hint_dependency_separates_helped_from_unaided_work():
    start = datetime(2026, 9, 1, 12, 0, 0)
    rows = [
        event(
            start,
            correct=True,
            kind="application",
            action="guide",
            target="application",
            hints=0,
        ),
        event(
            start + timedelta(minutes=2),
            concept="ratios",
            correct=False,
            kind="application",
            action="guide",
            target="application",
            hints=2,
        ),
    ]

    report = aggregate_learning_os_events(rows, since=start)
    assert report["hint_dependency"]["hint_free"] == {
        "attempts": 1,
        "successes": 1,
        "success_rate": 1.0,
    }
    assert report["hint_dependency"]["hinted"] == {
        "attempts": 1,
        "successes": 0,
        "success_rate": 0.0,
    }


def test_lookback_rows_establish_baseline_but_do_not_inflate_window_attempts():
    start = datetime(2026, 10, 1, 12, 0, 0)
    rows = [
        event(
            start - timedelta(days=8),
            correct=True,
            kind="transfer",
            surface="classroom",
            action="check_transfer",
            target="transfer",
        ),
        event(
            start + timedelta(hours=1),
            correct=True,
            kind="retention",
            surface="chat",
            action="review",
            target="retention",
        ),
    ]

    report = aggregate_learning_os_events(rows, since=start)
    assert report["evidence_attempts"] == 1
    assert report["retention"]["7d"]["attempts"] == 1
    assert report["cross_surface_continuity"]["cross_surface"]["attempts"] == 1



def test_already_repaired_failure_is_not_credited_to_later_remediation():
    start = datetime(2026, 9, 1, 12, 0, 0)
    rows = [
        event(
            start,
            correct=False,
            kind="application",
            action="check_application",
            target="application",
            misconception="sign error",
        ),
        event(
            start + timedelta(hours=1),
            correct=True,
            kind="application",
            action="check_application",
            target="application",
        ),
        event(
            start + timedelta(hours=2),
            correct=True,
            kind="application",
            action="remediate",
            target="application",
        ),
    ]

    report = aggregate_learning_os_events(rows, since=start)
    assert report["remediation"]["eligible_followups"] == 0
    assert report["remediation"]["repair_rate"] is None



@pytest.mark.asyncio
async def test_personal_report_is_scoped_to_authenticated_user(monkeypatch):
    loader = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(analytics_routes, "load_learning_os_analytics", loader)

    db = object()
    result = await analytics_routes.my_learning_os_analytics(
        days=14,
        db=db,
        current_user=SimpleNamespace(id=42),
    )

    assert result == {"ok": True}
    loader.assert_awaited_once_with(db, days=14, user_id=42)


@pytest.mark.asyncio
async def test_system_report_requires_durable_rbac_permission(monkeypatch):
    has_permission = AsyncMock(return_value=False)
    has_role = AsyncMock(return_value=False)
    monkeypatch.setattr(
        analytics_routes.RBACService, "user_has_permission", has_permission
    )
    monkeypatch.setattr(
        analytics_routes.RBACService, "user_has_role", has_role
    )

    with pytest.raises(HTTPException) as exc:
        await analytics_routes.system_learning_os_analytics(
            days=30,
            db=object(),
            current_user=SimpleNamespace(id=42),
        )

    assert exc.value.status_code == 403
    has_permission.assert_awaited_once()
    has_role.assert_awaited_once()


@pytest.mark.asyncio
async def test_system_report_returns_only_aggregate_loader_result(monkeypatch):
    monkeypatch.setattr(
        analytics_routes.RBACService,
        "user_has_permission",
        AsyncMock(return_value=True),
    )
    loader = AsyncMock(return_value={"evidence_attempts": 12})
    monkeypatch.setattr(analytics_routes, "load_learning_os_analytics", loader)

    db = object()
    result = await analytics_routes.system_learning_os_analytics(
        days=30,
        db=db,
        current_user=SimpleNamespace(id=42),
    )

    assert result == {"evidence_attempts": 12}
    loader.assert_awaited_once_with(db, days=30)



def test_cross_surface_continuity_ignores_attempts_more_than_30_days_apart():
    start = datetime(2026, 8, 1, 12, 0, 0)
    rows = [
        event(
            start,
            correct=True,
            kind="application",
            surface="chat",
            action="check_application",
            target="application",
        ),
        event(
            start + timedelta(days=31),
            correct=True,
            kind="transfer",
            surface="classroom",
            action="check_transfer",
            target="transfer",
        ),
    ]

    report = aggregate_learning_os_events(
        rows,
        since=start,
        now=start + timedelta(days=32),
    )
    continuity = report["cross_surface_continuity"]
    assert continuity["max_gap_days"] == 30
    assert continuity["cross_surface"]["attempts"] == 0
    assert continuity["same_surface"]["attempts"] == 0



def test_same_surface_retention_is_available_as_cross_surface_control():
    start = datetime(2026, 9, 1, 12, 0, 0)
    rows = [
        event(
            start,
            correct=True,
            kind="transfer",
            surface="classroom",
            action="check_transfer",
            target="transfer",
        ),
        event(
            start + timedelta(days=8),
            correct=True,
            kind="retention",
            surface="classroom",
            action="review",
            target="retention",
        ),
    ]

    report = aggregate_learning_os_events(rows, since=start)
    same = report["cross_surface_continuity"]["same_surface"]
    assert same["retention_attempts"] == 1
    assert same["retention_successes"] == 1
    assert same["retention_success_rate"] == 1.0
