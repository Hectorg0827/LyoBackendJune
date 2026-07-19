"""Contract tests for the guided AI Classroom teaching loop."""

import unittest

from lyo_app.ai_classroom.sdui_models import ActionIntent, SceneType
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    ClassroomDirector,
    ContextSnapshot,
    Trigger,
    TriggerType,
)
from lyo_app.ai_classroom.websocket_routes import canonical_action_intent


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

    def test_learner_response_is_not_misclassified_as_a_question(self):
        self.assertEqual(
            canonical_action_intent(ActionIntent.USER_MESSAGE),
            ActionIntent.USER_MESSAGE,
        )


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

    async def test_correct_checkpoint_is_confirmed_before_advancing(self):
        decision = await self.director.decide_scene(
            self.trigger(
                ActionIntent.SUBMIT_ANSWER,
                answer_data={"is_correct": True},
            ),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.CELEBRATION)

    async def test_incorrect_checkpoint_reteaches(self):
        decision = await self.director.decide_scene(
            self.trigger(
                ActionIntent.SUBMIT_ANSWER,
                answer_data={"is_correct": False},
            ),
            self.context,
        )
        self.assertEqual(decision.selected_scene_type, SceneType.CORRECTION)

    async def test_adaptive_signals_change_the_pedagogical_move(self):
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
        self.assertEqual(stretch.selected_scene_type, SceneType.INSTRUCTION)
        self.assertGreater(stretch.difficulty_adjustment, 0)


if __name__ == "__main__":
    unittest.main()
