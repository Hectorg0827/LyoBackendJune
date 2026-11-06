"""The classroom teacher, companion, and AI classmates have separate roles."""

import asyncio
from types import SimpleNamespace

import pytest

from lyo_app.ai_classroom.classroom_cast import (
    CLASSMATES, TEACHERS, add_classmate_turn, teacher_for_topic,
)
from lyo_app.ai_classroom.sdui_models import ExampleBlock, Scene, SceneType, StudentPrompt, TeacherMessage


def _scene():
    return Scene(scene_type=SceneType.INSTRUCTION, components=[
        TeacherMessage(text="A fraction names equal parts of a whole."),
        ExampleBlock(title="Fractions", content="Four equal slices each represent one quarter."),
    ])


def test_character_registry_is_separate_from_lyo_and_stable():
    assert len(TEACHERS) == len(CLASSMATES) == 4
    assert len({character.id for character in (*TEACHERS, *CLASSMATES)}) == 8
    assert teacher_for_topic("Algebra") == teacher_for_topic("algebra")
    assert all(character.id != "lyo" for character in (*TEACHERS, *CLASSMATES))


@pytest.mark.asyncio
async def test_disabled_peers_do_not_create_synthetic_people_or_model_calls(monkeypatch):
    monkeypatch.delenv("LYO_CLASSROOM_AI_PEERS_ENABLED", raising=False)
    context = SimpleNamespace(classroom_mode="classroom")
    scene = _scene()
    assert await add_classmate_turn(scene, context, {}) is scene
    assert not any(isinstance(component, StudentPrompt) for component in scene.components)


@pytest.mark.asyncio
async def test_authored_peers_are_bounded_and_saved_without_duplication(monkeypatch):
    monkeypatch.setenv("LYO_CLASSROOM_AI_PEERS_ENABLED", "true")
    from lyo_app.ai_classroom import adaptive_teaching
    calls = []

    async def authored(_system, payload, _schema):
        calls.append(payload)
        return SimpleNamespace(text="Why must all four slices be the same size?", purpose="ask_clarifying")

    monkeypatch.setattr(adaptive_teaching, "model_json", authored)
    context = SimpleNamespace(classroom_mode="classroom")
    progress = {"guided_state": {}}
    first, second, third = _scene(), _scene(), _scene()
    for scene in (first, second):
        progress["guided_state"]["scene"] = scene.model_dump(mode="json")
        await add_classmate_turn(scene, context, progress)
        assert not any(isinstance(c, StudentPrompt) for c in scene.components)
    progress["guided_state"]["scene"] = third.model_dump(mode="json")
    await add_classmate_turn(third, context, progress)
    peers = [c for c in third.components if isinstance(c, StudentPrompt)]
    assert len(peers) == 1
    assert peers[0].student_name == "Maya"
    assert peers[0].student_avatar == "student_maya"
    assert len(calls) == 1
    assert "learner_answer" not in calls[0]
    assert progress["guided_state"]["scene"]["components"][2]["type"] == "StudentPrompt"
    await add_classmate_turn(third, context, progress)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_solo_mode_never_spawns_classmates(monkeypatch):
    monkeypatch.setenv("LYO_CLASSROOM_AI_PEERS_ENABLED", "true")
    scene = _scene()
    progress = {}
    await add_classmate_turn(scene, SimpleNamespace(classroom_mode="solo"), progress)
    assert progress == {}


@pytest.mark.asyncio
async def test_slow_optional_classmate_has_three_second_budget(monkeypatch):
    """A stalled peer may disappear, but cannot hold a learner's scene for 12s."""
    monkeypatch.setenv("LYO_CLASSROOM_AI_PEERS_ENABLED", "true")
    from lyo_app.ai_classroom import adaptive_teaching, classroom_cast

    async def authored(_system, _payload, _schema):
        raise AssertionError("The optional provider call should have timed out")

    async def timed_out(awaitable, *, timeout):
        assert timeout == 3
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(adaptive_teaching, "model_json", authored)
    monkeypatch.setattr(classroom_cast.asyncio, "wait_for", timed_out)
    scene = _scene()
    progress = {"peer_eligible_scenes": 2, "guided_state": {"scene": scene.model_dump(mode="json")}}
    result = await add_classmate_turn(scene, SimpleNamespace(classroom_mode="classroom"), progress)
    assert result is scene
    assert not any(isinstance(c, StudentPrompt) for c in scene.components)
    assert progress.get("peer_turns_generated", 0) == 0
