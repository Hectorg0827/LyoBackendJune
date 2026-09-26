"""Canonical concept identity survives the adaptive teaching pathway."""
import unittest
import uuid
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lyo_app.ai.lesson_composer import slugify_skill
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    _SESSION_PROGRESS, SceneLifecycleEngine, SceneCompiler, ContextSnapshot, session_concept,
)
from lyo_app.ai_classroom.sdui_models import ActionIntent, InputField
from lyo_app.ai_classroom.adaptive_teaching import LearningPlan, LearningUnit, GuidedState, TeachingUnavailable
from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from tests.adaptive_fixtures import action, context, engine, seed, plan, ScriptedTeacher

PLAN_CONCEPT = "square_roots"
SESSION = "concept-identity-session"
TOPIC = "Quadratic equations"
OBJECTIVE = f"Practise and apply {TOPIC}"


def _context(**overrides):
    return context(session_id=SESSION, **{"topic": TOPIC, "learning_objective": OBJECTIVE, **overrides})


@pytest.fixture(autouse=True)
def clean_sessions():
    _SESSION_PROGRESS.clear()
    yield
    _SESSION_PROGRESS.clear()


@pytest.mark.parametrize("name,expected", [
    ("Square Roots!", "square_roots"),
    ("x" * 200, "x" * 80),
    ("current_concept", None),
    (None, None),
    ("", None),
    ("!!!", None),
])
def test_concepts_share_the_same_key_as_chat_and_never_use_placeholders(name, expected):
    assert SceneLifecycleEngine._canonical_concept_id(name) == expected


def test_a_graph_concept_id_is_preserved():
    concept = str(uuid.uuid4())
    assert SceneLifecycleEngine._canonical_concept_id(concept) == concept


def test_plan_titles_that_collapse_to_one_record_are_rejected():
    units = [LearningUnit(title=title, objective="Compare equal parts of the same whole.",
                          material="Equal parts of the same whole can be compared with a common denominator.")
             for title in ("Square Roots!", "Square Roots?")]
    with pytest.raises(ValueError, match="distinct, specific skills"):
        LearningPlan(units=units)


@pytest.mark.asyncio
async def test_old_session_and_authored_lesson_keep_their_canonical_identity():
    teacher = ScriptedTeacher()
    runner = AdaptiveSession(teacher)
    ctx = context(topic="Mathematics", lesson_title="Quadratic equations", total_lessons=3)
    progress = {}
    await runner.run(ctx, progress, action(welcome=True, record_scope="unit"))
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.record_scope == "topic"
    assert AdaptiveSession.record_concept(ctx, state) == "Quadratic equations"

    # Stored states written before this field existed resume as topic scoped;
    # changing devices cannot silently retarget the next answer.
    old = state.model_dump()
    old.pop("record_scope")
    restored = GuidedState.model_validate(old)
    assert restored.record_scope == "topic"
    assert AdaptiveSession.record_concept(ctx, restored) == "Quadratic equations"


@pytest.mark.asyncio
async def test_reconnecting_without_scope_preserves_unit_identity_and_server_class_labels():
    teacher = ScriptedTeacher()
    runner = AdaptiveSession(teacher)
    ctx = context(target_duration_minutes=24)
    progress = {}
    await runner.run(ctx, progress, action(welcome=True, record_scope="unit"))
    first = GuidedState.model_validate(progress["guided_state"])
    assert first.scene["metadata"]["target_concepts"] == ["Fraction skill 1"]

    # A resumed session is restored from JSON on another device, which may
    # connect without the entry URL's record_scope query parameter.
    progress["guided_state"] = json.loads(json.dumps(progress["guided_state"]))
    await runner.run(ctx, progress, action(welcome=True))
    resumed = GuidedState.model_validate(progress["guided_state"])
    assert resumed.record_scope == "unit"
    assert resumed.pending.id == first.pending.id
    assert AdaptiveSession.record_concept(ctx, resumed) == "Fraction skill 1"


@pytest.mark.asyncio
async def test_first_plan_failure_does_not_drop_unit_scope_on_retry():
    teacher = ScriptedTeacher()
    teacher.plan.side_effect = [TeachingUnavailable("provider unavailable"), plan()]
    runner = AdaptiveSession(teacher)
    ctx = context(target_duration_minutes=24)
    progress = {}
    await runner.run(ctx, progress, action(welcome=True, record_scope="unit"))
    assert "guided_state" not in progress
    assert progress["record_scope"] == "unit"
    await runner.run(ctx, progress, action(ActionIntent.RETRY))
    state = GuidedState.model_validate(progress["guided_state"])
    assert state.record_scope == "unit"
    assert AdaptiveSession.record_concept(ctx, state) == "Fraction skill 1"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["choose", "apply"])
