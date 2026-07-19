"""Contract tests for the evidence-based AI Classroom teaching loop."""

import unittest
from unittest.mock import AsyncMock

from lyo_app.ai_classroom.sdui_models import (
    ActionIntent,
    ClassroomMode,
    HintLevel,
    InputField,
    SceneType,
)
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    ClassroomDirector,
    ContextSnapshot,
    Trigger,
    TriggerType,
    expected_transfer_keywords,
    score_transfer_response,
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


if __name__ == "__main__":
    unittest.main()
