"""A demonstration is recorded against the concept, not the sentence.

The Classroom's teaching objective is prose: "Practise and apply Quadratic
equations". Its concept id is an identity: `quadratic_equations`. Those are
different kinds of thing, and for two graded paths the engine used the first
as the second — slugifying a whole sentence into a pseudo-concept.

Nothing looked broken. Evidence was written, the projection ran, a row
appeared. It was simply a row nothing else would ever read:

    readiness / Chat / spaced repetition -> quadratic_equations
    a web classroom session              -> practise_and_apply_quadratic_equations

So a learner could work through every session their study plan scheduled and
stay at "you haven't started yet" forever, while the evidence for that work
piled up under keys no surface asks about. The same objective text is what
`entry-contract.mjs` sends from Home and Test Prep, so the split hit the whole
web client; iOS sent no objective and landed on the topic by luck.

The rule these tests hold: a concept id may come from an authored component,
from the lesson being taught, or from the topic — never from free text written
for the Director to read.
"""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from lyo_app.ai.lesson_composer import slugify_skill
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    _SESSION_PROGRESS,
    ContextSnapshot,
    SceneCompiler,
    SceneLifecycleEngine,
    session_concept,
)
from lyo_app.ai_classroom.sdui_models import (
    InputField,
    QuizCard,
    QuizOption,
    Scene,
    SceneType,
)

SESSION = "concept-identity-session"

# What a study plan schedules, and how the learner's record names it. These
# two lines are the whole contract: `topic_standing.concept_id_for_topic` is
# `slugify_skill`, the same function the Classroom canonicalizes with.
TOPIC = "Quadratic equations"
PLAN_CONCEPT = slugify_skill(TOPIC)

# What entry-contract.mjs puts in the `objective` query parameter. Prose, meant
# for the Director to teach from.
OBJECTIVE = f"Practise and apply {TOPIC}"


def _engine(context: ContextSnapshot):
    engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
    engine.db = MagicMock()
    engine.db.rollback = AsyncMock()
    engine.session_contexts = {SESSION: context}
    engine.active_scenes = {}
    engine.websocket_manager = None
    engine.process_trigger = AsyncMock(return_value=MagicMock(scene_id="next"))
    return engine


def _context(**overrides) -> ContextSnapshot:
    fields = dict(
        user_id="42",
        session_id=SESSION,
        topic=TOPIC,
        learning_objective=OBJECTIVE,
    )
    fields.update(overrides)
    return ContextSnapshot(**fields)


def _unauthored_quiz() -> Scene:
    """A quiz the Director generated without naming a concept.

    This is the ordinary case for a freeform session — there is no authored
    course to carry concept ids — and it is exactly the case that falls back to
    the session's lesson or topic identity, never to the learning objective.
    """
    quiz = QuizCard(
        component_id="quiz-1",
        question="Which value satisfies the equation?",
        options=[
            QuizOption(id="a", label="x = 2", is_correct=True, feedback_correct="Yes."),
            QuizOption(id="b", label="x = 5", is_correct=False, feedback_incorrect="No."),
        ],
    )
    return Scene(scene_id="s1", scene_type=SceneType.CHALLENGE, components=[quiz])


def _unauthored_transfer() -> Scene:
    field = InputField(
        component_id="input-1",
        placeholder="Explain",
        question="Where else does this shape show up?",
        expected_keywords=["parabola", "roots"],
        min_words=3,
        min_score=0.25,
    )
    return Scene(scene_id="s2", scene_type=SceneType.CHALLENGE, components=[field])


class _Capture:
    def __init__(self):
        self.events = []

    async def log(self, _db, event_in):
        self.events.append(event_in)
        return MagicMock()

    @property
    def only(self):
        assert len(self.events) == 1, f"expected one event, got {len(self.events)}"
        return self.events[0]


