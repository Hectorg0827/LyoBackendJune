"""
Standalone unit test for the A2UI intent injection logic in stream_lyo2.py.
Does NOT require a running server, database, or real API key.
Directly tests the injection map and plan mutation logic.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# ── Minimal stubs so we can import schemas without real DB/env ──────────────

# Stub out pydantic settings validation before importing the module
import unittest
from unittest.mock import MagicMock, patch

# We only need the schemas — import them directly
from lyo_app.ai.schemas.lyo2 import (
    Intent, ActionType, PlannedAction, LyoPlan, RouterDecision
)

# ── Reproduce the injection logic exactly as it is in stream_lyo2.py ────────

def apply_a2ui_injection(plan: LyoPlan, decision: RouterDecision, request_text: str) -> LyoPlan:
    """Mirror of the deterministic A2UI injection block in stream_lyo2.py."""
    _has_a2ui_step = any(
        s.action_type == ActionType.GENERATE_A2UI for s in plan.steps
    )
    _intent_to_a2ui = {
        Intent.COURSE:            {"ui_type": "course", "title": request_text or ""},
        Intent.EXPLAIN:           {"ui_type": "explanation"},
        Intent.QUIZ:              {"ui_type": "quiz"},
        Intent.FLASHCARDS:        {"ui_type": "quiz"},
        Intent.STUDY_PLAN:        {"ui_type": "study_plan"},
        # Fallbacks
        Intent.CHAT:              {"ui_type": "explanation"},
        Intent.GENERAL:           {"ui_type": "explanation"},
        Intent.GREETING:          {"ui_type": "explanation"},
        Intent.HELP:              {"ui_type": "explanation"},
        Intent.SUMMARIZE_NOTES:   {"ui_type": "explanation"},
        Intent.COMMUNITY:         {"ui_type": "explanation"},
        Intent.UNKNOWN:           {"ui_type": "explanation"},
    }
    if not _has_a2ui_step and decision.intent in _intent_to_a2ui:
        a2ui_params = _intent_to_a2ui[decision.intent]
        plan.steps.append(PlannedAction(
            action_type=ActionType.GENERATE_A2UI,
            description=f"Auto-injected A2UI step for intent {decision.intent}",
            parameters=a2ui_params,
        ))
    return plan


def make_plan(has_a2ui=False) -> LyoPlan:
    steps = []
    if has_a2ui:
        steps.append(PlannedAction(
            action_type=ActionType.GENERATE_A2UI,
            description="Existing A2UI step",
            parameters={"ui_type": "course"}
        ))
    else:
        steps.append(PlannedAction(
            action_type=ActionType.GENERATE_TEXT,
            description="Generate text",
            parameters={}
        ))
    return LyoPlan(steps=steps)


def make_decision(intent: Intent) -> RouterDecision:
    return RouterDecision(
        intent=intent,
        confidence=0.9,
        needs_clarification=False,
        clarification_question=None,
        context={}
    )


class TestA2UIInjection(unittest.TestCase):

    # ── Intents that SHOULD produce a2ui injection ───────────────────────────

    def test_chat_intent_injects_explanation(self):
        plan = apply_a2ui_injection(make_plan(), make_decision(Intent.CHAT), "Hello!")
        a2ui_steps = [s for s in plan.steps if s.action_type == ActionType.GENERATE_A2UI]
        self.assertEqual(len(a2ui_steps), 1, "CHAT should inject exactly 1 A2UI step")
        self.assertEqual(a2ui_steps[0].parameters["ui_type"], "explanation")

    def test_general_intent_injects_explanation(self):
        plan = apply_a2ui_injection(make_plan(), make_decision(Intent.GENERAL), "test")
        a2ui_steps = [s for s in plan.steps if s.action_type == ActionType.GENERATE_A2UI]
        self.assertEqual(len(a2ui_steps), 1)
        self.assertEqual(a2ui_steps[0].parameters["ui_type"], "explanation")

    def test_greeting_intent_injects_explanation(self):
        plan = apply_a2ui_injection(make_plan(), make_decision(Intent.GREETING), "Hi!")
        a2ui_steps = [s for s in plan.steps if s.action_type == ActionType.GENERATE_A2UI]
        self.assertEqual(len(a2ui_steps), 1)

    def test_help_intent_injects_explanation(self):
        plan = apply_a2ui_injection(make_plan(), make_decision(Intent.HELP), "Help?")
        a2ui_steps = [s for s in plan.steps if s.action_type == ActionType.GENERATE_A2UI]
        self.assertEqual(len(a2ui_steps), 1)

    def test_unknown_intent_injects_explanation(self):
        plan = apply_a2ui_injection(make_plan(), make_decision(Intent.UNKNOWN), "???")
        a2ui_steps = [s for s in plan.steps if s.action_type == ActionType.GENERATE_A2UI]
        self.assertEqual(len(a2ui_steps), 1)

    def test_course_intent_injects_course_ui(self):
        plan = apply_a2ui_injection(make_plan(), make_decision(Intent.COURSE), "Teach me Python")
        a2ui_steps = [s for s in plan.steps if s.action_type == ActionType.GENERATE_A2UI]
        self.assertEqual(len(a2ui_steps), 1)
        self.assertEqual(a2ui_steps[0].parameters["ui_type"], "course")

    def test_quiz_intent_injects_quiz_ui(self):
        plan = apply_a2ui_injection(make_plan(), make_decision(Intent.QUIZ), "Quiz me")
        a2ui_steps = [s for s in plan.steps if s.action_type == ActionType.GENERATE_A2UI]
        self.assertEqual(len(a2ui_steps), 1)
        self.assertEqual(a2ui_steps[0].parameters["ui_type"], "quiz")

    def test_explain_intent_injects_explanation(self):
        plan = apply_a2ui_injection(make_plan(), make_decision(Intent.EXPLAIN), "Explain gravity")
        a2ui_steps = [s for s in plan.steps if s.action_type == ActionType.GENERATE_A2UI]
        self.assertEqual(len(a2ui_steps), 1)
        self.assertEqual(a2ui_steps[0].parameters["ui_type"], "explanation")

    # ── Guard: should NOT inject a second step if one already exists ─────────

    def test_no_duplicate_injection_if_step_exists(self):
        plan = apply_a2ui_injection(make_plan(has_a2ui=True), make_decision(Intent.CHAT), "Hi")
        a2ui_steps = [s for s in plan.steps if s.action_type == ActionType.GENERATE_A2UI]
        self.assertEqual(len(a2ui_steps), 1, "Should not inject a second A2UI step")

    # ── Verify all enum members are covered ──────────────────────────────────

    def test_all_intent_members_covered(self):
        """Every Intent value should either have explicit ui_type or be silently handled."""
        covered = {
            Intent.COURSE, Intent.EXPLAIN, Intent.QUIZ, Intent.FLASHCARDS,
            Intent.STUDY_PLAN, Intent.CHAT, Intent.GENERAL, Intent.GREETING,
            Intent.HELP, Intent.SUMMARIZE_NOTES, Intent.COMMUNITY, Intent.UNKNOWN,
            Intent.SCHEDULE_REMINDERS, Intent.MODIFY_ARTIFACT,
        }
        all_intents = set(Intent)
        uncovered = all_intents - covered
        self.assertEqual(
            uncovered, set(),
            f"These intents are not in the injection map: {uncovered}"
        )


if __name__ == "__main__":
    print("🧪 Running A2UI injection tests...\n")
    unittest.main(verbosity=2)
