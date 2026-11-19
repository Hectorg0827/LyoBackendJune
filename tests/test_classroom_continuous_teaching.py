"""Continuous Teaching bridge safety contract; no provider network calls in CI."""
import asyncio
from types import SimpleNamespace

from lyo_app.ai_classroom.continuous_teaching import (
    MAX_REPLIES, ContinuousTeachingBridge, SerializedTransitionRunner, bridge_enabled, fallback_ack,
    initial_prompt, short_topic, message_is_session_scoped,
)


class Sink:
    def __init__(self):
        self.messages = []

    async def send_to_connection(self, connection_id, payload):
        self.messages.append((connection_id, payload))


def teacher(fake_ai=None):
    sink = Sink()
    connection = SimpleNamespace(
        connection_id="c1", session_id="session-A", user_id="student-A"
    )
    async def ai_reply(topic, language, answer):
        return "That is worth exploring. What makes you curious?"
    return sink, ContinuousTeachingBridge(
        sink, connection, "fractions", "en-US", ai_reply=fake_ai or ai_reply
    )


def test_flag_requires_explicit_staging_opt_in_and_is_off_in_production():
    assert not bridge_enabled("1", environment="production", flag="1")
    assert not bridge_enabled("1", environment="staging", flag="0")
    assert not bridge_enabled("0", environment="staging", flag="1")
    assert bridge_enabled("1", environment="staging", flag="1")
    assert bridge_enabled("1", environment="testing", flag="1")


def test_language_and_topic_are_bounded():
    assert len(short_topic("x" * 10000)) == 100
    assert "¿" in initial_prompt("fracciones", "es-MX", "startup")
    assert "next step" in initial_prompt("fractions", "en-US", "transition")
    assert "Gracias" in fallback_ack("es-ES", keep_talking=True)


def test_start_is_immediate_ungraded_non_scene_and_scoped_to_connection():
    async def run():
        sink, bridge = teacher()
        await bridge.begin("startup")
        assert len(sink.messages) == 1
        connection_id, msg = sink.messages[-1]
        assert connection_id == "c1"
        assert msg.event_type == "bridge_message"
        assert msg.session_id == "session-A"
        assert msg.user_id == "student-A"
        assert msg.data["ungraded"] is True
        assert msg.data["prompt"] is True
        assert msg.data["ai_generated"] is False
        assert "fractions" in msg.data["text"]
    asyncio.run(run())


def test_two_ai_replies_are_bounded_and_never_grade_or_write_progress():
    async def run():
        sink, bridge = teacher()
        await bridge.begin("startup")
        assert not bridge.answer("I like math", 999)
        assert not bridge.answer("", 1)
        assert not bridge.answer("secret" * 100, 1)
        assert bridge.answer("I'm curious", 1)
        assert not bridge.answer("second simultaneous submission", 1)
        await bridge.task
        first = sink.messages[-1][1].data
        assert first["ai_generated"] is True and first["ungraded"] is True
        assert first["prompt"] is True
        assert bridge.answer("Because I can share pizza", 1)
        await bridge.task
        last = sink.messages[-1][1].data
        assert last["prompt"] is False and last["ungraded"] is True
        assert not bridge.answer("More grading please", 1)
        assert bridge.replies == MAX_REPLIES
        assert all(m.event_type == "bridge_message" for _, m in sink.messages)
        assert all("verdict" not in m.data and "mastery" not in m.data
                   for _, m in sink.messages)
    asyncio.run(run())


def test_transition_replaces_pending_answer_and_drops_stale_generation():
    async def delayed(topic, language, answer):
        await asyncio.sleep(0.2)
        return "This reply should not be delivered."
    async def run():
        sink, bridge = teacher(delayed)
        await bridge.begin("startup")
        assert bridge.answer("start reply", 1)
        await bridge.begin("transition")
        await asyncio.sleep(0.22)
        assert len(sink.messages) == 2  # startup and new transition question
        assert sink.messages[-1][1].data["generation"] == 2
        bridge.close()
        assert not bridge.answer("stale after handoff", 2)
    asyncio.run(run())


