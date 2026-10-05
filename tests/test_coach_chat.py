"""Fast Coach chat contract tests."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from lyo_app.ai.schemas.lyo2 import Intent
from lyo_app.coach.chat import (
    format_coach_answer,
    is_coach_request,
    process_coach_turn,
    requested_minutes,
)
from lyo_app.coach.service import build_today_view
from lyo_app.coach.schemas import (
    LearningGoalRead,
    MissionItem,
    ReadinessRead,
    TodayCoachView,
)
from lyo_app.teaching_runtime.interaction_contract import (
    InteractionMode,
    interaction_contract_for_request,
)
from lyo_app.teaching_runtime.models import (
    LearnerSnapshot,
    SessionSnapshot,
    TeachingAction,
    TeachingContext,
    TeachingSurface,
)
from lyo_app.teaching_runtime.policy import TeachingPolicy


def _today() -> TodayCoachView:
    now = datetime.utcnow()
    goal = LearningGoalRead(
        id="goal-1",
        goal_type="test",
        title="Biology test",
        subject="Biology",
        status="active",
        deadline=None,
        desired_outcome={},
        constraints={"daily_minutes": 25},
        source_surface="test_prep",
        source_ref_type="test_profile",
        source_ref_id="profile-1",
        created_at=now,
        updated_at=now,
        skills=[],
    )
    return TodayCoachView(
        primary_goal_id=goal.id,
        active_goals=[goal],
        readiness={
            goal.id: ReadinessRead(
                readiness_index=0.5,
                readiness_level="getting_there",
                calibrated=False,
                assessed_skills=2,
                total_skills=4,
                critical_gaps=2,
            )
        },
        mission=[
            MissionItem(
                goal_id=goal.id,
                goal_title=goal.title,
                skill_id="skill-1",
                concept_id="mitosis",
                title="Mitosis",
                action="check_application",
                target_evidence_type="application",
                recommended_surface="quiz",
                estimated_minutes=6,
                priority_score=1.2,
                reason="Application evidence is due.",
            )
        ],
        total_minutes=6,
        coach_note="Biology test: the best next use of time is Mitosis.",
        generated_at=now,
    )


@pytest.mark.parametrize(
    "text",
    [
        "What should I study?",
        "What should I work on today?",
        "What is my mission today?",
        "How ready am I?",
        "I have 20 minutes",
    ],
)
def test_explicit_study_now_language_uses_coach(text):
    assert is_coach_request(text)
    contract = interaction_contract_for_request(text=text, routed_intent=Intent.CHAT)
    assert contract.mode is InteractionMode.WORKFLOW
    assert contract.workflow_intent is Intent.COACH
    assert contract.fast_lane is True


def test_new_test_intake_still_outranks_coach_language():
    contract = interaction_contract_for_request(
        text="I have a test Friday. What should I study?"
    )
    assert contract.workflow_intent is Intent.TEST_PREP


def test_time_constraint_does_not_hijack_an_explicit_teaching_request():
    text = "I have 20 minutes, teach me photosynthesis"
    assert is_coach_request(text) is False
    contract = interaction_contract_for_request(text=text, routed_intent=Intent.COACH)
    assert contract.mode is InteractionMode.TEACH
    assert contract.workflow_intent is None


def test_specific_readiness_question_is_not_forced_into_coach():
    assert is_coach_request("Am I ready to submit this essay?") is False


def test_midterm_intake_outranks_a_coach_question():
    contract = interaction_contract_for_request(
        text="I have a midterm next week; what should I study?"
    )
    assert contract.workflow_intent is Intent.TEST_PREP


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("I have 5 minutes", 5),
        ("I have 20 min", 20),
        ("I have half an hour", 30),
        ("I have an hour", 60),
        ("I have 999 minutes", 180),
    ],
)
def test_time_budget_is_deterministic_and_bounded(text, minutes):
    assert requested_minutes(text) == minutes


def test_coach_answer_uses_evidence_language_not_fake_grade():
    answer = format_coach_answer(_today(), budget_minutes=20)
    assert "Readiness: Getting there" in answer
    assert "2/4 required skills assessed" in answer
    assert "Today's mission (6 min)" in answer
    assert "predicted grade" not in answer.lower()


@pytest.mark.asyncio
async def test_coach_turn_passes_time_budget_to_receding_horizon(monkeypatch):
    captured = {}

    async def fake_today(db, user_id, *, minute_cap_override=None):
        captured["user_id"] = user_id
        captured["budget"] = minute_cap_override
        return _today()

    monkeypatch.setattr("lyo_app.coach.chat.build_today_view", fake_today)
    view, answer, budget = await process_coach_turn(
        object(),
        7,
        "I have 15 minutes. What should I study?",
    )

    assert view.primary_goal_id == "goal-1"
    assert captured == {"user_id": 7, "budget": 15}
    assert budget == 15
    assert "15-minute limit" in answer


@pytest.mark.asyncio
async def test_today_passes_larger_time_budget_into_each_goal_projection(monkeypatch):
    captured = []
    goal = SimpleNamespace(
        id="goal-1",
        deadline=None,
        constraints={"daily_minutes": 15},
    )
    goal_read = _today().active_goals[0]
    readiness = _today().readiness["goal-1"]

    async def fake_active_goals(db, user_id):
        return [goal]

    async def fake_goal_view(
        db,
        user_id,
        requested_goal,
        *,
        use_cache=True,
        minute_cap_override=None,
    ):
        captured.append((use_cache, minute_cap_override))
        mission = [
            MissionItem(
                goal_id="goal-1",
                goal_title="Biology test",
                skill_id=f"skill-{index}",
                concept_id=f"concept-{index}",
                title=f"Topic {index}",
                action="guide",
                target_evidence_type="application",
                recommended_surface="classroom",
                estimated_minutes=10,
                priority_score=3 - index,
                reason="Needs guided application.",
            )
            for index in range(3)
        ]
        return SimpleNamespace(goal=goal_read, readiness=readiness, mission=mission)

    monkeypatch.setattr("lyo_app.coach.service.active_goals", fake_active_goals)
    monkeypatch.setattr("lyo_app.coach.service.build_goal_view", fake_goal_view)

    result = await build_today_view(object(), 7, minute_cap_override=30)

    assert captured == [(False, 30)]
    assert result.total_minutes == 30
    assert len(result.mission) == 3


def test_teaching_policy_does_not_replace_coach_with_a_quiz():
    context = TeachingContext(
        intent="COACH",
        user_text="what should I study?",
        learner=LearnerSnapshot(
            concept_id=None,
            evidence_state="NOT_SEEN",
            attempts=0,
        ),
        session=SessionSnapshot(surface=TeachingSurface.CHAT),
        metadata={
            "interaction_mode": "workflow",
            "response_depth": "standard",
            "has_media": False,
            "has_current_media": False,
        },
    )
    decision = TeachingPolicy.decide(context)
    assert decision.action is TeachingAction.ANSWER
    assert decision.reason_code == "learner_requested_workflow"
