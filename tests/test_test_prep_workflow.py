"""Account continuity, real scheduling and safe retries across Test Prep surfaces."""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from lyo_app.study_plans.workflow import local_day_bounds, normalize_schedule, baseline_schedule, profile_ready
from lyo_app.study_plans.schemas import IntakeMessage, TestProfileUpdate as ProfileUpdate
from lyo_app.study_plans.models import TestProfile as Profile, StudyPlan, StudySession  # register before DB fixture


def profile(**changes):
    values = dict(subject="Biology", test_date=date(2026, 10, 10),
        topics=[{"name": "Cells", "confidence": 3}, {"name": "DNA", "confidence": 7}],
        daily_minutes_available=30, study_days_per_week=5,
        workflow_state={"timezone": "America/New_York", "known_fields": ["test_date", "daily_minutes_available"]})
    return SimpleNamespace(**(values | changes))


def test_local_day_follows_dst_not_fixed_24_hours():
    start, end = local_day_bounds("America/New_York", datetime(2026, 3, 8, 18, tzinfo=timezone.utc))
    assert start == datetime(2026, 3, 8, 5)
    assert end - start == timedelta(hours=23)
    start, end = local_day_bounds("America/New_York", datetime(2026, 11, 1, 18, tzinfo=timezone.utc))
    assert end - start == timedelta(hours=25)


def test_local_day_can_differ_from_utc_date():
    start, _ = local_day_bounds("America/Los_Angeles", datetime(2026, 10, 2, 1, tzinfo=timezone.utc))
    assert start == datetime(2026, 10, 1, 7)


def test_unconfirmed_placeholder_date_is_not_enough_to_build():
    assert profile_ready(profile())
    assert not profile_ready(profile(workflow_state={"known_fields": ["daily_minutes_available"]}))


def test_invalid_timezone_is_rejected_at_both_writes():
    with pytest.raises(ValueError):
        IntakeMessage(user_message="hello", timezone="not/a/zone")
    with pytest.raises(ValueError):
        ProfileUpdate(expected_revision=0, timezone="not/a/zone")


def test_baseline_schedule_respects_topics_budget_days_and_final_review():
    now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    rows = baseline_schedule(profile(), now)
    assert rows and all(r["topic"] in {"Cells", "DNA"} for r in rows)
    assert all(r["duration_minutes"] == 30 for r in rows)
    assert any(r["session_type"] == "mock_test" for r in rows)
    assert all(r["session_type"] == "review" for r in rows if r["scheduled_at"].date() >= date(2026, 10, 9))
    assert all(r["scheduled_at"].tzinfo is None for r in rows)


def test_empty_or_overbudget_model_schedule_never_becomes_a_plan():
    now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        normalize_schedule([], profile(), now)
    row = {"scheduled_at": "2026-09-22T18:00:00-04:00", "duration_minutes": 25,
           "topic": "Cells", "session_type": "practice"}
    with pytest.raises(ValueError):
        normalize_schedule([row, row], profile(), now)


@pytest.fixture
async def learner(db_session):
    from lyo_app.auth.models import User
    user = User(email="prep@example.test", username="prep-test", hashed_password="unused")
    db_session.add(user)
    await db_session.commit()
    return user


def llm_reply(**updates):
    return {"content": json.dumps({"message_to_user": "When is your test?", "smart_blocks": [],
        "intake_complete": False, "profile_update": updates})}


@pytest.mark.asyncio
async def test_opening_is_read_only_and_intake_resumes_without_profile_id(db_session, learner, monkeypatch):
    from lyo_app.study_plans import routes
    from lyo_app.study_plans.models import TestProfile
    ai = AsyncMock(return_value=llm_reply(subject="Biology"))
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion", ai)
    assert (await routes.prep_state(learner, db_session))["profile"] is None
    first = await routes.intake_turn(IntakeMessage(user_message="I have a biology test", request_id="first",
        timezone="America/New_York", conversation_id="chat-1"), learner, db_session)
    resumed = await routes.prep_state(learner, db_session)
    assert resumed["profile"].id == first.test_profile_id
    assert len(resumed["profile"].intake_transcript) == 2
    second = await routes.intake_turn(IntakeMessage(user_message="Friday", request_id="second"), learner, db_session)
    assert second.test_profile_id == first.test_profile_id
    replay = await routes.intake_turn(IntakeMessage(user_message="Friday", request_id="second"), learner, db_session)
    assert replay == second
    assert ai.await_count == 2
    assert (await db_session.scalar(select(func.count()).select_from(TestProfile))) == 1


