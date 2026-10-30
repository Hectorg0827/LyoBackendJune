"""The opening and its result must not wait behind the next authored lesson."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import GuidedState, TeachingUnavailable
from lyo_app.ai_classroom.sdui_models import ActionIntent, TeacherMessage
from lyo_app.ai_classroom.websocket_manager import WebSocketManager
from tests.adaptive_fixtures import ScriptedTeacher, action, context


@pytest.mark.asyncio
@pytest.mark.parametrize("language, greeting", [("en-US", "Hello, Ana!"), ("es-ES", "¡Hola, Ana!")])
async def test_opening_greets_the_learner_and_names_the_subject(language, greeting):
    ctx = context(learner_name="Ana", language_code=language)
    runner, progress = AdaptiveSession(ScriptedTeacher()), {}
    scene = await runner.run(ctx, progress, action(welcome=True))
    speech = next(c.text for c in scene.components if isinstance(c, TeacherMessage))
    assert speech.startswith(greeting)
    assert "Fractions" in speech
    assert "question" in speech or "pregunta" in speech
    # A reconnect replays the same opening, without creating another probe.
    assert (await runner.run(ctx, progress, action(welcome=True))).scene_id == scene.scene_id


@pytest.mark.asyncio
@pytest.mark.parametrize("option_id, verdict", [("a", "correct"), ("b", "incorrect"), ("c", "incorrect"), ("d", "declined")])
async def test_result_arrives_before_a_blocked_next_generation(option_id, verdict):
    teacher, sender = ScriptedTeacher(), AsyncMock()
    runner, progress, ctx = AdaptiveSession(teacher, feedback_sender=sender), {}, context()
    await runner.run(ctx, progress, action(welcome=True))
    pending = GuidedState.model_validate(progress["guided_state"]).pending
    option = next(o for o in pending.task.options if o.id == option_id)
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_turn(*args):
        started.set()
        await release.wait()
        raise TeachingUnavailable("Simulated provider outage")

    teacher.turn.side_effect = slow_turn
    trigger = action(ActionIntent.SUBMIT_ANSWER, pending.id, answer_data={"selected_option_id": option_id})
    task = asyncio.create_task(runner.run(ctx, progress, trigger))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not task.done()
        sender.assert_awaited_once()
        component, received_verdict, feedback, language = sender.await_args.args
        assert (component, received_verdict, language) == (pending.id, verdict, "en-US")
        if verdict != "declined":
            assert option.feedback in feedback
            assert "correct" in feedback
        else:
            assert "incorrect" not in feedback
        release.set()
        scene = await task
        assert feedback in scene.model_dump_json()
        assert pending.id in progress["guided_state"]["handled"]
        await runner.run(ctx, progress, trigger)
        sender.assert_awaited_once()  # A replay never grades or announces twice.
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_early_feedback_failure_does_not_block_the_next_lesson():
    sender = AsyncMock(side_effect=ConnectionError("disconnected"))
    runner, progress, ctx = AdaptiveSession(ScriptedTeacher(), feedback_sender=sender), {}, context()
    await runner.run(ctx, progress, action(welcome=True))
    pending = GuidedState.model_validate(progress["guided_state"]).pending
    scene = await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, pending.id,
                                                  answer_data={"selected_option_id": "a"}))
    assert pending.task.options[0].feedback in scene.model_dump_json()
    assert GuidedState.model_validate(progress["guided_state"]).phase == "guided"


@pytest.mark.asyncio
async def test_feedback_is_only_sent_to_the_owner_in_the_requested_session():
    manager = WebSocketManager.__new__(WebSocketManager)
    owner = SimpleNamespace(user_id="42", connection_id="owner")
    other = SimpleNamespace(user_id="99", connection_id="other")
    manager.rooms = {"lesson": SimpleNamespace(get_active_connections=lambda: [owner, other])}
    manager.send_to_connection = AsyncMock()
    await manager.send_answer_feedback("lesson", "42", "question", "correct", "That's correct because…", "en-US")
    manager.send_to_connection.assert_awaited_once()
    connection_id, payload = manager.send_to_connection.await_args.args
    assert connection_id == "owner" and payload.event_type == "answer_feedback"
    assert payload.data["component_id"] == "question"
