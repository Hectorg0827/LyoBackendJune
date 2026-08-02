"""Contract tests for the evidence-based AI Classroom teaching loop."""

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from lyo_app.ai_classroom.sdui_models import (
    ActionIntent,
    ClassroomMode,
    HintLevel,
    InputField,
    TeacherMessage,
    ExampleBlock,
    CTAButton,
    SceneType,
)
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    ClassroomDirector,
    ContextAssembler,
    ContextSnapshot,
    SceneCompiler,
    SceneLifecycleEngine,
    Trigger,
    TriggerType,
    describe_transfer_gap,
    detect_hesitation,
    expected_transfer_keywords,
    score_transfer_response,
    _SESSION_PROGRESS,
)
from lyo_app.ai_classroom.websocket_routes import canonical_action_intent
from lyo_app.personalization.schemas import KnowledgeTraceRequest
from lyo_app.personalization.service import PersonalizationEngine


class ClassroomActionContractTests(unittest.TestCase):
    def test_legacy_clients_map_to_canonical_teaching_actions(self):
        self.assertEqual(
            canonical_action_intent(ActionIntent.QUIZ_ANSWER),
            ActionIntent.SUBMIT_ANSWER,
        )
        self.assertEqual(
            canonical_action_intent(ActionIntent.CONFUSED),
            ActionIntent.REQUEST_HINT,
        )
        self.assertEqual(
            canonical_action_intent(ActionIntent.TOO_EASY),
            ActionIntent.SKIP_AHEAD,
        )

    def test_new_evidence_and_mode_intents_are_canonical(self):
        self.assertEqual(
            canonical_action_intent(ActionIntent.SUBMIT_TRANSFER),
            ActionIntent.SUBMIT_TRANSFER,
        )
        self.assertEqual(
            canonical_action_intent(ActionIntent.SET_MODE),
            ActionIntent.SET_MODE,
        )
        self.assertEqual(
            canonical_action_intent(ActionIntent.SKIP_QUESTION),
            ActionIntent.SKIP_QUESTION,
        )

    def test_transfer_input_carries_a_transparent_server_rubric(self):
        field = InputField(
            question="Apply proportional reasoning to a new recipe.",
            placeholder="Explain your example",
            concept_id="proportional reasoning",
            expected_keywords=["ratio", "scale"],
        )
        self.assertEqual(field.action_intent, ActionIntent.SUBMIT_TRANSFER.value)
        self.assertEqual(field.evidence_type, "transfer")
        self.assertGreater(field.min_words, 1)

    def test_neutral_legacy_events_are_valid_analytics_evidence(self):
        from lyo_app.classroom.analytics import LyoAnalyticsEvent

        skipped = LyoAnalyticsEvent(
            event_type="check_skipped",
            card_id="fractions-check",
            topic="Compare fractions",
        )
        helped = LyoAnalyticsEvent(
            event_type="help_requested",
            card_id="fractions-check",
            topic="Compare fractions",
        )

        self.assertIsNone(skipped.is_correct)
        self.assertIsNone(helped.is_correct)

    def test_legacy_stream_never_advances_on_silence(self):
        from lyo_app.classroom.routes import websocket_lesson_stream

        source = inspect.getsource(websocket_lesson_stream)
        self.assertNotIn("asyncio.wait_for", source)
        self.assertIn("intent in ADVANCE_INTENTS", source)


class TransferEvidenceTests(unittest.TestCase):
    def test_substantive_application_with_rubric_language_passes(self):
        correct, coverage, missing = score_transfer_response(
            "I use the ratio to scale every ingredient by the same factor.",
            ["ratio", "scale", "factor"],
            min_words=6,
            min_score=0.25,
        )
        self.assertTrue(correct)
        self.assertGreaterEqual(coverage, 2 / 3)
        self.assertEqual(missing, ["factor"] if coverage < 1 else [])

    def test_short_or_unrelated_response_fails(self):
        correct, coverage, missing = score_transfer_response(
            "I get it.",
            ["ratio", "scale"],
            min_words=6,
            min_score=0.25,
        )
        self.assertFalse(correct)
        self.assertEqual(coverage, 0)
        self.assertEqual(missing, ["ratio", "scale"])

    def test_keywords_come_from_authored_objective_and_content(self):
        keywords = expected_transfer_keywords(
            "Compare fractions with unlike denominators",
            "Use a common denominator before comparing numerators.",
        )
        self.assertIn("fractions", keywords)
        self.assertIn("denominators", keywords)


