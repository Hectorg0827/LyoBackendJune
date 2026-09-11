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

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from lyo_app.ai.lesson_composer import slugify_skill
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    _SESSION_PROGRESS,
    ContextSnapshot,
    SceneLifecycleEngine,
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
    the session's objective.
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


if __name__ == "__main__":
    unittest.main()
