from datetime import datetime, timedelta
from types import SimpleNamespace

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
    assert report["model_cost_per_successful_session"]["available"] is False


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
