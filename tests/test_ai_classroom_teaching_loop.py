"""Contract tests for the evidence-based AI Classroom teaching loop."""

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from lyo_app.ai_classroom.sdui_models import (
    ActionIntent,
    TeacherMessage,
)
from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, CriterionResult, Evaluation, GuidedState, PendingTask,
)
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    ContextAssembler,
    ContextSnapshot,
    SceneLifecycleEngine,
    Trigger,
    TriggerType,
    detect_hesitation,
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


class LiveTeachingLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from tests.adaptive_fixtures import ScriptedTeacher, context, action
        self.action = action
        self.teacher = ScriptedTeacher()
        self.context = context(target_duration_minutes=8)
        self.progress = {}
        self.runner = AdaptiveSession(self.teacher)
        await self.runner.run(self.context, self.progress, action(welcome=True))

    def state(self):
        return GuidedState.model_validate(self.progress["guided_state"])

    async def answer(self, option="a", **extra):
        pending = self.state().pending
        intent = (ActionIntent.SUBMIT_ANSWER if pending.task.response_format == "choice"
                  else ActionIntent.SUBMIT_TRANSFER)
        return await self.runner.run(self.context, self.progress, self.action(
            intent, pending.id, answer_data={"selected_option_id": option,
                                            "response": "Four equal cuts leave a longer piece.", **extra}))

    async def test_correct_tap_starts_practice_but_earns_no_credit(self):
        from tests.adaptive_fixtures import tap_probe
        opening = self.state().scene
        probe = next(c for c in opening["components"] if c["type"] == "QuizCard")
        self.assertTrue(all(o.get("is_correct") is None for o in probe["options"]))
        await tap_probe(self.runner, self.progress, self.context)
        state = self.state()
        self.assertEqual(state.phase, "guided")
        self.assertEqual(state.completed, [])
        self.assertEqual(state.outbox, [])
        self.assertTrue(any(c["type"] == "QuizCard" for c in state.scene["components"]))

    async def test_client_correctness_cannot_override_the_server_option(self):
        from tests.adaptive_fixtures import tap_probe
        await tap_probe(self.runner, self.progress, self.context)
        await self.answer(option="b", is_correct=True)
        state = self.state()
        self.assertEqual(state.completed, [])
        self.assertFalse(state.outbox[-1]["correct"])
        self.assertEqual(state.next_move, "reteach")

    async def test_transfer_is_open_and_private_until_it_is_graded(self):
        from tests.adaptive_fixtures import tap_probe
        await tap_probe(self.runner, self.progress, self.context)
        for _ in range(4):
            await self.answer()
        state = self.state()
        self.assertEqual(state.phase, "transfer")
        self.assertFalse(state.path_done)
        self.assertEqual(state.outbox[-1]["evidence_type"], "application")
        field = next(c for c in state.scene["components"] if c["type"] == "InputField")
        self.assertEqual(field["evidence_type"], "transfer")
        self.assertEqual(field["expected_keywords"], [])
        self.assertNotIn(state.pending.task.example_answer, str(state.scene))
        await self.answer(is_correct=False)
        self.assertTrue(self.state().path_done)
        self.assertEqual(self.state().outbox[-1]["evidence_type"], "transfer")

    async def test_spanish_skip_is_neutral_and_continues(self):
        from tests.adaptive_fixtures import context, advance_to_task
        self.context = context(target_duration_minutes=8, language_code="es-MX")
        self.progress = {}
        await self.runner.run(self.context, self.progress, self.action(welcome=True))
        await self.runner.run(self.context, self.progress, self.action(
            ActionIntent.SKIP_QUESTION, self.state().pending.id))
        await advance_to_task(self.runner, self.progress, self.context)
        scene = await self.runner.run(self.context, self.progress, self.action(
            ActionIntent.SKIP_QUESTION, self.state().pending.id))
        self.assertEqual(self.state().completed, [])
        self.assertEqual(self.state().outbox, [])
        self.assertTrue(self.state().path_done)
        self.assertIn("Puedes volver", " ".join(c.text for c in scene.components
                                                if isinstance(c, TeacherMessage)))

    async def test_short_transfer_uses_grounded_meaning_instead_of_keyword_counts(self):
        from tests.adaptive_fixtures import transfer_task
        response = "Four cuts; fewer divisions leave longer pieces."
        task = transfer_task()
        pending = PendingTask(task=task, speech="Apply the same principle to ribbons.",
                              board_title="Ribbons", board_content="Two identical ribbons are cut.",
                              phase="transfer")
        verdict = Evaluation(verdict="correct", confidence=0.96, question_clear=True,
            feedback="You connected equal lengths to the size of each piece.",
            criteria=[CriterionResult(index=0, met=True, quote="Four cuts"),
                      CriterionResult(index=1, met=True, quote="fewer divisions leave longer pieces")])
        generate = AsyncMock(return_value=verdict)
        result = await AdaptiveTeacher(generate).evaluate(self.context, pending, response)
        self.assertEqual(result.verdict, "correct")
        self.assertIn("Never infer missing reasoning", generate.await_args.args[0])


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


class LearnerPacingTests(unittest.IsolatedAsyncioTestCase):
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
        from tests.adaptive_fixtures import context, engine, seed
        from lyo_app.ai_classroom.scene_lifecycle_engine import session_progress_key
        _SESSION_PROGRESS.clear()
        self.context = context()
        self.engine = engine(self.context)
        self.component_id = seed(self.engine, self.context)
        self.key = session_progress_key("42", "fractions")

    async def asyncTearDown(self):
        _SESSION_PROGRESS.clear()

    async def test_skip_is_persisted_without_correctness_and_enters_review_queue(self):
        from tests.adaptive_fixtures import action
        await self.engine.process_trigger(action(ActionIntent.SKIP_QUESTION, self.component_id))
        state = _SESSION_PROGRESS[self.key]["guided_state"]
        self.assertEqual(state["skipped"], [0])
        self.assertEqual(state["completed"], [])
        self.assertEqual(state["outbox"], [])
        self.assertTrue(state["unit_done"])
        # Skipping writes no correctness, and now owes the learner a revisit:
        # the unit is queued for spaced review as a failed recall, which is a
        # second durable write and so a second persist.
        self.assertEqual(self.engine._persist_session_progress.await_count, 2)

    async def test_explicit_continue_advances_after_skip_without_marking_mastery(self):
        from tests.adaptive_fixtures import action
        await self.engine.process_trigger(action(ActionIntent.SKIP_QUESTION, self.component_id))
        await self.engine.process_trigger(action())
        state = _SESSION_PROGRESS[self.key]["guided_state"]
        self.assertEqual(state["unit_index"], 1)
        self.assertEqual(state["completed"], [])
        self.assertEqual(state["skipped"], [0])


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
            "review_concept_id": "fraction_skill_1",
            "language_code": "en-US",
        }

        await engine._persist_session_progress(trigger, context, progress)

        self.assertEqual(stored_session.context["skipped_lessons"], [1])
        self.assertEqual(stored_session.context["review_concept_id"], "fraction_skill_1")
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