@pytest.mark.asyncio
async def test_provider_failure_preserves_answer_and_retry_does_not_duplicate_it(db_session, learner, monkeypatch):
    from lyo_app.study_plans import routes
    ai = AsyncMock(side_effect=[RuntimeError("offline"), llm_reply(subject="Biology")])
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion", ai)
    body = IntakeMessage(user_message="Biology", request_id="retry-me")
    with pytest.raises(HTTPException) as exc:
        await routes.intake_turn(body, learner, db_session)
    assert exc.value.status_code == 503
    saved = await routes.prep_state(learner, db_session)
    assert len(saved["profile"].intake_transcript) == 1
    await routes.intake_turn(body, learner, db_session)
    saved = await routes.prep_state(learner, db_session)
    assert len(saved["profile"].intake_transcript) == 2


@pytest.mark.asyncio
async def test_plan_generation_is_idempotent_and_model_failure_gets_real_schedule(db_session, learner, monkeypatch):
    from lyo_app.study_plans import routes
    from lyo_app.study_plans.models import TestProfile, StudyPlan, StudySession
    p = TestProfile(user_id=learner.id, subject="Biology", test_date=date.today() + timedelta(days=14),
        topics=[{"name": "Cells", "confidence": 3}], intake_complete=True,
        workflow_state={"timezone": "America/New_York"})
    db_session.add(p); await db_session.commit()
    ai = AsyncMock(return_value={"content": "{}", "is_fallback": True})
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion", ai)
    first = await routes.generate_plan(p.id, learner, db_session)
    second = await routes.generate_plan(p.id, learner, db_session)
    assert first == second and first["total_sessions"] > 0
    assert ai.await_count == 1
    assert (await db_session.scalar(select(func.count()).select_from(StudyPlan))) == 1
    rows = (await db_session.execute(select(StudySession))).scalars().all()
    assert all(s.topic == "Cells" for s in rows)


@pytest.mark.asyncio
async def test_edits_reject_stale_versions_and_preserve_completed_work(db_session, learner, monkeypatch):
    from lyo_app.study_plans import routes
    from lyo_app.study_plans.models import TestProfile, StudyPlan, StudySession
    p = TestProfile(user_id=learner.id, subject="Biology", test_date=date.today() + timedelta(days=14),
        topics=[{"name": "Cells"}], intake_complete=True, workflow_state={"revision": 2, "timezone": "UTC"})
    db_session.add(p); await db_session.flush()
    plan = StudyPlan(user_id=learner.id, test_profile_id=p.id)
    db_session.add(plan); await db_session.flush()
    done = StudySession(study_plan_id=plan.id, user_id=learner.id, scheduled_at=datetime.utcnow(),
        duration_minutes=20, topic="Cells", session_type="learn", status="completed", performance_score=0.75)
    future = StudySession(study_plan_id=plan.id, user_id=learner.id, scheduled_at=datetime.utcnow() + timedelta(days=1),
        duration_minutes=20, topic="Cells", session_type="practice")
    db_session.add_all([done, future]); await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await routes.edit_profile(p.id, ProfileUpdate(expected_revision=1, daily_minutes_available=25), learner, db_session)
    assert exc.value.status_code == 409
    result = await routes.edit_profile(p.id, ProfileUpdate(expected_revision=2, daily_minutes_available=25), learner, db_session)
    assert result["needs_plan"]
    assert done.status == "completed" and float(done.performance_score) == 0.75
    assert future.status == "skipped" and plan.status == "archived"


