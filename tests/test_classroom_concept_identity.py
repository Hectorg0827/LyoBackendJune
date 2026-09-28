"""Canonical concept identity survives the adaptive teaching pathway."""
import unittest
import uuid
import json
from unittest.mock import AsyncMock, patch

import pytest

from lyo_app.ai.lesson_composer import slugify_skill
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    _SESSION_PROGRESS, SceneLifecycleEngine, session_concept,
)
from lyo_app.ai_classroom.sdui_models import ActionIntent, InputField, QuizCard
from lyo_app.ai_classroom.adaptive_teaching import LearningPlan, LearningUnit, GuidedState, TeachingUnavailable
from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from tests.adaptive_fixtures import (
    action, context, engine, seed, plan, ScriptedTeacher, tap_probe, simulated_skill_identity,
)

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


def test_non_latin_skills_remain_distinct_in_plans_and_evidence():
    units = [LearningUnit(title=title, objective="Learn to compare a particular type of concept.",
                          material="Each concept has specific criteria and a worked example of the comparison.")
             for title in ("客户细分", "顧客分析")]
    LearningPlan(units=units)
    assert slugify_skill(units[0].title) != slugify_skill(units[1].title)
    with pytest.raises(ValueError, match="distinct, specific skills"):
        LearningPlan(units=[units[0], units[0].model_copy(update={"title": "客户细分！"})])


@pytest.mark.parametrize("title", ["Introduction", "Basics", "Part 1", "Lesson 2"])
def test_generic_titles_cannot_merge_unrelated_subjects_records(title):
    unit = LearningUnit(title=title, objective="Compare equal parts of the same whole.",
                        material="Equal parts of the same whole can be compared with a common denominator.")
    with pytest.raises(ValueError, match="distinct, specific skills"):
        LearningPlan(units=[unit])


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
@pytest.mark.parametrize("topic,title,has_identity", [
    ("Square roots", None, True),
    ("Mathematics", "Square roots", True),
    (None, None, False),
])
async def test_live_evidence_names_the_taught_lesson_or_topic_never_a_generic_objective(kind, topic, title, has_identity):
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
    if has_identity:
        expected = simulated_skill_identity(ctx, plan()).unit_ids[0]
        assert log.await_args.args[1].concept_id == expected
        assert dkt.await_args.args[2] == expected
        assert expected != slugify_skill(ctx.learning_objective)
    else:
        log.assert_not_awaited()
        dkt.assert_not_awaited()


class LiveComponentConceptTests(unittest.IsolatedAsyncioTestCase):
    """The guided pathway's actual components and evidence share one identity."""

    async def test_a_generated_quiz_names_the_unit_instead_of_prose(self):
        teacher = ScriptedTeacher()
        runner, progress = AdaptiveSession(teacher), {}
        ctx = _context(target_duration_minutes=24, lesson_title=None)
        scene = await runner.run(ctx, progress, action(welcome=True, record_scope="unit"))
        current = GuidedState.model_validate(progress["guided_state"])
        card = next(c for c in scene.components if isinstance(c, QuizCard))
        self.assertEqual(card.concept_id, current.unit.title)
        self.assertNotEqual(card.concept_id, OBJECTIVE)

    async def test_a_transfer_question_and_graded_answer_keep_topic_identity(self):
        teacher = ScriptedTeacher()
        runner, progress = AdaptiveSession(teacher), {}
        ctx = _context(target_duration_minutes=8, lesson_title=None)
        await runner.run(ctx, progress, action(welcome=True))
        await tap_probe(runner, progress, ctx)
        for _ in range(4):
            pending = GuidedState.model_validate(progress["guided_state"]).pending
            intent = (ActionIntent.SUBMIT_ANSWER if pending.task.response_format == "choice"
                      else ActionIntent.SUBMIT_TRANSFER)
            await runner.run(ctx, progress, action(intent, pending.id,
                answer_data={"selected_option_id": "a", "response": "Four cuts leave longer pieces."}))
        current = GuidedState.model_validate(progress["guided_state"])
        self.assertEqual(current.phase, "transfer")
        scene = await runner.run(ctx, progress, action(welcome=True))
        field = next(c for c in scene.components if isinstance(c, InputField))
        self.assertEqual(field.concept_id, TOPIC)
        self.assertNotEqual(field.concept_id, OBJECTIVE)
        self.assertTrue(field.question.strip())
        self.assertEqual(field.expected_keywords, [])
        await runner.run(ctx, progress, action(ActionIntent.SUBMIT_TRANSFER, current.pending.id,
            answer_data={"response": "Four cuts leave longer pieces from equal ribbons."}))
        self.assertEqual(progress["guided_state"]["outbox"][-1]["concept_id"], TOPIC)

    async def test_missing_topic_cannot_create_a_placeholder_concept(self):
        teacher = ScriptedTeacher()
        runner, progress = AdaptiveSession(teacher), {}
        ctx = _context(topic=None, lesson_title=None, target_duration_minutes=8)
        await runner.run(ctx, progress, action(welcome=True))
        state = GuidedState.model_validate(progress["guided_state"])
        self.assertIsNone(AdaptiveSession.record_concept(ctx, state))
        self.assertIsNone(session_concept(ctx))
        self.assertIsNone(session_concept(None))
