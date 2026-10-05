"""Lyo Coach is a goal orchestrator over canonical evidence, not a second tutor."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lyo_app.coach.models import GoalSkill, LearningGoal
from lyo_app.coach.service import (
    _action_for_skill,
    _readiness,
    _state_for_skill,
    ensure_test_goal,
)
from lyo_app.coach.schemas import GoalSkillState
from lyo_app.events.concept_record import ConceptRecord, RungRecord
from lyo_app.study_plans.models import TestProfile


def _goal(days=5):
    now = datetime.utcnow()
    return LearningGoal(
        id="goal-1",
        user_id=7,
        goal_type="test",
        title="Biology test",
        subject="Biology",
        status="active",
        deadline=now + timedelta(days=days),
        desired_outcome={},
        constraints={"daily_minutes": 25},
        created_at=now,
        updated_at=now,
    )


def _skill(name="Mitosis", weight=1.0):
    now = datetime.utcnow()
    return GoalSkill(
        id=f"skill-{name}",
        goal_id="goal-1",
        user_id=7,
        concept_id=name.lower().replace(" ", "_"),
        display_name=name,
        weight=weight,
        required_rung="transfer",
        priority=5,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


def _record(best, state, misconception=None, last_seen=None):
    return ConceptRecord(
        concept_id="mitosis",
        display_name="Mitosis",
        state=state,
        rungs=[RungRecord(kind=best, confidence=0.9, unaided=True)],
        best_rung=best,
        next_rung=None,
        misconception=misconception,
        last_seen=last_seen,
    )


def test_no_evidence_starts_with_a_diagnostic_not_a_beginner_lecture():
    action, evidence, surface, minutes, _ = _action_for_skill(
        _skill(), None, overdue_review=False
    )
    assert action == "diagnose"
    assert evidence == "recognition"
    assert surface == "quiz"
    assert minutes <= 5


def test_application_moves_to_transfer_instead_of_repeating_application():
    action, evidence, surface, _, _ = _action_for_skill(
        _skill(),
        _record("application", "APPLIED"),
        overdue_review=False,
    )
    assert action == "check_transfer"
    assert evidence == "transfer"
    assert surface == "quiz"


def test_misconception_repairs_before_advancing():
    action, evidence, surface, _, _ = _action_for_skill(
        _skill(),
        _record("recognition", "RECOGNIZED", misconception="Confuses mitosis and meiosis"),
        overdue_review=False,
    )
    assert action == "remediate"
    assert evidence == "application"
    assert surface == "classroom"


def test_readiness_is_evidence_progress_not_a_grade_prediction():
    states = [
        GoalSkillState(
            skill_id="a",
            concept_id="a",
            display_name="A",
            weight=3,
            required_rung="transfer",
            strongest_rung="transfer",
            evidence_state="TRANSFERRED",
            evidence_progress=1.0,
            priority_score=0,
        ),
        GoalSkillState(
            skill_id="b",
            concept_id="b",
            display_name="B",
            weight=1,
            required_rung="transfer",
            strongest_rung="recognition",
            evidence_state="RECOGNIZED",
            evidence_progress=0.4,
            priority_score=1,
        ),
    ]
    result = _readiness(states)
    assert result.readiness_index == pytest.approx(0.85)
    # A recognition-only critical gap prevents the product claiming "Ready"
    # even though the weighted ordinal index happens to be high.
    assert result.readiness_level == "getting_there"
    assert result.calibrated is False
    assert result.critical_gaps == 1


def test_deadline_urgency_increases_priority_without_changing_evidence():
    skill = _skill()
    record = _record("recognition", "RECOGNIZED")
    now = datetime.utcnow()
    near = _state_for_skill(_goal(days=1), skill, record, average_weight=1.0, now=now)
    later = _state_for_skill(_goal(days=20), skill, record, average_weight=1.0, now=now)
    assert near.evidence_progress == later.evidence_progress
    assert near.priority_score > later.priority_score


@pytest.mark.asyncio
async def test_test_prep_is_an_adapter_into_general_learning_goals_and_resyncs_edits():
    database = create_async_engine("sqlite+aiosqlite://")
    try:
        from lyo_app.coach.models import CoachSnapshot

        async with database.begin() as conn:
            await conn.run_sync(TestProfile.__table__.create)
            await conn.run_sync(LearningGoal.__table__.create)
            await conn.run_sync(GoalSkill.__table__.create)

        profile = TestProfile(
            id="profile-1",
            user_id=7,
            subject="Biology",
            test_date=date.today() + timedelta(days=5),
            test_format="mixed",
            topics=[
                {"name": "Mitosis", "weight": 3},
                {"name": "Meiosis", "weight": 1},
            ],
            materials=[],
            baseline_confidence=5,
            daily_minutes_available=25,
            study_days_per_week=5,
            stress_level=4,
            intake_complete=True,
            intake_transcript=[],
            workflow_state={"timezone": "America/New_York"},
        )

        async with AsyncSession(database, expire_on_commit=False) as db:
            db.add(profile)
            await db.flush()
            goal = await ensure_test_goal(db, profile)
            await db.commit()

            assert goal.goal_type == "test"
            assert goal.source_ref_type == "test_profile"
            assert goal.constraints["daily_minutes"] == 25

            skills = list(
                (
                    await db.execute(
                        __import__("sqlalchemy").select(GoalSkill).where(GoalSkill.goal_id == goal.id)
                    )
                ).scalars().all()
            )
            assert {s.display_name for s in skills} == {"Mitosis", "Meiosis"}

            # The existing goal identity survives a Test Prep edit; only its
            # current skill requirements change.
            original_id = goal.id
            profile.topics = [{"name": "Genetics", "weight": 2}]
            profile.subject = "Biology II"
            goal2 = await ensure_test_goal(db, profile)
            await db.commit()

            assert goal2.id == original_id
            assert goal2.title == "Biology II test"
            skills2 = list(
                (
                    await db.execute(
                        __import__("sqlalchemy").select(GoalSkill).where(GoalSkill.goal_id == goal2.id)
                    )
                ).scalars().all()
            )
            assert [s.display_name for s in skills2] == ["Genetics"]
    finally:
        await database.dispose()
