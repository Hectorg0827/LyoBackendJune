"""A Classroom's requested topic must survive subsequent authenticated socket turns.

A missed current_topic assignment used to turn "Comparing fractions" into
"ct-grade-{opaque ID}" on the very next learner action, despite the first scene
having the correct topic.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.conversation_flow import ConversationManager, ConversationSession
from lyo_app.ai_classroom.scene_lifecycle_engine import ContextAssembler
from lyo_app.ai_classroom.websocket_routes import _send_welcome_scene
from lyo_app.ai_classroom.websocket_manager import StreamingMode


def connection(user="42", sid="ct-test-session-42", topic="Comparing fractions"):
    return SimpleNamespace(
        user_id=user, session_id=sid,
        websocket=SimpleNamespace(query_params={"topic": topic, "language": "en-US"}),
    )


async def launch(monkeypatch, cm, conn):
    monkeypatch.setattr(
        "lyo_app.ai_classroom.conversation_flow.get_conversation_manager",
        lambda: cm,
    )
    engine = SimpleNamespace(
        process_trigger=AsyncMock(return_value=SimpleNamespace(scene_id="test-scene")),
    )
    await _send_welcome_scene(engine, conn, StreamingMode.ADAPTIVE)
    await asyncio.sleep(0)
    engine.process_trigger.assert_awaited_once()
    return engine.process_trigger.await_args.args[0]


@pytest.mark.asyncio
async def test_new_authenticated_socket_keeps_topic_on_next_action(monkeypatch):
    cm = ConversationManager()
    conn = connection()
    trigger = await launch(monkeypatch, cm, conn)
    assert trigger.action_data["topic"] == "Comparing fractions"
    assert cm.get_session(conn.session_id).current_topic == "Comparing fractions"
    after_welcome = SimpleNamespace(
        user_id=conn.user_id,
        session_id=conn.session_id,
        course_id=None,
        action_data={"action_intent": "submit_answer"},
    )
    topic, _, _, _ = await ContextAssembler(SimpleNamespace())._resolve_topic(after_welcome)
    assert topic == "Comparing fractions"  # Never the internal ID.


@pytest.mark.asyncio
async def test_existing_owned_session_without_topic_is_seeded_once(monkeypatch):
    cm = ConversationManager()
    cm._sessions["ct-test-session-42"] = ConversationSession(
        session_id="ct-test-session-42", user_id="42", current_topic=None,
    )
    await launch(monkeypatch, cm, connection())
    assert cm.get_session("ct-test-session-42").current_topic == "Comparing fractions"
    await launch(monkeypatch, cm, connection(topic="A different injected topic"))
    assert cm.get_session("ct-test-session-42").current_topic == "Comparing fractions"


@pytest.mark.asyncio
async def test_other_owner_cannot_inherit_or_overwrite_topic(monkeypatch):
    cm = ConversationManager()
    cm._sessions["ct-test-session-42"] = ConversationSession(
        session_id="ct-test-session-42", user_id="42",
        current_topic="Owner's private lesson",
    )
    trigger = await launch(monkeypatch, cm, connection(user="43", topic="Public mathematics"))
    assert trigger.action_data["topic"] == "Public mathematics"
    assert cm.get_session("ct-test-session-42").user_id == "42"
    assert cm.get_session("ct-test-session-42").current_topic == "Owner's private lesson"
