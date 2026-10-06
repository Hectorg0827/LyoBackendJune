from lyo_app.ai.schemas.lyo2 import Intent
from lyo_app.chat.fast_path import fast_route_intent


def test_fast_route_handles_obvious_chat():
    assert fast_route_intent("Hey!") is Intent.GREETING
    assert fast_route_intent("Who is the president of France?") is Intent.CHAT
    assert fast_route_intent("What about Europe?") is Intent.CHAT


def test_fast_route_keeps_workflows_on_full_router():
    assert fast_route_intent("Create a course on marketing") is None
    assert fast_route_intent("Teach me calculus") is None
    assert fast_route_intent("I have a test next week") is None


def test_fast_route_keeps_media_and_forced_intents_off_fast_lane():
    assert fast_route_intent("What is this?", has_media=True) is None
    assert fast_route_intent("Hi", forced_intent=Intent.COURSE) is None
