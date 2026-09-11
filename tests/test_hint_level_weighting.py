"""Help is weighed by how much of it the learner needed.

The five-rung hint ladder — nudge, principle, worked step, full example,
prerequisite — has existed in the interface and in `HINT_DAMPING` for a while.
The Classroom passed only a *count*, so being walked through a full worked
example scored exactly the same as taking one gentle nudge. Both halves of
the mechanism were built; they were not connected.

Asking for help is never failure and never demotes the rung reached. A
transfer done with a nudge is still a transfer. What changes is the
confidence attached to it, because the demonstration proves less about what
the learner can do unaided.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
from lyo_app.events.evidence import (
    HINT_DAMPING,
    confidence_after_hints,
    evidence_from_graded_answer,
    strongest_hint_level,
)

SESSION = "hint-session"
CONCEPT = "compare_fractions"


# ─── Which rung counts ───────────────────────────────────────────────────────

class StrongestHintLevelTests(unittest.TestCase):
    def test_the_most_help_wins_not_the_most_recent(self):
        """A learner who took a nudge and then a full worked example was
        walked through it."""
        self.assertEqual(
            strongest_hint_level("nudge", "full_example"), "full_example"
        )
        self.assertEqual(
            strongest_hint_level("full_example", "nudge"), "full_example"
        )

    def test_the_first_rung_is_kept_when_nothing_stronger_arrives(self):
        self.assertEqual(strongest_hint_level(None, "nudge"), "nudge")

    def test_an_unknown_rung_is_ignored_rather_than_ranked(self):
        """A new client-side rung must not silently register as the weakest
        kind of help."""
        self.assertIsNone(strongest_hint_level("vibes"))
        self.assertEqual(strongest_hint_level("worked_step", "vibes"), "worked_step")

    def test_no_help_is_no_rung(self):
        self.assertIsNone(strongest_hint_level(None, None))


# ─── What that does to the evidence ──────────────────────────────────────────

class HintDampingTests(unittest.TestCase):
    def test_a_worked_example_proves_less_than_a_nudge(self):
        nudged = evidence_from_graded_answer(correct=True, hint_level="nudge")
        walked = evidence_from_graded_answer(correct=True, hint_level="full_example")
        self.assertLess(walked["confidence"], nudged["confidence"])

    def test_the_named_rung_beats_the_bare_count(self):
        """Counting alone cannot tell three nudges from one worked example.
        Where the rung is known it decides."""
        counted = evidence_from_graded_answer(correct=True, hints_used=3)
        named = evidence_from_graded_answer(
            correct=True, hints_used=3, hint_level="full_example"
        )
        self.assertNotEqual(counted["confidence"], named["confidence"])
        self.assertEqual(
            named["confidence"], confidence_after_hints(1.0, hint_level="full_example")
        )

    def test_surfaces_that_only_count_hints_still_work(self):
        """Chat's check knows a hint was used, not which kind."""
        self.assertEqual(
            evidence_from_graded_answer(correct=True, hints_used=1)["confidence"],
            confidence_after_hints(1.0, hints_used=1),
        )

    def test_help_never_demotes_the_rung_reached(self):
        walked = evidence_from_graded_answer(
            correct=True, hint_level="prerequisite", evidence_type="transfer"
        )
        self.assertEqual(walked["kind"], "transfer")
        self.assertGreater(walked["confidence"], 0.0)

    def test_every_rung_of_the_ladder_is_priced(self):
        for rung in ("nudge", "principle", "worked_step", "full_example", "prerequisite"):
            self.assertIn(rung, HINT_DAMPING)


# ─── The classroom actually carries it ───────────────────────────────────────

def _engine():
    engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
    engine.db = MagicMock()
    engine.db.rollback = AsyncMock()
    engine.session_contexts = {
        SESSION: SimpleNamespace(learning_objective=CONCEPT, lesson_index=0)
    }
    engine.active_scenes = {}
    engine.websocket_manager = None
    engine.process_trigger = AsyncMock(return_value=MagicMock(scene_id="next"))
    return engine


def _quiz_scene():
    quiz = QuizCard(
        component_id="quiz-1",
        question="Which fraction is larger?",
        concept_id=CONCEPT,
        options=[
            QuizOption(id="a", label="1/2", is_correct=True),
            QuizOption(id="b", label="1/3", is_correct=False),
        ],
    )
    return Scene(scene_id="s1", scene_type=SceneType.CHALLENGE, components=[quiz])


