"""Continuous Teaching bridge safety contract; no provider network calls in CI."""
import asyncio
from types import SimpleNamespace

from lyo_app.ai_classroom.continuous_teaching import (
    MAX_REPLIES, ContinuousTeachingBridge, bridge_enabled, fallback_ack,
    initial_prompt, short_topic,
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