@pytest.mark.asyncio
async def test_foreign_profile_cannot_be_resumed_or_edited(db_session, learner):
    from lyo_app.study_plans import routes
    for operation in [routes.intake_turn(IntakeMessage(user_message="hello", test_profile_id="foreign"), learner, db_session),
                      routes.edit_profile("foreign", ProfileUpdate(expected_revision=0, subject="Math"), learner, db_session)]:
        with pytest.raises(HTTPException) as exc:
            await operation
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_handoff_refuses_to_describe_a_plan_that_is_not_there(
    db_session, learner, monkeypatch
):
    """The guard at its own level, with a profile present and no plan.

    `process_chat_turn` returns before reaching this when intake is unfinished,
    so the branch is only reachable if the saved state disagrees with the plan
    that was just generated. It still must not invent a handoff: a client would
    render "Start now" against a plan id that resolves to nothing.
    """
    from lyo_app.study_plans import chat as chat_module

    async def profile_but_no_plan(current_user, db):
        return {"profile": SimpleNamespace(subject="Biology", test_date=date.today()),
                "plan": None, "sessions": []}

    monkeypatch.setattr(chat_module.routes, "prep_state", profile_but_no_plan)
    assert await chat_module._handoff(learner, db_session) is None

    # And with neither, which is a learner who has never started.
    async def nothing(current_user, db):
        return {"profile": None, "plan": None, "sessions": []}

    monkeypatch.setattr(chat_module.routes, "prep_state", nothing)
    assert await chat_module._handoff(learner, db_session) is None


@pytest.mark.asyncio
async def test_a_session_with_nothing_to_teach_is_not_offered_as_start_now(
    db_session, learner, monkeypatch
):
    """A session with no topic cannot open a Classroom, so offering it would
    be a button that goes nowhere. The plan is still handed over; only the
    start is withheld."""
    from lyo_app.study_plans import chat as chat_module

    async def state(current_user, db):
        return {
            "profile": SimpleNamespace(subject="Biology", test_date=date.today()),
            "plan": SimpleNamespace(id="plan-1"),
            "sessions": [SimpleNamespace(id="s1", topic="   ", session_type="learn",
                                         status="scheduled", scheduled_at=None)],
        }

    monkeypatch.setattr(chat_module.routes, "prep_state", state)

    handoff = await chat_module._handoff(learner, db_session)

    assert handoff is not None and handoff["plan_id"] == "plan-1"
    assert handoff["next_session"] is None


# ─── More than one exam ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_second_exam_starts_its_own_intake_instead_of_replaying_the_first(
    db_session, learner, monkeypatch
):
    """The reported bug.

    Once a plan existed, every later turn returned the same saved-plan sentence
    without the learner's message ever reaching the model. Saying "I also have
    a social studies test" got the biology plan read back, and there was no way
    to add an exam, correct one, or be heard at all.
    """
    from lyo_app.study_plans import routes

    complete = llm_reply(test_date=(date.today() + timedelta(days=14)).isoformat(),
        topics=[{"name": "Cells", "confidence": 3}], daily_minutes_available=25,
        study_days_per_week=4)
    parsed = json.loads(complete["content"])
    parsed["intake_complete"] = True
    complete["content"] = json.dumps(parsed)
    ai = AsyncMock(side_effect=[llm_reply(subject="Biology"), complete,
                                {"content": "{}", "is_fallback": True}])
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion", ai)

    first = await routes.intake_turn(IntakeMessage(user_message="I have a biology test",
        request_id="a"), learner, db_session)
    await routes.intake_turn(IntakeMessage(user_message="In two weeks, cells, 25 minutes",
        request_id="b"), learner, db_session)
    plan = await routes.generate_plan(first.test_profile_id, learner, db_session)
    assert plan["plan_id"]

    # Now the second exam. The classifier says yes; intake then asks about it.
    monkeypatch.setattr(routes, "describes_a_different_test",
                        AsyncMock(return_value=True))
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion",
                        AsyncMock(return_value=llm_reply(subject="Social Studies")))

    second = await routes.intake_turn(IntakeMessage(
        user_message="I also have a social studies test next Tuesday",
        request_id="c"), learner, db_session)

    # A new exam, not the old one read back.
    assert second.test_profile_id != first.test_profile_id
    assert second.intake_complete is False
    assert "Biology test plan is saved" not in second.message_to_user
    assert (await db_session.scalar(select(func.count()).select_from(Profile))) == 2