def test_provider_outage_leads_to_local_ungraded_ack_without_progress():
    async def unavailable(topic, language, answer):
        raise RuntimeError("provider capacity")
    async def run():
        sink, bridge = teacher(unavailable)
        await bridge.begin("startup")
        assert bridge.answer("A guess", 1)
        await bridge.task
        result = sink.messages[-1][1].data
        assert result["ai_generated"] is False
        assert result["ungraded"] is True
        assert result["prompt"] is True
        assert "starting point" in result["text"]
    asyncio.run(run())


def test_transition_task_keeps_reply_channel_live_while_scene_is_generating():
    """Repro for sequential socket receiver: answers must be processed before scene."""
    async def run():
        complete = asyncio.Event()
        received = []
        sink, bridge = teacher()

        async def real_director(message):
            received.append(message)
            await complete.wait()

        runner = SerializedTransitionRunner(bridge, real_director)
        assert await runner.start('continue-1')
        assert runner.busy
        assert len(sink.messages) == 1
        assert sink.messages[0][1].data["phase"] == "transition"
        assert not await runner.start('duplicate-continue')
        assert bridge.answer("I noticed a pattern", 1)
        await bridge.task
        assert sink.messages[-1][1].data["ungraded"]
        assert len(received) == 1  # absolutely no duplicate lesson advance
        complete.set()
        await runner.task
        assert not runner.busy
        assert not bridge.answer("late feedback", 1)
        await runner.shutdown()

    asyncio.run(run())


def test_transition_shutdown_cancels_authoritative_task_on_disconnect():
    async def run():
        sink, bridge = teacher()
        started = asyncio.Event()
        async def never_finish(message):
            started.set()
            await asyncio.Event().wait()
        runner = SerializedTransitionRunner(bridge, never_finish)
        assert await runner.start("continue")
        await started.wait()
        await runner.shutdown()
        assert runner.task.done() and not runner.busy
        assert not bridge.active
    asyncio.run(run())


def test_failed_authoritative_transition_is_reported_without_grade_side_effects():
    async def run():
        sink, bridge = teacher()
        failures = []
        async def fails(_message):
            raise RuntimeError("the user's sensitive submitted answer")
        async def signal_failure():
            failures.append("lesson_transition_failed")
        runner = SerializedTransitionRunner(bridge, fails, on_error=signal_failure)
        assert await runner.start("continue")
        await runner.task
        assert failures == ["lesson_transition_failed"]
        assert bridge.active is False
        assert not runner.busy
        assert all(m.event_type == "bridge_message" for _, m in sink.messages)
        assert not bridge.answer("late", 1)
    asyncio.run(run())


def test_bridge_delivery_failure_never_blocks_real_lesson_action():
    class BrokenDelivery:
        async def send_to_connection(self, *_args):
            raise OSError("socket transport unavailable")

    async def run():
        connection = SimpleNamespace(
            connection_id="c1", session_id="session-A", user_id="student-A"
        )
        bridge = ContinuousTeachingBridge(BrokenDelivery(), connection, "fractions", "en-US")
        called = []
        async def real_director(message):
            called.append(message)
        runner = SerializedTransitionRunner(bridge, real_director)
        assert await runner.start("continue")
        await runner.task
        assert called == ["continue"]
        assert bridge.active is False
    asyncio.run(run())


def test_untrusted_socket_identity_cannot_redirect_continuous_or_graded_action():
    socket_session = "session-A"
    socket_user = "learner-A"
    assert message_is_session_scoped(
        {"event_type": "bridge_reply"}, socket_session, socket_user
    )  # omitted IDs are injected from the authenticated connection
    assert message_is_session_scoped(
        {"event_type": "user_action", "session_id": socket_session,
         "user_id": socket_user}, socket_session, socket_user
    )
    assert not message_is_session_scoped(
        {"event_type": "user_action", "session_id": "session-B",
         "user_id": socket_user}, socket_session, socket_user
    )
    assert not message_is_session_scoped(
        {"event_type": "user_action", "session_id": socket_session,
         "user_id": "learner-B"}, socket_session, socket_user
    )
    assert not message_is_session_scoped(
        {"event_type": "bridge_reply", "session_id": "session-B"},
        socket_session, socket_user
    )
    assert not message_is_session_scoped(
        {"event_type": "bridge_reply", "user_id": "learner-B"},
        socket_session, socket_user
    )
