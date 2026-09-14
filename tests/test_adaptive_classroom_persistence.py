"""Persistence and authenticated routing, including a real SQLite round trip."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from lyo_app.ai_classroom.adaptive_persistence import learner_session
from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.scene_lifecycle_engine import ContextAssembler, SceneLifecycleEngine
from lyo_app.ai_classroom.sdui_models import ActionIntent, Scene, SceneType, TeacherMessage, UserActionPayload
from lyo_app.ai_classroom.websocket_manager import WebSocketManager
from lyo_app.ai_classroom.websocket_routes import _register_lifecycle_handlers
from lyo_app.classroom.models import ClassroomInteraction, ClassroomSession
from tests.adaptive_fixtures import ScriptedTeacher, action, context, evaluation, advance_to_task
from tests.export_guided_fixtures import FixtureTeacher


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
        await advance_to_task(runner, progress, ctx)
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