@pytest.mark.asyncio
async def test_talking_about_the_planned_exam_does_not_invent_a_second_one(
    db_session, learner, monkeypatch
):
    """The other half of the same decision. A wrong "yes" interrogates the
    learner about an exam they never mentioned, so anything short of a clear
    second exam stays with the first."""
    from lyo_app.study_plans import routes

    complete = llm_reply(test_date=(date.today() + timedelta(days=14)).isoformat(),
        topics=[{"name": "Cells", "confidence": 3}], daily_minutes_available=25,
        study_days_per_week=4)
    parsed = json.loads(complete["content"])
    parsed["intake_complete"] = True
    complete["content"] = json.dumps(parsed)
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion",
        AsyncMock(side_effect=[llm_reply(subject="Biology"), complete]))
    first = await routes.intake_turn(IntakeMessage(user_message="I have a biology test",
        request_id="a"), learner, db_session)
    await routes.intake_turn(IntakeMessage(user_message="In two weeks, cells, 25 minutes",
        request_id="b"), learner, db_session)
    await routes.generate_plan(first.test_profile_id, learner, db_session)

    monkeypatch.setattr(routes, "describes_a_different_test", AsyncMock(return_value=False))
    reply = await routes.intake_turn(IntakeMessage(user_message="thanks!", request_id="c"),
                                     learner, db_session)

    assert reply.test_profile_id == first.test_profile_id
    assert (await db_session.scalar(select(func.count()).select_from(Profile))) == 1


@pytest.mark.asyncio
async def test_an_unclear_message_never_invents_an_exam(db_session, learner, monkeypatch):
    """The classifier fails safe. A model outage must not start interrogating
    someone about an exam they never mentioned."""
    from lyo_app.study_plans import routes

    profile = SimpleNamespace(subject="Biology", test_date=date.today())
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion",
                        AsyncMock(side_effect=RuntimeError("model down")))
    assert await routes.describes_a_different_test("I also have chemistry", profile) is False

    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion",
                        AsyncMock(return_value={"content": "{}", "is_fallback": True}))
    assert await routes.describes_a_different_test("I also have chemistry", profile) is False

    # And an empty turn is not an exam.
    assert await routes.describes_a_different_test("   ", profile) is False


# ─── Two exams, one calendar ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_second_plan_is_not_scheduled_on_top_of_the_first(
    db_session, learner, monkeypatch
):
    """The wiring, not the helper.

    Testing `first_free_slot` alone proves the arithmetic and nothing about
    whether plan generation uses it — removing the call from `generate_plan`
    left every scheduling test passing.
    """
    from lyo_app.study_plans import routes
    from lyo_app.study_plans.models import StudySession as Session

    exam_day = date.today() + timedelta(days=10)
    when = datetime.combine(exam_day - timedelta(days=2), datetime.min.time()).replace(hour=18)

    # Build a completed profile the planner can be run against.
    profile = Profile(user_id=learner.id, subject="Social Studies", test_date=exam_day,
                      topics=[{"name": "Civics", "confidence": 3}],
                      daily_minutes_available=120, study_days_per_week=5,
                      intake_complete=True, intake_transcript=[],
                      workflow_state={"timezone": "UTC", "known_fields": [], "revision": 0})
    db_session.add(profile)
    await db_session.flush()

    # A block the learner already owes time to, from their biology plan.
    other_plan = StudyPlan(user_id=learner.id, test_profile_id="other", status="active",
                           total_sessions=1)
    db_session.add(other_plan)
    await db_session.flush()
    db_session.add(Session(study_plan_id=other_plan.id, user_id=learner.id,
                           scheduled_at=when, duration_minutes=60,
                           topic="Cells", session_type="learn", status="scheduled"))
    await db_session.flush()

    # The planner proposes exactly that slot for the new exam.
    monkeypatch.setattr(routes, "normalize_schedule", lambda items, prof, now=None: [
        {"scheduled_at": when, "duration_minutes": 60,
         "topic": "Civics", "session_type": "learn"}])
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion", AsyncMock(
        return_value={"content": json.dumps({"sessions": [], "weekly_milestones": [],
                                             "reasoning": ""}), "is_fallback": False}))

    await routes.generate_plan(profile.id, learner, db_session)

    placed = (await db_session.execute(select(Session).where(
        Session.user_id == learner.id, Session.topic == "Civics"))).scalars().all()
    assert placed, "the new exam got no study block at all"
    for block in placed:
        finish = block.scheduled_at + timedelta(minutes=block.duration_minutes)
        assert not (block.scheduled_at < when + timedelta(minutes=60) and when < finish), (
            "the learner is booked for two subjects at once")



