"""The Classroom writes to the shared event stream, not just reads from it.

Chat already logs every check as evidence, and the event processor projects
that into `ai_classroom.MasteryState` — the table this engine consults before
deciding how to teach. Until now the traffic went one way: the Classroom read
the learner model and never wrote to it, so its own last question could not
inform its next lesson, and nothing it taught was visible to Chat.

These tests drive the real submission handlers, with only the collaborators
that need a database stubbed out, and assert on the event that actually
reaches `log_learning_event`. Asserting that the emitting code *exists* would
pass just as happily if nothing ever called it.
"""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from lyo_app.ai.lesson_composer import slugify_skill

from lyo_app.ai_classroom.scene_lifecycle_engine import (
    _SESSION_PROGRESS,
    SceneLifecycleEngine,
)
from lyo_app.ai_classroom.sdui_models import (
    InputField,
    QuizCard,
    QuizOption,
    Scene,
    SceneType,
)

SESSION = "evidence-session"
CONCEPT = "compare_fractions"


def _engine():
    engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
    engine.db = MagicMock()
    engine.db.rollback = AsyncMock()
    engine.session_contexts = {}
    engine.active_scenes = {}
    engine.websocket_manager = None
    # The scene this submission produces is not what these tests are about.
    engine.process_trigger = AsyncMock(return_value=MagicMock(scene_id="next"))
    return engine


def _quiz_scene(concept_id=CONCEPT):
    quiz = QuizCard(
        component_id="quiz-1",
        question="Which fraction is larger?",
        concept_id=concept_id,
        options=[
            QuizOption(id="a", label="1/2", is_correct=True, feedback_correct="Yes."),
            QuizOption(
                id="b",
                label="1/3",
                is_correct=False,
                feedback_incorrect="Not quite.",
                misconception_tag="bigger_denominator_is_bigger",
            ),
        ],
    )
    return Scene(scene_id="s1", scene_type=SceneType.CHALLENGE, components=[quiz])


def _transfer_scene(evidence_type="transfer", concept_id=CONCEPT):
    field = InputField(
        component_id="input-1",
        placeholder="Explain in your own words",
        question="Where else would you use a common denominator?",
        concept_id=concept_id,
        evidence_type=evidence_type,
        expected_keywords=["denominator", "equal", "parts"],
        min_words=3,
        min_score=0.25,
    )
    return Scene(scene_id="s2", scene_type=SceneType.CHALLENGE, components=[field])


class _Capture:
    """Stands in for the personalization engine and the event log."""

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
    """Silence the DKT writes; capture the event log."""
    engine = MagicMock()
    engine.return_value.trace_knowledge = AsyncMock(return_value={})
    engine.return_value.dkt.update_mastery = AsyncMock(return_value={})
    return (
        patch("lyo_app.personalization.service.PersonalizationEngine", engine),
        patch("lyo_app.events.processor.log_learning_event", capture.log),
    )


class ClassroomQuizEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    def tearDown(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    async def _submit(self, engine, option_id="a"):
        capture = _Capture()
        personalization, log = _patches(capture)
        with personalization, log:
            await engine.handle_quiz_submission(
                user_id="42",
                session_id=SESSION,
                quiz_component_id="quiz-1",
                selected_option_id=option_id,
                response_time_ms=4000,
            )
        return capture

    async def test_a_correct_quiz_answer_reaches_the_shared_event_stream(self):
        engine = _engine()
        engine.active_scenes = {"s1": _quiz_scene()}

        event = (await self._submit(engine)).only

        self.assertEqual(event.user_id, 42)
        self.assertEqual(event.concept_id, CONCEPT)
        self.assertEqual(event.source_surface, "classroom")
        self.assertEqual(event.measurable_outcome, 1.0)

    async def test_a_multiple_choice_hit_is_recorded_as_recognition_not_mastery(self):
        engine = _engine()
        engine.active_scenes = {"s1": _quiz_scene()}

        event = (await self._submit(engine)).only

        # Picking the right option out of two proves the weakest positive rung.
        # Recording it higher would let a lucky guess look like understanding.
        self.assertEqual(event.evidence_type, "recognition")

    async def test_a_wrong_answer_carries_its_misconception_forward(self):
        engine = _engine()
        engine.active_scenes = {"s1": _quiz_scene()}

        event = (await self._submit(engine, option_id="b")).only

        self.assertEqual(event.measurable_outcome, 0.0)
        self.assertEqual(event.misconception, "bigger_denominator_is_bigger")
        # Wrong is still exposure, never negative evidence of a higher rung.
        self.assertEqual(event.evidence_type, "exposure")

    async def test_the_learners_answer_is_never_counted_against_mastery_twice(self):
        """`skill_ids_json` is what asks the processor to run a DKT update.

        Both handlers already run one directly for the same answer, so passing
        it here would apply a single answer to the learner's mastery twice.
        """
        engine = _engine()
        engine.active_scenes = {"s1": _quiz_scene()}

        event = (await self._submit(engine)).only

        self.assertIsNone(event.skill_ids_json)

    async def test_a_guest_submission_writes_no_learner_record(self):
        engine = _engine()
        engine.active_scenes = {"s1": _quiz_scene()}
        capture = _Capture()
        personalization, log = _patches(capture)
        with personalization, log:
            await engine.handle_quiz_submission(
                user_id="guest-abc",
                session_id=SESSION,
                quiz_component_id="quiz-1",
                selected_option_id="a",
                response_time_ms=4000,
            )
        self.assertEqual(capture.events, [])

    async def test_an_unattributed_question_logs_nothing_rather_than_guessing(self):
        engine = _engine()
        engine.active_scenes = {"s1": _quiz_scene(concept_id=None)}

        capture = await self._submit(engine)

        self.assertEqual(capture.events, [])

    async def test_a_failure_to_log_never_costs_the_learner_their_turn(self):
        engine = _engine()
        engine.active_scenes = {"s1": _quiz_scene()}

        async def _explode(*_args, **_kwargs):
            raise RuntimeError("event stream is down")

        personalization, _ = _patches(_Capture())
        with personalization, patch(
            "lyo_app.events.processor.log_learning_event", _explode
        ):
            await engine.handle_quiz_submission(
                user_id="42",
                session_id=SESSION,
                quiz_component_id="quiz-1",
                selected_option_id="a",
                response_time_ms=4000,
            )

        # The next scene was still produced.
        engine.process_trigger.assert_awaited_once()

    async def test_a_question_the_server_could_not_grade_records_nothing(self):
        """A lookup failure is not a wrong answer.

        When the scene or the selected option cannot be found, correctness
        stays at its `False` default. Logging that would mark the learner down
        for a question the server failed to look up — the same shape as
        counting a skipped question wrong.
        """
        engine = _engine()
        engine.active_scenes = {}  # the scene is gone
        # A real session objective is present, so the concept is perfectly
        # nameable. Only the fact that nothing was graded should stop the
        # write — without this the test would pass on the missing concept
        # instead, and would go on passing with the guard removed.
        engine.session_contexts = {
            SESSION: SimpleNamespace(
                learning_objective="Compare fractions", lesson_index=0
            )
        }

        capture = await self._submit(engine)

        self.assertEqual(capture.events, [])


class ClassroomConceptIdentityTests(unittest.IsolatedAsyncioTestCase):
    """The two surfaces have to name a concept the same way.

    Chat keys mastery on `slugify_skill(topic)`. The Classroom carries human
    text — a learning objective or lesson title. Logged raw, "Compare
    fractions" and "compare_fractions" are two concepts to the projection, and
    the surfaces go on keeping separate records of one idea.
    """

    def setUp(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    def tearDown(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    async def _submit(self, concept_id):
        engine = _engine()
        engine.active_scenes = {"s1": _quiz_scene(concept_id=concept_id)}
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
        return capture

    async def test_a_human_readable_objective_is_recorded_as_chat_would_key_it(self):
        event = (await self._submit("Compare Fractions!")).only

        self.assertEqual(event.concept_id, slugify_skill("Compare Fractions!"))
        self.assertEqual(event.concept_id, "compare_fractions")

    async def test_a_graph_concept_id_is_left_alone(self):
        """Slugifying a UUID would turn a valid graph id into one matching
        nothing, and would send it to the wrong column in the projection."""
        graph_id = str(uuid.uuid4())

        event = (await self._submit(graph_id)).only

        self.assertEqual(event.concept_id, graph_id)

    async def test_a_title_too_long_for_the_column_is_not_dropped_silently(self):
        event = (await self._submit("Understanding " + "very " * 40 + "long topic")).only

        # The column is String(80); an overflow would fail the write and be
        # swallowed by the catch-and-log path.
        self.assertLessEqual(len(event.concept_id), 80)

    async def test_the_placeholder_is_never_recorded_as_a_concept(self):
        """`current_concept` is what the callers fall back to when they could
        not determine one. Recording against it pools unrelated work into a
        single fake row."""
        self.assertEqual((await self._submit("current_concept")).events, [])


class ClassroomTransferEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    def tearDown(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    async def _submit(self, engine, response):
        capture = _Capture()
        personalization, log = _patches(capture)
        with personalization, log:
            await engine.handle_transfer_submission(
                user_id="42",
                session_id=SESSION,
                input_component_id="input-1",
                response=response,
                response_time_ms=9000,
            )
        return capture

    async def test_a_transfer_response_is_recorded_at_the_rung_it_was_asked_for(self):
        engine = _engine()
        engine.active_scenes = {"s2": _transfer_scene()}

        event = (
            await self._submit(
                engine, "You split both into equal parts using a common denominator."
            )
        ).only

        self.assertEqual(event.evidence_type, "transfer")
        self.assertEqual(event.measurable_outcome, 1.0)
        self.assertEqual(event.source_surface, "classroom")

    async def test_the_wire_word_retrieval_is_stored_as_the_ladders_retention(self):
        engine = _engine()
        engine.active_scenes = {"s2": _transfer_scene(evidence_type="retrieval")}

        event = (
            await self._submit(
                engine, "You split both into equal parts using a common denominator."
            )
        ).only

        # The classroom keeps emitting the vocabulary it already emits; the
        # stored record uses the one word every reader shares.
        self.assertEqual(event.evidence_type, "retention")

    async def test_the_hidden_rubric_never_enters_the_learner_record(self):
        """The only per-response diagnosis this rubric produces is the list of
        expected keywords the learner missed. Those are grading internals. In
        the learner model they would sit one render away from the screen.
        """
        engine = _engine()
        engine.active_scenes = {"s2": _transfer_scene()}

        event = (await self._submit(engine, "no idea")).only

        self.assertIsNone(event.misconception)
        for keyword in ("denominator", "equal", "parts"):
            self.assertNotIn(keyword, str(event.model_dump()))

    async def test_a_response_with_no_rubric_to_score_it_records_nothing(self):
        engine = _engine()
        engine.active_scenes = {}  # no InputField to score against
        # As above: the concept is nameable from the session, so only the
        # absence of a rubric can be what stops the write.
        engine.session_contexts = {
            SESSION: SimpleNamespace(
                learning_objective="Compare fractions", lesson_index=0
            )
        }

        capture = await self._submit(engine, "a thoughtful answer")

        self.assertEqual(capture.events, [])

    async def test_an_unsuccessful_transfer_is_exposure_not_a_failed_transfer(self):
        engine = _engine()
        engine.active_scenes = {"s2": _transfer_scene()}

        event = (await self._submit(engine, "no idea")).only

        self.assertEqual(event.measurable_outcome, 0.0)
        self.assertEqual(event.evidence_type, "exposure")


if __name__ == "__main__":
    unittest.main()
