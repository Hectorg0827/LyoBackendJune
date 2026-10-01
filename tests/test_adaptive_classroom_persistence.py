"""Persistence and authenticated routing, including a real SQLite round trip."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from lyo_app.ai_classroom.adaptive_persistence import learner_session
from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import GuidedState, LearningTask
from lyo_app.ai_classroom.scene_lifecycle_engine import ContextAssembler, SceneLifecycleEngine
from lyo_app.ai_classroom.sdui_models import ActionIntent, Scene, SceneType, TeacherMessage, UserActionPayload
from lyo_app.ai_classroom.websocket_manager import WebSocketManager
from lyo_app.ai_classroom.websocket_routes import _register_lifecycle_handlers
from lyo_app.classroom.models import ClassroomInteraction, ClassroomSession
from lyo_app.events.concept_record import learner_record
from lyo_app.events.models import EventType, LearningEvent
from tests.adaptive_fixtures import ScriptedTeacher, action, context, evaluation, decline_probe, past_the_probe
from tests.export_guided_fixtures import FixtureTeacher


@pytest.mark.asyncio
async def test_this_build_reads_a_session_saved_by_a_later_one():
    """Tolerance for unknown fields, stated in the direction it actually works.

    This does not make an *older* build read a session saved here. That build
    still has `extra="forbid"` and will refuse the fields added since; nothing
    committed now can change a binary already deployed. What it does is make
    every future field safe: once a build carrying this tolerance is the one
    being rolled back to, a session written above it is readable rather than
    refused — which is the whole of the guarantee, and the previous version
    of this test claimed more than that.

    Until then, the case that matters is a session this build cannot read at
    all, which must not cost the learner their turn. That is
    `test_an_unreadable_saved_session_costs_the_learner_nothing_but_the_session`
    below.

    The generation contracts keep refusing unknown fields, because there the
    strictness is what makes a model that echoes its input or invents a field
    get rejected and asked again.
    """
    progress, ctx = {}, context(target_duration_minutes=8)
    runner = AdaptiveSession(ScriptedTeacher())
    await runner.run(ctx, progress, action(welcome=True))
    saved = json.loads(json.dumps(progress["guided_state"]))
    saved["confidence_weighting"] = {"from": "a later release"}
    saved["review_cadence_days"] = 3

    restored = GuidedState.model_validate(saved)
    assert restored.owner == "42" and restored.phase == "diagnose"
    assert restored.pending is not None and restored.pending.phase == "diagnose"
    assert not hasattr(restored, "confidence_weighting")

    # The learner carries on from the restored session rather than losing it.
    progress["guided_state"] = saved
    scene = await AdaptiveSession(ScriptedTeacher()).run(ctx, progress, action(welcome=True))
    assert any(isinstance(c, TeacherMessage) for c in scene.components)

    with pytest.raises(ValidationError):
        LearningTask(
            kind="apply", response_format="short_answer",
            scenario="Two identical pies are cut into 3 and 6 equal slices.",
            question="Which slice is larger, and why?", response_hint="Name it and say why.",
            criteria=["Names the third"], example_answer="A third.",
            invented_by_the_model="not a field",
        )


@pytest.mark.asyncio
async def test_an_unreadable_saved_session_costs_the_learner_nothing_but_the_session():
    """The case unknown-field tolerance cannot reach.

    A session can be unreadable for reasons no `extra=` setting helps with: a
    field whose type has moved, a value no longer in an enum, a rollback into
    a build that predates a field, a hand-edited row. Hydration used to raise
    straight through the learner's turn, so they opened their lesson and got
    an error where the teaching was.

    It is set aside instead. The blob is kept in `guided_history` so nothing
    is destroyed and it can be looked at, and the classroom starts them again
    rather than handing them a failure.
    """
    engine = SceneLifecycleEngine(AsyncMock())
    progress = {"guided_state": {"owner": "42", "phase": "a phase that no longer exists"}}

    state = engine._read_guided_state(progress, progress["guided_state"])

    assert state is None, "an unreadable session is not silently half-read"
    assert "guided_state" not in progress, "it is cleared, or the next turn fails the same way"
    assert progress["guided_history"] == [{"owner": "42", "phase": "a phase that no longer exists"}]


@pytest.mark.asyncio
async def test_a_readable_session_is_left_exactly_where_it_was():
    """The guard must not become a way to lose a session that was fine."""
    progress, ctx = {}, context(target_duration_minutes=8)
    await AdaptiveSession(ScriptedTeacher()).run(ctx, progress, action(welcome=True))
    saved = json.loads(json.dumps(progress["guided_state"]))

    engine = SceneLifecycleEngine(AsyncMock())
    state = engine._read_guided_state(progress, saved)

    assert state is not None and state.owner == "42"
    assert progress["guided_state"] == saved
    assert "guided_history" not in progress


@pytest.mark.asyncio
async def test_database_restores_an_explored_model_without_an_interaction_or_new_teacher_turn():
    database = create_async_engine("sqlite+aiosqlite://")
    try:
        async with database.begin() as connection:
            await connection.run_sync(ClassroomSession.__table__.create)
            await connection.run_sync(ClassroomInteraction.__table__.create)
        progress, ctx = {}, context(target_duration_minutes=8)
        runner = AdaptiveSession(FixtureTeacher())
        await runner.run(ctx, progress, action(welcome=True))
        # Only the probe is passed: exploring a visual has to happen while the
        # modelled example is still on screen.
        await decline_probe(runner, progress, ctx)
        activity_id = "visual:" + progress["guided_state"]["step_id"]
        change = action(ActionIntent.UPDATE_ACTIVITY, activity_id, answer_data={"value": 3})
        expected = await runner.run(ctx, progress, change)
        async with AsyncSession(database) as db:
            instance = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
            instance.db = db
            assert await instance._persist_session_progress(change, ctx, progress, record_interaction=False)
        async with AsyncSession(database) as db:
            restored = await ContextAssembler(db)._load_persisted_session_progress(action(welcome=True))
            assert not (await db.execute(select(ClassroomInteraction))).scalars().all()
        teacher = ScriptedTeacher()
        actual = await AdaptiveSession(teacher).run(ctx, restored, action(welcome=True))
        assert actual == expected
        assert restored["guided_state"]["presentation"]["visual"]["value"] == 3
        assert restored["guided_state"]["beat_index"] == -1
        assert restored["guided_state"]["outbox"] == []
        teacher.turn.assert_not_awaited()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_database_restores_the_exact_partial_question_and_rejects_another_user():
    database = create_async_engine("sqlite+aiosqlite://")
    try:
        async with database.begin() as connection:
            await connection.run_sync(ClassroomSession.__table__.create)
            await connection.run_sync(ClassroomInteraction.__table__.create)
        teacher, progress, ctx = ScriptedTeacher(), {}, context()
        runner = AdaptiveSession(teacher)
        await runner.run(ctx, progress, action(welcome=True))
        await past_the_probe(runner, progress, ctx)
        pending = progress["guided_state"]["pending"]
        await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, pending["id"],
                                              answer_data={"selected_option_id": "a"}))
        teacher.evaluate.return_value = evaluation("partial", follow_up="Why is that piece larger?")
        pending = progress["guided_state"]["pending"]
        turn = action(ActionIntent.SUBMIT_TRANSFER, pending["id"], answer_data={"response": "One half", "is_correct": True})
        expected = await runner.run(ctx, progress, turn)
        async with AsyncSession(database) as db:
            instance = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
            instance.db = db
            assert await instance._persist_session_progress(turn, ctx, progress)
        async with AsyncSession(database) as db:
            restored = await ContextAssembler(db)._load_persisted_session_progress(action(welcome=True))
            another_user = action().model_copy(update={"user_id": "43"})
            assert await ContextAssembler(db)._load_persisted_session_progress(another_user) == {}
            interactions = (await db.execute(select(ClassroomInteraction))).scalars().all()
            assert len(interactions) == 1 and interactions[0].is_correct is None
        offline = ScriptedTeacher()
        actual = await AdaptiveSession(offline).run(ctx, restored, action(welcome=True))
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json")
        assert restored["guided_state"]["pending"]["answers"] == ["One half"]
        assert len(restored["guided_state"]["outbox"]) == 1
        offline.plan.assert_not_awaited()
        offline.turn.assert_not_awaited()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_classroom_intervention_is_durable_but_never_counts_as_mastery_evidence():
    database = create_async_engine("sqlite+aiosqlite://")
    try:
        async with database.begin() as connection:
            await connection.run_sync(
                ClassroomSession.__table__.create
            )
            await connection.run_sync(
                ClassroomInteraction.__table__.create
            )
            await connection.run_sync(
                LearningEvent.__table__.create
            )

        progress = {
            "_pending_teaching_intervention": {
                "scene_id": "scene-guide-1",
                "action": "guide",
                "target_evidence_type": "application",
                "policy_version": "learning-os-v1",
                "concept_id": "compare-fractions",
            }
        }
        ctx = context()
        turn = action(ActionIntent.CONTINUE)

        async with AsyncSession(database) as db:
            instance = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
            instance.db = db
            assert await instance._persist_session_progress(turn, ctx, progress)

        async with AsyncSession(database) as db:
            events = (
                await db.execute(
                    select(LearningEvent).where(
                        LearningEvent.user_id == 42,
                        LearningEvent.event_type == EventType.AI_SESSION,
                    )
                )
            ).scalars().all()
            assert len(events) == 1
            event = events[0]
            assert event.source_surface == "classroom"
            assert event.concept_id == "compare-fractions"
            assert event.evidence_type is None
            assert event.evidence_confidence is None
            assert event.measurable_outcome is None
            assert event.metadata_json["event_kind"] == "teaching_policy_decision"
            assert event.metadata_json["action"] == "guide"
            assert event.metadata_json["target_evidence_type"] == "application"

            record = await learner_record(db, 42)
            assert record.unavailable is False
            assert record.concepts == []

        assert "_pending_teaching_intervention" not in progress
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_postgres_lock_uses_same_key_and_releases_on_failure(monkeypatch):
    bind = MagicMock(spec=AsyncEngine)
    bind.dialect = SimpleNamespace(name="postgresql")
    connection = AsyncMock()
    bind.connect.return_value.__aenter__.return_value = connection
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=SimpleNamespace(name="locked-session"))
    session.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("lyo_app.ai_classroom.adaptive_persistence.AsyncSession", MagicMock(return_value=session))
    with pytest.raises(RuntimeError, match="teaching failure"):
        async with learner_session(SimpleNamespace(bind=bind), '["42","fractions"]') as locked:
            assert locked.name == "locked-session"
            raise RuntimeError("teaching failure")
    calls = connection.execute.await_args_list
    assert "pg_advisory_lock" in str(calls[1].args[0])
    assert "pg_advisory_unlock" in str(calls[-1].args[0])
    assert calls[1].args[1] == calls[-1].args[1]
    connection.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("intent,method,data", [
    (ActionIntent.SUBMIT_ANSWER, "handle_quiz_submission", {"selected_option_id": "a"}),
    (ActionIntent.SUBMIT_TRANSFER, "handle_transfer_submission", {"response": "One half"}),
    (ActionIntent.REQUEST_HINT, "handle_user_action", {}),
])
async def test_websocket_uses_authenticated_identity_not_payload(monkeypatch, intent, method, data):
    manager = MagicMock()
    manager.event_handlers = {}
    instance = MagicMock()
    setattr(instance, method, AsyncMock(return_value=SimpleNamespace(scene_id="next")))
    monkeypatch.setattr("lyo_app.ai_classroom.websocket_routes.SceneLifecycleEngine", MagicMock(return_value=instance))
    async def database_session():
        yield MagicMock()
    monkeypatch.setattr("lyo_app.ai_classroom.websocket_routes.get_async_session", database_session)
    await _register_lifecycle_handlers(manager, instance)
    handler = manager.register_event_handler.call_args.args[1]
    await handler(UserActionPayload(user_id="99", session_id="other-learner", component_id="question",
                                    action_intent=intent, answer_data=data),
                  SimpleNamespace(user_id="42", session_id="fractions"))
    called = getattr(instance, method)
    called.assert_awaited_once()
    assert called.await_args.kwargs["user_id"] == "42"
    assert called.await_args.kwargs["session_id"] == "fractions"


@pytest.mark.asyncio
async def test_scene_only_reaches_the_owners_devices_in_a_shared_topic_room():
    instance = WebSocketManager.__new__(WebSocketManager)
    devices = [SimpleNamespace(user_id="42", name="web"), SimpleNamespace(user_id="43", name="other"),
               SimpleNamespace(user_id="42", name="phone")]
    room = MagicMock()
    room.get_active_connections.return_value = devices
    instance.rooms = {"fractions": room}
    instance.scene_streamer = SimpleNamespace(stream_scene=AsyncMock())
    instance.stats = {"scenes_streamed": 0}
    scene = Scene(scene_type=SceneType.INSTRUCTION, components=[TeacherMessage(text="Compare these equal parts.")])
    await instance.stream_scene_to_session("fractions", scene, user_id="42")
    recipients = [call.args[1].name for call in instance.scene_streamer.stream_scene.await_args_list]
    assert recipients == ["web", "phone"]
