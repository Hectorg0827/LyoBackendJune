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

import json
import pytest

from lyo_app.ai_classroom.scene_lifecycle_engine import session_progress_key
from lyo_app.ai_classroom.sdui_models import ActionIntent
from tests.adaptive_fixtures import action, context, engine, seed


@pytest.fixture(autouse=True)
def clean_sessions():
    _SESSION_PROGRESS.clear()
    yield
    _SESSION_PROGRESS.clear()


async def graded_event(kind, hint_level):
    instance, ctx = engine(), context()
    component_id = seed(instance, ctx, kind, hint_level)
    log = AsyncMock()
    with patch("lyo_app.events.processor.log_learning_event", log):
        if kind == "choose":
            await instance.handle_quiz_submission("42", "fractions", component_id, "a")
        else:
            await instance.handle_transfer_submission("42", "fractions", component_id, "One half, fewer cuts.")
    return log.await_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["choose", "apply"])
async def test_both_live_graders_preserve_hint_rung_and_correctness(kind):
    unaided = await graded_event(kind, None)
    nudged = await graded_event(kind, "nudge")
    walked = await graded_event(kind, "full_example")
    assert walked.evidence_confidence < nudged.evidence_confidence < unaided.evidence_confidence
    assert nudged.hints_used == walked.hints_used == 1
    assert walked.measurable_outcome == 1.0
    assert walked.evidence_type == ("recognition" if kind == "choose" else "application")


@pytest.mark.asyncio
async def test_a_worked_example_survives_reconnect_and_damps_the_next_answer():
    instance, ctx = engine(), context()
    component_id = seed(instance, ctx)
    await instance.process_trigger(action(ActionIntent.REQUEST_EXAMPLE, component_id))
    key = session_progress_key("42", "fractions")
    serialized = json.dumps(_SESSION_PROGRESS[key]["guided_state"])
    saved = json.loads(serialized)
    assert saved["pending"]["hint_level"] == "full_example"
    assert saved["pending"]["hints_used"] == 1
    _SESSION_PROGRESS.clear()
    _SESSION_PROGRESS[key] = {"guided_state": saved}
    restored = engine(ctx)
    await restored.process_trigger(action(welcome=True))
    restored.adaptive_teacher.turn.assert_not_awaited()
    # The worked example is a paced presentation and it returns the learner to
    # the SAME checkpoint rather than swapping in a different question — so
    # walk it to its end the way tapping Continue does, then answer the
    # question that was actually asked. Typing prose at it, as this test used
    # to, only graded back when asking for an example replaced the choice
    # checkpoint with a written one.
    for _ in range(len(_SESSION_PROGRESS[key]["guided_state"].get("presentation") or []) + 1):
        if not _SESSION_PROGRESS[key]["guided_state"].get("presentation"):
            break
        await restored.process_trigger(action(ActionIntent.CONTINUE))
    pending = _SESSION_PROGRESS[key]["guided_state"]["pending"]
    assert pending["hint_level"] == "full_example", "the example is still counted after resuming"
    log = AsyncMock()
    with patch("lyo_app.events.processor.log_learning_event", log):
        await restored.process_trigger(action(ActionIntent.SUBMIT_ANSWER, pending["id"],
                                              answer_data={"selected_option_id": "a"}))
    event = log.await_args.args[1]
    # Compare against the unhelped answer, not only against the helper that
    # computed this number: asserting solely that the value equals
    # `confidence_after_hints(...)` is self-referential, and a damping function
    # that quietly returned its input unchanged would satisfy it.
    assert event.evidence_confidence < confidence_after_hints(1.0), (
        "a full worked example has to cost confidence"
    )
    assert event.evidence_confidence == confidence_after_hints(1.0, hint_level="full_example")
    assert event.hints_used == 1
