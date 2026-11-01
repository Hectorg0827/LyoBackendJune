"""Character identities and bounded AI classmate turns for LYO Classroom.

Lyo is the learner's companion, never the classroom teacher. The four existing
teacher and classmate illustrations are selected by stable IDs. Classmates are
shown only after an actual, authored speaking turn has reached the client.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from lyo_app.ai_classroom.sdui_models import Scene, StudentPrompt, TeacherMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    trait: str
    voice: str


TEACHERS = (
    Character("teacher_1", "Teacher 1", "clear and patient", "onyx"),
    Character("teacher_2", "Teacher 2", "warm and reflective", "echo"),
    Character("teacher_3", "Teacher 3", "expressive and creative", "fable"),
    Character("teacher_4", "Teacher 4", "gentle and encouraging", "shimmer"),
)

CLASSMATES = (
    Character("student_maya", "Maya", "clever and cheeky", "alloy"),
    Character("student_sam", "Sam", "cool and analytical", "nova"),
    Character("student_rio", "Rio", "funny and supportive", "fable"),
    Character("student_zack", "Zack", "curious and persistent", "echo"),
)


def teacher_for_topic(topic: str) -> Character:
    """The same subject gets the same teacher on every client/platform."""
    index = sum(ord(char) for char in (topic or "").lower()) % len(TEACHERS)
    return TEACHERS[index]


def classmate_feature_enabled() -> bool:
    # Extra model calls are explicitly opt-in, and never enable paid TTS.
    return os.getenv("LYO_CLASSROOM_AI_PEERS_ENABLED", "false").lower() == "true"


async def add_classmate_turn(scene: Scene, context, progress: dict) -> Scene:
    """Author at most one useful peer question every three new lesson scenes.

    This is a separate, optional multi-agent teaching layer. It never grades
    the learner, invents evidence, delays the canonical teacher on provider
    failure, or re-authors a saved scene when the learner reconnects.
    """
    if not classmate_feature_enabled():
        return scene
    mode = getattr(context, "classroom_mode", "solo")
    if str(getattr(mode, "value", mode)) != "classroom":
        return scene
    if progress.get("last_peer_checked_scene") == scene.scene_id:
        return scene
    if any(isinstance(component, StudentPrompt) for component in scene.components):
        return scene
    if len(scene.components) >= 10 or scene.metadata.presentation_focus != "board":
        return scene

    progress["last_peer_checked_scene"] = scene.scene_id
    if progress.get("peer_turns_generated", 0) >= 4:
        return scene
    scene_count = progress.get("peer_eligible_scenes", 0) + 1
    progress["peer_eligible_scenes"] = scene_count
    if scene_count % 3 != 0:
        return scene

    teacher = next((c for c in scene.components if isinstance(c, TeacherMessage)), None)
    if teacher is None or len(teacher.text.strip()) < 25 or teacher.text.lstrip().startswith("["):
        return scene
    board = next((str(c.content)[:500] for c in scene.components
                  if getattr(c, "type", "") == "ExampleBlock" and getattr(c, "content", None)), "")
    if not board:
        return scene

    peer = CLASSMATES[progress.get("peer_turns_generated", 0) % len(CLASSMATES)]
    try:
        # Deliberately do not send learner answers, identity or records to
        # this secondary agent; only already-authored lesson content.
        from lyo_app.ai_classroom.adaptive_teaching import StrictModel, model_json

        class PeerLine(StrictModel):
            text: str = Field(min_length=12, max_length=210)
            purpose: Literal["ask_clarifying", "reinforce_concept"]

        response = await asyncio.wait_for(model_json(
            "You are one clearly identified AI classmate, not the teacher or Lyo. "
            "Speak in one brief, natural, age-appropriate turn. Ask a specific, "
            "helpful question grounded in the lesson or offer one accurate "
            "observation. Do not invent personal experience, grade the real "
            "learner, provide an answer key, or introduce an unrelated fact. "
            "Match the language of the teacher's lesson.",
            {"classmate": peer.name, "personality": peer.trait,
             "teacher_said": teacher.text[:400], "board": board},
            PeerLine,
        ), timeout=12)
    except Exception as exc:
        logger.info("Optional AI classmate unavailable: %s", type(exc).__name__)
        return scene

    try:
        component = StudentPrompt(
            student_name=peer.name,
            student_avatar=peer.id,
            personality_trait=("analytical" if peer.id == "student_sam" else
                               "creative" if peer.id == "student_maya" else
                               "supportive" if peer.id == "student_rio" else "curious"),
            purpose=response.purpose,
            text=response.text,
            priority=2,
        )
    except Exception as exc:
        logger.info("Invalid optional classmate turn: %s", type(exc).__name__)
        return scene
    # Let the board appear before the classmate refers to it.
    board_index = next((index for index, item in enumerate(scene.components)
                        if getattr(item, "type", "") == "ExampleBlock"),
                       scene.components.index(teacher))
    scene.components.insert(board_index + 1, component)
    progress["peer_turns_generated"] = progress.get("peer_turns_generated", 0) + 1
    # AdaptiveSession saves its scene before this optional layer runs. Keep
    # the durable resumed scene exactly equal to the one streamed now.
    guided = progress.get("guided_state")
    if isinstance(guided, dict) and isinstance(guided.get("scene"), dict):
        if guided["scene"].get("scene_id") == scene.scene_id:
            guided["scene"] = scene.model_dump(mode="json")
    return scene