class RubricLeakRegressionTests(unittest.TestCase):
    """Guards the fix for the internal rubric bleeding into visible chat.

    `handle_transfer_submission` used to build learner-facing feedback by
    joining the Evaluator's raw `missing` keyword list directly into text
    (e.g. "Add the missing reasoning link around ratio, scale"), handing the
    learner the exact words the grader was scoring for. `describe_transfer_gap`
    replaces that: it must describe the *category* of gap without ever
    quoting a rubric keyword.
    """

    def test_gap_description_never_quotes_rubric_keywords(self):
        keywords = ["ratio", "scale", "factor"]
        _correct, coverage, missing = score_transfer_response(
            "I get it.", keywords, min_words=6, min_score=0.25,
        )
        self.assertEqual(missing, keywords)  # sanity: evaluator did find gaps

        hint = describe_transfer_gap("I get it.", min_words=6, coverage=coverage, min_score=0.25)
        for keyword in keywords:
            self.assertNotIn(keyword, hint.lower())

    def test_gap_description_distinguishes_short_from_off_target(self):
        too_short = describe_transfer_gap("I get it.", min_words=6, coverage=0.0, min_score=0.25)
        off_target = describe_transfer_gap(
            "I followed the steps and got an answer that felt right to me.",
            min_words=6,
            coverage=0.1,
            min_score=0.25,
        )
        self.assertNotEqual(too_short, off_target)
        self.assertIn("more", too_short.lower())


class HesitationClassifierTests(unittest.TestCase):
    def test_detects_common_hesitation_phrases(self):
        for phrase in ["idk", "I'm not sure", "no idea", "I don't know", "can you help?", "I'm stuck"]:
            with self.subTest(phrase=phrase):
                self.assertTrue(detect_hesitation(phrase))

    def test_does_not_flag_substantive_answers(self):
        self.assertFalse(
            detect_hesitation(
                "I use the ratio to scale every ingredient by the same factor."
            )
        )

    def test_empty_or_missing_text_is_not_hesitant(self):
        self.assertFalse(detect_hesitation(None))
        self.assertFalse(detect_hesitation(""))
        self.assertFalse(detect_hesitation("   "))


class SpacedRetrievalContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_trace_normalizes_json_user_id_for_mastery_and_schedule(self):
        engine = PersonalizationEngine()
        engine.dkt.get_skill_readiness = AsyncMock(return_value=(0.2, 0.8))
        engine.dkt.update_mastery = AsyncMock(return_value=0.4)
        engine._update_repetition_schedule = AsyncMock()
        db = object()
        await engine.trace_knowledge(
            db,
            KnowledgeTraceRequest(
                learner_id="42",
                skill_id="fractions",
                item_id="compare fractions",
                correct=True,
                time_taken_seconds=8,
            ),
        )
        engine.dkt.update_mastery.assert_awaited_once()
        self.assertEqual(engine.dkt.update_mastery.await_args.args[1], 42)
        self.assertEqual(engine._update_repetition_schedule.await_args.args[1], 42)


class ClassroomDirectorTeachingLoopTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.director = ClassroomDirector()
        self.context = ContextSnapshot(
            user_id="42",
            session_id="course-1",
            topic="Fractions",
            learning_objective="Compare fractions with unlike denominators",
        )

    def trigger(self, action_intent, **action_data):
        return Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id="42",
            session_id="course-1",
            action_data={"action_intent": action_intent, **action_data},
        )

    async def test_continue_checks_understanding_before_advancing(self):
        decision = await self.director.decide_scene(
            self.trigger(ActionIntent.CONTINUE),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.CHALLENGE)
        self.assertTrue(decision.require_interaction)

    async def test_mastered_checkpoint_advances_to_instruction(self):
        decision = await self.director.decide_scene(
            self.trigger(ActionIntent.CONTINUE, advanced_after_mastery=True),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.INSTRUCTION)

    async def test_correct_recognition_requires_transfer_evidence(self):
        decision = await self.director.decide_scene(
            self.trigger(
                ActionIntent.SUBMIT_ANSWER,
                answer_data={"is_correct": True},
            ),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.REFLECTION)
        self.assertTrue(decision.require_interaction)

    async def test_correct_transfer_confirms_mastery(self):
        decision = await self.director.decide_scene(
            self.trigger(
                ActionIntent.SUBMIT_TRANSFER,
                answer_data={"is_correct": True},
            ),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.CELEBRATION)

    async def test_incorrect_evidence_reteaches(self):
        recognition = await self.director.decide_scene(
            self.trigger(
                ActionIntent.SUBMIT_ANSWER,
                answer_data={"is_correct": False},
            ),
            self.context,
        )
        transfer = await self.director.decide_scene(
            self.trigger(
                ActionIntent.SUBMIT_TRANSFER,
                answer_data={"is_correct": False},
            ),
            self.context,
        )
        self.assertEqual(recognition.selected_scene_type, SceneType.CORRECTION)
        self.assertEqual(transfer.selected_scene_type, SceneType.CORRECTION)
        self.assertTrue(transfer.require_interaction)

    async def test_hint_ladder_and_challenge_mode_change_the_move(self):
        self.context.hint_level = HintLevel.NUDGE
        hint = await self.director.decide_scene(
            self.trigger(ActionIntent.REQUEST_HINT),
            self.context,
        )
        stretch = await self.director.decide_scene(
            self.trigger(ActionIntent.SKIP_AHEAD),
            self.context,
        )
        self.assertEqual(hint.selected_scene_type, SceneType.INSTRUCTION)
        self.assertLess(hint.difficulty_adjustment, 0)
        self.assertGreater(stretch.difficulty_adjustment, 0)

    async def test_skip_is_neutral_and_waits_for_explicit_continuation(self):
        self.context.learner_signal = ActionIntent.SKIP_QUESTION.value
        decision = await self.director.decide_scene(
            self.trigger(ActionIntent.SKIP_QUESTION),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.INSTRUCTION)
        self.assertTrue(decision.require_interaction)

    async def test_hesitant_signal_shifts_from_assessment_to_scaffolding(self):
        # A hesitant transfer submission would normally score as incorrect
        # and fall into CORRECTION (which surfaces rubric-derived feedback).
        # The hesitant state must pre-empt that and route to a plain
        # scaffolding INSTRUCTION scene instead.
        self.context.learner_signal = "hesitant"
        decision = await self.director.decide_scene(
            self.trigger(
                ActionIntent.SUBMIT_TRANSFER,
                answer_data={"is_correct": False, "hesitant": True},
            ),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.INSTRUCTION)
        self.assertNotEqual(decision.selected_scene_type, SceneType.CORRECTION)

    async def test_hesitant_signal_overrides_frustration_correction(self):
        # Even with repeated consecutive failures (which would otherwise force
        # CORRECTION), a hesitant learner still gets scaffolding, not a
        # rubric-based correction.
        self.context.learner_signal = "hesitant"
        self.context.frustration.frustration_score = 0.9
        self.context.frustration.consecutive_failures = 5
        decision = await self.director.decide_scene(
            self.trigger(
                ActionIntent.SUBMIT_TRANSFER,
                answer_data={"is_correct": False, "hesitant": True},
            ),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.INSTRUCTION)

    async def test_review_mode_opens_with_due_retrieval(self):
        self.context.classroom_mode = ClassroomMode.REVIEW
        self.context.review_due_items = ["fraction comparison"]
        decision = await self.director.decide_scene(
            Trigger(
                trigger_type=TriggerType.SYSTEM_TIMEOUT,
                user_id="42",
                session_id="course-1",
            ),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.CHALLENGE)


class LearnerGatedTeachingBeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_instruction_is_one_short_teacher_turn_then_a_checkpoint(self):
        compiler = SceneCompiler(ai_service=None)
        context = ContextSnapshot(
            user_id="42",
            session_id="spanish-course",
            topic="Fracciones",
            lesson_title="Comparar fracciones",
            lesson_content=(
                "Para comparar fracciones con denominadores distintos, "
                "primero usa un denominador común."
            ),
            learning_objective="Comparar fracciones",
            language_code="es-US",
        )

        components = await compiler._create_instruction_components(context)
        teacher_messages = [
            component for component in components
            if isinstance(component, TeacherMessage)
        ]

        self.assertEqual(len(teacher_messages), 1)
        self.assertLessEqual(len(teacher_messages[0].text.split()), 55)
        self.assertFalse(teacher_messages[0].text.lstrip().startswith("["))
        self.assertEqual(teacher_messages[0].language_code, "es-US")
        self.assertTrue(any(isinstance(c, ExampleBlock) for c in components))
        self.assertIsInstance(components[-1], CTAButton)
        self.assertEqual(components[-1].action_intent, ActionIntent.CONTINUE.value)
        self.assertEqual(components[-1].delay_ms, 0)

    async def test_spanish_skip_copy_is_neutral_and_creates_no_fake_answer(self):
        compiler = SceneCompiler(ai_service=None)
        context = ContextSnapshot(
            user_id="42",
            session_id="spanish-course",
            topic="Fracciones",
            learning_objective="Comparar fracciones",
            language_code="es-MX",
            learner_signal=ActionIntent.SKIP_QUESTION.value,
        )

        components = await compiler._create_instruction_components(context)

        self.assertEqual(len(components), 2)
        self.assertIsInstance(components[0], TeacherMessage)
        self.assertIn("no cuenta como error", components[0].text)
        self.assertIsInstance(components[1], CTAButton)
        self.assertEqual(components[1].action_intent, ActionIntent.CONTINUE.value)

    async def test_user_action_never_schedules_unattended_continuation(self):
        engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
        engine.trigger_listener = MagicMock()
        engine.process_trigger = AsyncMock()
        trigger = Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id="42",
            session_id="course-1",
            action_data={"action_intent": ActionIntent.CONTINUE},
        )

        await engine._handle_user_action_trigger(trigger)

        engine.trigger_listener.cancel_timeout.assert_called_once_with("course-1")
        engine.trigger_listener.schedule_timeout.assert_not_called()
        engine.process_trigger.assert_awaited_once_with(trigger)


class DurableSkipTeachingLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session_id = "skip-contract-course"
        _SESSION_PROGRESS.pop(self.session_id, None)
        self.context = ContextSnapshot(
            user_id="42",
            session_id=self.session_id,
            topic="Fractions",
            course_id="7",
            lesson_index=0,
            lesson_title="Compare fractions",
            lesson_content="Use a common denominator.",
            total_lessons=2,
            learning_objective="Compare fractions",
            language_code="en-US",
        )
        self.engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
        self.engine.context_assembler = MagicMock()
        self.engine.context_assembler.assemble_context = AsyncMock(
            return_value=self.context
        )
        self.engine.context_assembler._resolve_current_lesson = AsyncMock(
            return_value=("lesson-2", 1, "Add fractions", "Add equal parts.", 2)
        )
        self.engine.director = ClassroomDirector()
        self.engine.compiler = SceneCompiler(ai_service=None)
        self.engine.session_contexts = {}
        self.engine.session_lesson_indices = {}
        self.engine.active_scenes = {}
        self.engine.websocket_manager = None
        self.engine._persist_session_progress = AsyncMock()

    async def asyncTearDown(self):
        _SESSION_PROGRESS.pop(self.session_id, None)

    async def test_skip_is_persisted_without_correctness_and_enters_review_queue(self):
        trigger = Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id="42",
            session_id=self.session_id,
            component_id="quiz-1",
            action_data={"action_intent": ActionIntent.SKIP_QUESTION},
        )

        await self.engine.process_trigger(trigger)

        progress = _SESSION_PROGRESS[self.session_id]
        self.assertEqual(progress["evidence"]["0"]["status"], "skipped")
        self.assertFalse(progress["evidence"]["0"]["recognition"])
        self.assertFalse(progress["evidence"]["0"]["transfer"])
        self.assertEqual(progress["skipped_lessons"], [0])
        self.assertEqual(progress["review_queue"][0]["lesson_index"], 0)
        self.assertIsNone(progress["attempt_history"][-1]["is_correct"])
        self.engine._persist_session_progress.assert_awaited_once()

    async def test_explicit_continue_advances_after_skip_without_marking_mastery(self):
        _SESSION_PROGRESS[self.session_id] = {
            "scene": 0,
            "covered": [],
            "mastered_lessons": [],
            "skipped_lessons": [0],
            "review_queue": [{
                "lesson_index": 0,
                "lesson_title": "Compare fractions",
                "objective": "Compare fractions",
            }],
        }
        trigger = Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id="42",
            session_id=self.session_id,
            action_data={"action_intent": ActionIntent.CONTINUE},
        )

        scene = await self.engine.process_trigger(trigger)

        progress = _SESSION_PROGRESS[self.session_id]
        self.assertEqual(progress["current_lesson_index"], 1)
        self.assertEqual(progress["mastered_lessons"], [])
        self.assertEqual(scene.scene_type, SceneType.INSTRUCTION)


class ClassroomPersistenceContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_skip_writes_durable_context_and_neutral_interaction(self):
        from lyo_app.classroom.models import ClassroomInteraction

        stored_session = SimpleNamespace(
            id=91,
            context={},
            subject=None,
            is_active=True,
            updated_at=None,
            ended_at=None,
        )
        scalar_result = MagicMock()
        scalar_result.scalars.return_value.first.return_value = stored_session
        db = MagicMock()
        db.execute = AsyncMock(return_value=scalar_result)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
        engine.db = db
        trigger = Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id="42",
            session_id="course-7",
            component_id="quiz-7",
            action_data={"action_intent": ActionIntent.SKIP_QUESTION},
        )
        context = ContextSnapshot(
            user_id="42",
            session_id="course-7",
            course_id="7",
            lesson_id="lesson-2",
            lesson_index=1,
            lesson_title="Compare fractions",
            learning_objective="Compare fractions",
            language_code="en-US",
        )
        progress = {
            "current_lesson_index": 1,
            "mastered_lessons": [],
            "skipped_lessons": [1],
            "evidence": {
                "1": {"recognition": False, "transfer": False, "status": "skipped"}
            },
            "attempt_history": [{"intent": "skip_question", "is_correct": None}],
            "review_queue": [{"lesson_index": 1, "objective": "Compare fractions"}],
            "language_code": "en-US",
        }

        await engine._persist_session_progress(trigger, context, progress)

        self.assertEqual(stored_session.context["skipped_lessons"], [1])
        self.assertEqual(stored_session.context["review_queue"][0]["lesson_index"], 1)
        self.assertIsNone(stored_session.context["attempt_history"][0]["is_correct"])
        interaction = next(
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], ClassroomInteraction)
        )
        self.assertEqual(interaction.event_type, ActionIntent.SKIP_QUESTION.value)
        self.assertIsNone(interaction.is_correct)
        self.assertEqual(interaction.card_id, "quiz-7")
        db.commit.assert_awaited_once()


class ClassroomLessonIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_requested_lesson_id_resolves_authored_lesson_and_cursor(self):
        lesson_row = SimpleNamespace(
            id=31,
            order_index=2,
            title="Equivalent fractions",
            content="Multiply numerator and denominator by the same number.",
            description=None,
            topic="Fractions",
        )
        lesson_result = MagicMock()
        lesson_result.first.return_value = lesson_row
        count_result = MagicMock()
        count_result.scalar.return_value = 4
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[lesson_result, count_result])

        resolved = await ContextAssembler(db)._resolve_current_lesson(
            "7",
            0,
            requested_lesson_id="31",
        )

        self.assertEqual(resolved[0], "31")
        self.assertEqual(resolved[1], 2)
        self.assertEqual(resolved[2], "Equivalent fractions")
        self.assertEqual(resolved[4], 4)


if __name__ == "__main__":
    unittest.main()