def test_two_exams_never_book_the_learner_at_the_same_moment():
    """More than one exam on a date is ordinary. Being in two places at 6pm is
    not, and until now each plan was built with no knowledge of the others."""
    from lyo_app.study_plans.routes import SESSION_GAP_MINUTES, first_free_slot

    busy = [(datetime(2026, 9, 29, 18, 0), datetime(2026, 9, 29, 19, 0))]

    # Clear of it: untouched.
    assert first_free_slot(datetime(2026, 9, 29, 16, 0), 45, busy) == datetime(2026, 9, 29, 16, 0)
    # Straight on top of it, and merely overlapping its tail: both move past.
    for clash in (datetime(2026, 9, 29, 18, 0), datetime(2026, 9, 29, 18, 45)):
        moved = first_free_slot(clash, 45, busy)
        assert moved >= busy[0][1] + timedelta(minutes=SESSION_GAP_MINUTES)
    # A learner with nothing booked keeps the time the planner chose.
    assert first_free_slot(datetime(2026, 9, 29, 18, 0), 45, []) == datetime(2026, 9, 29, 18, 0)


def test_a_block_is_never_moved_past_the_exam_it_revises_for():
    """`normalize_schedule` has already checked every block against the exam
    date; this runs after it. Moving one without a bound would quietly undo
    that check and schedule revision for after the paper is sat."""
    from lyo_app.study_plans.routes import first_free_slot

    exam_end = datetime(2026, 9, 29, 23, 59, 59)
    # A short shift — well inside the search limit, so it is the exam bound
    # and nothing else that stops this. The next free moment is 23:45, and a
    # 45-minute block there runs past midnight, into the exam day.
    busy = [(datetime(2026, 9, 29, 22, 0), datetime(2026, 9, 29, 23, 30))]
    start = datetime(2026, 9, 29, 22, 0)

    # Left where it was: a visible clash the learner can move beats revision
    # scheduled for after the paper is sat.
    assert first_free_slot(start, 45, busy, not_after=exam_end) == start
    # Without the bound the same call places a block that runs past the exam,
    # which is what makes this worth pinning.
    unbounded = first_free_slot(start, 45, busy)
    assert unbounded + timedelta(minutes=45) > exam_end


def test_a_block_is_moved_rather_than_dropped():
    """A block at an awkward hour is one the learner can move. A topic that was
    silently never scheduled is one they find out about after the exam."""
    from lyo_app.study_plans.routes import first_free_slot

    day = datetime(2026, 9, 29, 0, 0)
    wall = [(day + timedelta(hours=h), day + timedelta(hours=h + 1)) for h in range(24)]
    placed = first_free_slot(datetime(2026, 9, 29, 9, 0), 45, wall)
    assert placed is not None


@pytest.mark.asyncio
async def test_chat_offers_no_start_now_until_a_plan_actually_exists(db_session, learner, monkeypatch):
    """A handoff is an offer to start something. Mid-intake there is no plan
    and no session, so offering one would send the learner at a schedule that
    does not exist — and they would have answered the questions for nothing."""
    from lyo_app.study_plans import routes
    from lyo_app.study_plans.chat import process_chat_turn

    # The model still wants more from the learner: intake_complete stays false.
    ai = AsyncMock(side_effect=[llm_reply(subject="Biology")])
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion", ai)
    request = SimpleNamespace(text="I have a biology test", client_message_id="mid-1",
                              conversation_id="mid", timezone="UTC", media=[])

    result = await process_chat_turn(request, learner, db_session)

    assert result.handoff is None
    # And nothing in the reply promises a schedule that has not been built.
    assert "[Test Prep](" not in result.text


