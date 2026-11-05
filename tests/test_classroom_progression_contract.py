"""Dependency-light checks for the classroom's saved mastery ladder.

The staging acceptance test will exercise the entire live service; these
checks isolate the deterministic server-owned transitions without importing
unrelated cloud/image integrations during a local offline build.
"""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "lyo_app/ai_classroom/adaptive_session.py"


def method(name):
    module = ast.parse(SOURCE.read_text(encoding="utf-8"), str(SOURCE))
    owner = next(node for node in module.body
                 if isinstance(node, ast.ClassDef) and node.name == "AdaptiveSession")
    selected = next(node for node in owner.body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    selected.decorator_list = []
    scope = {}
    exec(compile(ast.Module(body=[selected], type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope[name]


advance = method("after_success")
stage = method("stage")


def state():
    return SimpleNamespace(
        unit=SimpleNamespace(targets=["Identify the whole", "Partition evenly", "Compare shares"]),
        phase="guided", target_index=0, faded_targets=[], guided_targets=[],
        completed=[], skipped=[], unit_index=0, independent_application=False,
        challenge_requested=False, unresolved_misconceptions=[], diagnostic_ceiling=None,
        mode="solo", review_is_due=False,
    )


def pending(phase, target, *, extra_help=False, independent=False):
    return SimpleNamespace(
        phase=phase, task=SimpleNamespace(
            target_index=target, kind="apply" if independent else "choose",
            response_format="short_answer" if independent else "choice"),
        assisted=phase in ("guided", "faded"), extra_help_used=extra_help,
        hints_used=0,
    )


class ProgressionContract(unittest.TestCase):
    def test_three_component_skills_advance_without_repeating_first_target(self):
        current = state()
        for target in range(3):
            self.assertEqual(current.target_index, target)
            self.assertEqual(current.phase, "guided")
            self.assertFalse(advance(current, pending("guided", target)))
            self.assertEqual(current.phase, "faded")
            self.assertFalse(advance(current, pending("faded", target)))
            self.assertIn(target, current.faded_targets)

        self.assertEqual(current.faded_targets, [0, 1, 2])
        self.assertEqual(current.phase, "independent")
        self.assertFalse(advance(current, pending("independent", 2, independent=True)))
        self.assertTrue(current.independent_application)
        self.assertEqual(current.completed, [0])
        self.assertEqual(current.phase, "transfer")

    def test_assisted_faded_answer_never_awards_unearned_mastery(self):
        current = state()
        advance(current, pending("guided", 0))
        advance(current, pending("faded", 0, extra_help=True))
        self.assertEqual(current.faded_targets, [])
        self.assertEqual(current.target_index, 0)
        self.assertEqual(current.phase, "faded")

    def test_partial_progress_has_visible_stage_number_but_not_false_completion(self):
        current = state()
        current.phase = "faded"
        current.target_index = 1
        english = SimpleNamespace(copy=lambda ctx, en, es: en)
        spanish = SimpleNamespace(copy=lambda ctx, en, es: es)
        self.assertEqual(stage(english, None, current), "Finish part 2 of 3")
        self.assertEqual(stage(spanish, None, current), "Completa la parte 2 de 3")
        self.assertEqual(current.completed, [])


if __name__ == "__main__":
    unittest.main()