def _patches(capture):
    engine = MagicMock()
    engine.return_value.trace_knowledge = AsyncMock(return_value={})
    engine.return_value.dkt.update_mastery = AsyncMock(return_value={})
    return (
        patch("lyo_app.personalization.service.PersonalizationEngine", engine),
        patch("lyo_app.events.processor.log_learning_event", capture.log),
    )


class ConceptIdentityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    def tearDown(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    async def _quiz_event(self, context):
        engine = _engine(context)
        engine.active_scenes = {"s1": _unauthored_quiz()}
        capture = _Capture()
        personalization, log = _patches(capture)
        with personalization, log:
            await engine.handle_quiz_submission(
                user_id="42",
                session_id=SESSION,
                quiz_component_id="quiz-1",
                selected_option_id="a",
                response_time_ms=4000,
            )
        return capture.only

    async def _transfer_event(self, context):
        engine = _engine(context)
        engine.active_scenes = {"s2": _unauthored_transfer()}
        capture = _Capture()
        personalization, log = _patches(capture)
        with personalization, log:
            await engine.handle_transfer_submission(
                user_id="42",
                session_id=SESSION,
                input_component_id="input-1",
                response="A parabola crosses the axis at its roots.",
                response_time_ms=9000,
            )
        return capture.only

    async def test_a_quiz_lands_on_the_concept_a_study_plan_would_read(self):
        event = await self._quiz_event(_context())

        self.assertEqual(
            event.concept_id,
            PLAN_CONCEPT,
            "the objective sentence was slugified into a pseudo-concept, so "
            "readiness can never see this work",
        )

    async def test_a_transfer_response_lands_on_the_same_concept(self):
        event = await self._transfer_event(_context())

        self.assertEqual(event.concept_id, PLAN_CONCEPT)

    async def test_no_concept_id_is_ever_derived_from_the_objective(self):
        # Stated separately from the two above because it is the rule, not an
        # example of it: if the objective ever reaches the key again with
        # different wording, those tests could still pass by coincidence.
        for event in (
            await self._quiz_event(_context()),
            await self._transfer_event(_context()),
        ):
            self.assertNotEqual(event.concept_id, slugify_skill(OBJECTIVE))
            self.assertNotIn("practise", event.concept_id)

    async def test_the_lesson_being_taught_wins_over_the_topic(self):
        # A course-backed session teaches one lesson of a broader topic, and
        # that lesson is the more specific true concept. This is the precedence
        # the engine already applies when choosing what to teach; the concept
        # key must not disagree with it.
        context = _context(lesson_title="Completing the square")

        event = await self._quiz_event(context)

        self.assertEqual(event.concept_id, slugify_skill("Completing the square"))

    async def test_an_authored_concept_id_still_wins_over_everything(self):
        engine = _engine(_context(lesson_title="Completing the square"))
        scene = _unauthored_quiz()
        scene.components[0].concept_id = "vertex_form"
        engine.active_scenes = {"s1": scene}
        capture = _Capture()
        personalization, log = _patches(capture)
        with personalization, log:
            await engine.handle_quiz_submission(
                user_id="42",
                session_id=SESSION,
                quiz_component_id="quiz-1",
                selected_option_id="a",
                response_time_ms=4000,
            )

        self.assertEqual(capture.only.concept_id, "vertex_form")

    async def test_a_session_with_nothing_to_name_writes_no_evidence(self):
        # Rather than pooling unrelated work under a placeholder concept.
        context = _context(topic=None, learning_objective=OBJECTIVE)

        engine = _engine(context)
        engine.active_scenes = {"s1": _unauthored_quiz()}
        capture = _Capture()
        personalization, log = _patches(capture)
        with personalization, log:
            await engine.handle_quiz_submission(
                user_id="42",
                session_id=SESSION,
                quiz_component_id="quiz-1",
                selected_option_id="a",
                response_time_ms=4000,
            )

        self.assertEqual(capture.events, [])


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


class IdentitylessSessionTests(unittest.IsolatedAsyncioTestCase):
    """A session with nothing to name records nothing, on every path.

    `_canonical_concept_id` rejects the `current_concept` placeholder for a
    stated reason: recording against it pools unrelated work into a single fake
    row. `_log_classroom_evidence` honours that and drops the write.

    The DKT trace did not. It was gated on `scored` alone and fell back to the
    placeholder, so every identity-less graded session in the product — across
    unrelated learners and unrelated subjects — accumulated into one shared
    `current_concept` mastery record. One of the two systems dropped the work
    and the other pooled it, which is worse than either choice made twice.
    """

    def setUp(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    def tearDown(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    async def _submit_quiz(self, context):
        engine = _engine(context)
        engine.active_scenes = {"s1": _unauthored_quiz()}
        capture = _Capture()
        personalization = MagicMock()
        personalization.return_value.trace_knowledge = AsyncMock(return_value={})
        personalization.return_value.dkt.update_mastery = AsyncMock(return_value={})
        with patch("lyo_app.personalization.service.PersonalizationEngine", personalization), \
             patch("lyo_app.events.processor.log_learning_event", capture.log):
            await engine.handle_quiz_submission(
                user_id="42",
                session_id=SESSION,
                quiz_component_id="quiz-1",
                selected_option_id="a",
                response_time_ms=4000,
            )
        return personalization, capture

    async def _submit_transfer(self, context):
        engine = _engine(context)
        engine.active_scenes = {"s2": _unauthored_transfer()}
        capture = _Capture()
        personalization = MagicMock()
        personalization.return_value.trace_knowledge = AsyncMock(return_value={})
        personalization.return_value.dkt.update_mastery = AsyncMock(return_value={})
        with patch("lyo_app.personalization.service.PersonalizationEngine", personalization), \
             patch("lyo_app.events.processor.log_learning_event", capture.log):
            await engine.handle_transfer_submission(
                user_id="42",
                session_id=SESSION,
                input_component_id="input-1",
                response="A parabola crosses the axis at its roots.",
                response_time_ms=9000,
            )
        return personalization, capture

    async def test_an_identityless_quiz_is_not_traced_against_a_placeholder(self):
        nameless = _context(topic=None, lesson_title=None)

        personalization, capture = await self._submit_quiz(nameless)

        personalization.return_value.trace_knowledge.assert_not_awaited()
        self.assertEqual(capture.events, [], "evidence already declined to record this")

    async def test_an_identityless_transfer_is_not_traced_either(self):
        # The transfer path persists through `dkt.update_mastery`, not
        # `trace_knowledge`. Asserting the quiz path's method here passed
        # trivially in the first draft of this test — green, and proving
        # nothing about the path it named.
        nameless = _context(topic=None, lesson_title=None)

        personalization, capture = await self._submit_transfer(nameless)

        personalization.return_value.dkt.update_mastery.assert_not_awaited()
        self.assertEqual(capture.events, [])

    async def test_a_named_session_is_still_traced(self):
        # The guard must not cost the ordinary case its mastery update.
        personalization, capture = await self._submit_quiz(_context())

        personalization.return_value.trace_knowledge.assert_awaited()
        request = personalization.return_value.trace_knowledge.await_args.args[1]
        self.assertEqual(request.skill_id, PLAN_CONCEPT)
        self.assertEqual(capture.only.concept_id, PLAN_CONCEPT)

    async def test_a_named_transfer_is_still_traced(self):
        personalization, capture = await self._submit_transfer(_context())

        personalization.return_value.dkt.update_mastery.assert_awaited()
        # (db, user_id, skill_id, correct, seconds, hints)
        skill_id = personalization.return_value.dkt.update_mastery.await_args.args[2]
        self.assertEqual(skill_id, PLAN_CONCEPT)
        self.assertEqual(capture.only.concept_id, PLAN_CONCEPT)


if __name__ == "__main__":
    unittest.main()