@pytest.mark.asyncio
async def test_chat_and_dedicated_intake_share_profile_transcript_and_plan(db_session, learner, monkeypatch):
    from lyo_app.study_plans import routes
    from lyo_app.study_plans.chat import process_chat_turn

    complete = llm_reply(test_date=(date.today() + timedelta(days=14)).isoformat(),
        topics=[{"name": "Cells", "confidence": 3}], daily_minutes_available=25, study_days_per_week=4)
    parsed = json.loads(complete["content"])
    parsed["intake_complete"] = True
    complete["content"] = json.dumps(parsed)
    ai = AsyncMock(side_effect=[llm_reply(subject="Biology"), complete,
                              {"content": "{}", "is_fallback": True}])
    monkeypatch.setattr(routes.ai_resilience_manager, "chat_completion", ai)
    request = SimpleNamespace(text="I have a biology test", client_message_id="chat-start",
                              conversation_id="chat-1", timezone="America/New_York", media=[])
    await process_chat_turn(request, learner, db_session)
    opened = await routes.prep_state(learner, db_session)
    profile_id = opened["profile"].id
    assert len(opened["profile"].intake_transcript) == 2
    # Switching to the dedicated page continues the same intake without an ID.
    reply = await routes.intake_turn(IntakeMessage(user_message="In two weeks, cells, 25 minutes four days a week",
        request_id="dedicated-finish"), learner, db_session)
    assert reply.test_profile_id == profile_id and reply.intake_complete
    plan = await routes.generate_plan(profile_id, learner, db_session)
    # Returning to Chat reopens the saved plan without another intake/model call.
    request.client_message_id = "chat-resume"
    result = await process_chat_turn(request, learner, db_session)
    message = result.text
    resumed = await routes.prep_state(learner, db_session)
    assert resumed["profile"].id == profile_id
    assert resumed["plan"].id == plan["plan_id"]
    assert resumed["timezone"] == "America/New_York"
    assert len(resumed["profile"].intake_transcript) == 4
    # Four, not three: a turn arriving after the plan exists is now classified
    # instead of being answered without being read. That extra call is the
    # price of the learner being able to say anything at all once they have a
    # plan — including that they have a second exam.
    assert "Test Prep" in message and ai.await_count == 4
    # One sentence, one link, and it is a route rather than an absolute URL:
    # an app link written as https://lyoai.app/... is a full page load that
    # drops the learner out of the conversation they are in.
    assert "[Test Prep](/test-prep)" in message
    assert "https://lyoai.app" not in message
    assert message.count("Test Prep") == 1, "the handoff said the same thing twice"
    # The structured handoff is what lets a client offer "Start now" without
    # asking anything the learner already answered.
    assert result.handoff and result.handoff["plan_id"] == plan["plan_id"]
    assert result.handoff["subject"] == "Biology"
    assert (await db_session.scalar(select(func.count()).select_from(Profile))) == 1
    assert (await db_session.scalar(select(func.count()).select_from(StudyPlan))) == 1


def test_schedule_rejects_unrequested_topics_and_overlaps():
    now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    row = {"scheduled_at": "2026-09-22T18:00:00-04:00", "duration_minutes": 10,
           "topic": "Cells", "session_type": "practice"}
    with pytest.raises(ValueError, match="overlap"):
        normalize_schedule([row, row], profile(), now)
    with pytest.raises(ValueError, match="saved test profile"):
        normalize_schedule([row | {"topic": "Unrequested subject"}], profile(), now)


@pytest.mark.asyncio
async def test_completion_retry_keeps_original_evidence(db_session, learner, monkeypatch):
    from lyo_app.study_plans import routes
    from lyo_app.study_plans.models import PlanEvent
    p = Profile(user_id=learner.id, subject="Biology", test_date=date.today() + timedelta(days=14))
    db_session.add(p); await db_session.flush()
    plan = StudyPlan(user_id=learner.id, test_profile_id=p.id)
    db_session.add(plan); await db_session.flush()
    session = StudySession(user_id=learner.id, study_plan_id=plan.id, topic="Cells",
        scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None), duration_minutes=25, session_type="practice")
    db_session.add(session); await db_session.commit()
    measure = AsyncMock(return_value=SimpleNamespace(score=0.75, graded=4, seen=5, measured=True))
    monkeypatch.setattr(routes, "derive_session_outcome", measure)
    first = await routes.complete_session(session.id, current_user=learner, db=db_session, user_notes="")
    repeated = await routes.complete_session(session.id, current_user=learner, db=db_session, user_notes="")
    assert first == repeated
    assert measure.await_count == 1
    assert (await db_session.scalar(select(func.count()).select_from(PlanEvent))) == 1


def test_night_before_reminder_is_previous_local_evening_across_dst():
    from lyo_app.study_plans.workflow import evening_before
    # Sunday 18:00 EDT; previous evening is Saturday 20:00 EST.
    assert evening_before(datetime(2026, 3, 8, 22), "America/New_York") == datetime(2026, 3, 8, 1)