def _transfer_scene():
    field = InputField(
        component_id="input-1",
        placeholder="Explain",
        question="Where else would you use a common denominator?",
        concept_id=CONCEPT,
        evidence_type="transfer",
        expected_keywords=["denominator", "equal", "parts"],
        min_words=3,
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


class ClassroomCarriesTheRungTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    def tearDown(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    async def _quiz(self, progress):
        _SESSION_PROGRESS[SESSION] = progress
        engine = _engine()
        engine.active_scenes = {"s1": _quiz_scene()}
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

    async def test_a_walked_through_answer_is_worth_less_than_an_unaided_one(self):
        unaided = await self._quiz({})
        walked = await self._quiz(
            {"hint_counts": {"0": 1}, "hint_levels": {"0": "full_example"}}
        )
        self.assertLess(walked.evidence_confidence, unaided.evidence_confidence)

    async def test_a_nudge_costs_less_than_a_worked_example(self):
        nudged = await self._quiz(
            {"hint_counts": {"0": 1}, "hint_levels": {"0": "nudge"}}
        )
        walked = await self._quiz(
            {"hint_counts": {"0": 1}, "hint_levels": {"0": "full_example"}}
        )
        self.assertLess(walked.evidence_confidence, nudged.evidence_confidence)
        # The count is identical; only the rung separates them.
        self.assertEqual(nudged.hints_used, walked.hints_used)

    async def test_help_still_leaves_a_correct_answer_correct(self):
        walked = await self._quiz(
            {"hint_counts": {"0": 2}, "hint_levels": {"0": "prerequisite"}}
        )
        self.assertEqual(walked.measurable_outcome, 1.0)
        self.assertEqual(walked.evidence_type, "recognition")

    async def test_a_transfer_response_carries_the_rung_too(self):
        _SESSION_PROGRESS[SESSION] = {
            "hint_counts": {"0": 1},
            "hint_levels": {"0": "worked_step"},
        }
        engine = _engine()
        engine.active_scenes = {"s2": _transfer_scene()}
        capture = _Capture()
        personalization, log = _patches(capture)
        with personalization, log:
            await engine.handle_transfer_submission(
                user_id="42",
                session_id=SESSION,
                input_component_id="input-1",
                response="You split both into equal parts using a common denominator.",
                response_time_ms=9000,
            )
        event = capture.only
        self.assertEqual(event.evidence_type, "transfer")
        self.assertAlmostEqual(
            event.evidence_confidence,
            confidence_after_hints(1.0, hint_level="worked_step"),
            places=6,
        )


class TheRungOutlivesTheRequestTests(unittest.IsolatedAsyncioTestCase):
    """`context` is rebuilt on every action, so a rung recorded only there is
    gone by the time the learner submits. It has to be in session progress."""

    def test_the_hint_handler_persists_the_rung(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "lyo_app" / "ai_classroom" / "scene_lifecycle_engine.py"
        ).read_text()
        self.assertIn('hint_levels = progress.setdefault("hint_levels", {})', source)
        self.assertIn("strongest_hint_level(", source)

    def test_both_graders_read_it_back(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "lyo_app" / "ai_classroom" / "scene_lifecycle_engine.py"
        ).read_text()
        # Both graders look the rung up for the question being answered...
        self.assertEqual(
            source.count('progress.get("hint_levels", {}).get(str(lesson_index))'), 2
        )
        # ...both hand it to the evidence helper, and the helper hands it on to
        # the ladder. Three call sites in total; a missing one means a grader
        # silently falls back to the bare count.
        self.assertEqual(source.count("hint_level=hint_level,"), 3)


if __name__ == "__main__":
    unittest.main()


class TheRungSurvivesARestartTests(unittest.TestCase):
    """In-memory is not where a rung can live alone.

    `_persist_session_progress` writes the durable snapshot that
    `assemble_context` rehydrates after a worker restart or a reconnect. It
    carried `hint_counts` and not `hint_levels`, so after a hydrate grading
    could see that help was taken but not which kind — and a full worked
    example scored like a nudge again, which is the whole gap this closes.
    """

    def setUp(self):
        from pathlib import Path

        self.source = (
            Path(__file__).resolve().parents[1]
            / "lyo_app" / "ai_classroom" / "scene_lifecycle_engine.py"
        ).read_text()

    def test_the_durable_snapshot_carries_the_rung(self):
        start = self.source.index('"hint_counts": dict(progress.get("hint_counts", {})),')
        window = self.source[start : start + 700]
        self.assertIn('"hint_levels": dict(progress.get("hint_levels", {}))', window)

    def test_it_is_written_beside_the_count_it_qualifies(self):
        """Separating them is how they drift: one persisted, one not."""
        self.assertEqual(
            self.source.count('"hint_counts": dict(progress.get("hint_counts", {})),'),
            self.source.count('"hint_levels": dict(progress.get("hint_levels", {})),'),
        )