@pytest.mark.parametrize("topic,title,expected", [
    ("Square roots", None, "square_roots"),
    ("Mathematics", "Square roots", "square_roots"),
    (None, None, None),
])
async def test_live_evidence_names_the_taught_lesson_or_topic_never_a_generic_objective(kind, topic, title, expected):
    ctx = context(topic=topic, lesson_title=title, learning_objective="Learn the basic concepts of mathematics")
    instance = engine(ctx)
    component_id = seed(instance, ctx, kind)
    log, dkt = AsyncMock(), AsyncMock()
    with patch("lyo_app.events.processor.log_learning_event", log), \
         patch("lyo_app.personalization.service.DeepKnowledgeTracer.update_mastery", dkt):
        if kind == "choose":
            await instance.handle_quiz_submission("42", "fractions", component_id, "a", 4000)
        else:
            await instance.handle_transfer_submission("42", "fractions", component_id, "One half, because fewer cuts make bigger pieces.", 4000)
    if expected:
        assert log.await_args.args[1].concept_id == expected
        assert dkt.await_args.args[2] == expected
    else:
        log.assert_not_awaited()
        dkt.assert_not_awaited()


class GeneratedComponentConceptTests(unittest.IsolatedAsyncioTestCase):
    """The components the engine builds itself must carry a concept, not prose.

    The first version of this fix changed only the two submission handlers, and
    it did not work. The handlers read the component's own `concept_id` first
    and fall back to the session's concept:

        validated_skill_id = comp.concept_id or self._session_concept(...)

    That precedence is right — an authored course names its concepts, and those
    should win. But the engine's *own* generated components were built with
    `concept_id=context.learning_objective`, so in the ordinary case there was
    nothing to fall back to: the prose won, exactly as before, and the fix was
    inert for every freeform session it was written for.

    The earlier tests missed it because they built scenes with no `concept_id`,
    which is not what the engine produces. These call the real builders.
    """

    def test_the_transfer_prompt_names_the_concept_not_the_objective(self):
        compiler = SceneCompiler()

        components = compiler._create_transfer_components(_context())

        fields = [c for c in components if isinstance(c, InputField)]
        self.assertEqual(len(fields), 1, "expected one transfer input")
        self.assertEqual(fields[0].concept_id, TOPIC)
        self.assertNotEqual(fields[0].concept_id, OBJECTIVE)

    def test_the_transfer_prompt_still_reads_as_prose(self):
        # The objective has a job: it is what the question and the rubric
        # keywords are written from. Taking it out of `concept_id` must not
        # take it out of the teaching.
        compiler = SceneCompiler()

        components = compiler._create_transfer_components(_context())

        fields = [c for c in components if isinstance(c, InputField)]
        self.assertTrue(fields[0].question.strip(), "the transfer question went missing")

    async def test_a_generated_quiz_names_the_concept_not_the_objective(self):
        compiler = SceneCompiler()
        context = _context()
        payload = {
            "question": "Which value satisfies the equation?",
            "options": [
                {"id": "a", "label": "x = 2", "is_correct": True, "feedback_correct": "Yes."},
                {"id": "b", "label": "x = 5", "is_correct": False, "feedback_incorrect": "No."},
            ],
        }
        manager = MagicMock()
        manager.chat_completion = AsyncMock(
            return_value={"content": json.dumps(payload), "is_fallback": False}
        )
        with patch("lyo_app.core.ai_resilience.ai_resilience_manager", manager):
            card = await compiler._generate_quiz_question(context)

        self.assertEqual(card.concept_id, TOPIC)
        self.assertNotEqual(card.concept_id, OBJECTIVE)

    async def test_the_fallback_quiz_names_the_concept_too(self):
        # The path taken when every provider fails. It is the one most likely
        # to run on a bad day, so it must not be the one that files a learner's
        # work under a pseudo-concept.
        compiler = SceneCompiler()
        context = _context()
        manager = MagicMock()
        manager.chat_completion = AsyncMock(return_value={"is_fallback": True, "content": ""})
        with patch("lyo_app.core.ai_resilience.ai_resilience_manager", manager):
            card = await compiler._generate_quiz_question(context)

        self.assertEqual(card.concept_id, TOPIC)
        self.assertNotEqual(card.concept_id, OBJECTIVE)

    def test_a_session_with_no_identity_has_no_concept(self):
        # `_canonical_concept_id` rejects the `current_concept` placeholder the
        # callers fall back to, so evidence is dropped rather than pooled under
        # a fake row. That is the intended end state for a session with nothing
        # to name.
        self.assertIsNone(session_concept(_context(topic=None, lesson_title=None)))
        self.assertIsNone(session_concept(None))
