"""Test Prep teaches, grades, and lands in the learner's record.

WHAT WAS ACTUALLY WRONG

It is tempting to describe the old behaviour as "Test Prep did not log
evidence". That is not quite it, and the difference decides the fix.

Test Prep gathered subject, topics and date, appended them to the request
text, and handed off to the prose planner. Only `Intent.EXPLAIN` reached
`_try_compose_lesson`, the one path that produces a server-gradeable check.
So there was nothing to log — not because a logging call was missing, but
because a learner could work through an entire test-prep session without
being asked a single question the server could mark.

Adding `source_surface="test_prep"` to a logging call would have been
pointless: there was no grading call site to attach it to.
"""

import unittest

from lyo_app.api.v1.stream_lyo2 import (
    _lesson_to_smart_blocks,
    _preferred_prep_topic,
    _surface_of,
)
from lyo_app.events.evidence import SOURCE_SURFACES


class _Option:
    def __init__(self, text, reveals=None):
        self.text = text
        self.reveals = reveals


class _Check:
    question = "Which stage produces the most ATP?"
    correct_index = 0
    explanation = "Oxidative phosphorylation."
    hint = None
    bailout_index = None
    options = [_Option("Oxidative phosphorylation"), _Option("Glycolysis", "counts_only_glycolysis")]


class _Lesson:
    skill_id = "cellular_respiration"
    is_probe = False
    sections = []
    check = _Check()


def _check_block(source_surface):
    blocks = _lesson_to_smart_blocks(_Lesson(), source_surface=source_surface)
    return next(b for b in blocks if b.get("metadata"))


# ─── What to teach for an upcoming test ──────────────────────────────────────

class PreferredTopicTests(unittest.TestCase):
    def test_a_named_topic_beats_the_subject_heading(self):
        """"Biology" is a shelf; "cellular respiration" is a lesson."""
        self.assertEqual(
            _preferred_prep_topic("Biology", ["cellular respiration", "genetics"]),
            "cellular respiration",
        )

    def test_the_subject_is_used_when_no_topic_was_named(self):
        self.assertEqual(_preferred_prep_topic("Biology", []), "Biology")

    def test_blank_topics_are_not_mistaken_for_topics(self):
        self.assertEqual(_preferred_prep_topic("Biology", ["", "   "]), "Biology")

    def test_nothing_to_teach_returns_nothing(self):
        """The caller then leaves Test Prep on the prose path rather than
        composing a lesson about nothing."""
        self.assertEqual(_preferred_prep_topic(None, None), "")
        self.assertEqual(_preferred_prep_topic("  ", [" "]), "")


# ─── The block remembers which surface asked ─────────────────────────────────

class CheckProvenanceTests(unittest.TestCase):
    def test_a_test_prep_check_is_marked_as_test_prep(self):
        self.assertEqual(
            _check_block("test_prep")["metadata"]["source_surface"], "test_prep"
        )

    def test_a_chat_check_is_still_marked_as_chat(self):
        self.assertEqual(_check_block("chat")["metadata"]["source_surface"], "chat")

    def test_the_skill_id_still_rides_along(self):
        """Grading needs it to know which mastery row to update; adding the
        surface must not displace it."""
        self.assertEqual(
            _check_block("test_prep")["metadata"]["skill_id"], "cellular_respiration"
        )

    def test_test_prep_is_a_surface_the_ladder_recognises(self):
        self.assertIn("test_prep", SOURCE_SURFACES)


# ─── Reading it back at grading time ─────────────────────────────────────────

class SurfaceOfTests(unittest.TestCase):
    def test_the_stored_surface_is_what_grading_reports(self):
        self.assertEqual(_surface_of(_check_block("test_prep")), "test_prep")

    def test_a_block_from_before_this_field_existed_reads_as_chat(self):
        """Every lesson block was composed by chat until Test Prep started
        composing its own, so that is the honest default — not a guess."""
        self.assertEqual(_surface_of({"metadata": {"skill_id": "x"}}), "chat")
        self.assertEqual(_surface_of({}), "chat")
        self.assertEqual(_surface_of(None), "chat")

    def test_an_unrecognised_surface_is_not_taken_at_face_value(self):
        """The value is read back off a stored block. An unknown surface is
        recorded as chat rather than written into the learner's history as
        something no reader understands."""
        self.assertEqual(_surface_of({"metadata": {"source_surface": "vibes"}}), "chat")
        self.assertEqual(_surface_of({"metadata": {"source_surface": None}}), "chat")


# ─── The route is actually wired ─────────────────────────────────────────────

class GradingUsesTheStoredSurfaceTests(unittest.TestCase):
    """`_surface_of` behaving correctly is worth nothing if the endpoint that
    records the verdict does not call it. It hardcoded "chat" before."""

    def test_the_check_endpoint_labels_evidence_from_the_block(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "lyo_app" / "api" / "v1" / "stream_lyo2.py"
        ).read_text()
        body = source[source.index("async def check_lyo2_answer"):]
        if "\nasync def " in body[1:]:
            body = body[: body.index("\nasync def ", 1)]

        self.assertIn("source_surface=_surface_of(block)", body)
        self.assertNotIn('source_surface="chat"', body)


class EmitterPersistsSoTheCheckStaysGradeableTests(unittest.IsolatedAsyncioTestCase):
    """Grading happens on a later request that has only the stored blocks to
    work from. A surface that streamed a lesson without persisting its blocks
    would show the learner a question nobody could mark."""

    async def test_the_lesson_blocks_are_written_to_the_conversation(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        import lyo_app.api.v1.stream_lyo2 as mod

        lesson = MagicMock()
        lesson.to_plain_text.return_value = "Respiration, taught."
        lesson.next_directions = []
        blocks = _lesson_to_smart_blocks(_Lesson(), source_surface="test_prep")
        conversation = MagicMock(id=7)
        store = MagicMock()
        store.add_message = AsyncMock()

        with patch.object(mod, "conversation_store", store):
            events = [
                event
                async for event in mod._emit_composed_lesson(
                    MagicMock(), lesson, blocks, [], conversation, "cid", "test_prep"
                )
            ]

        store.add_message.assert_awaited_once()
        persisted = store.add_message.await_args.kwargs["blocks"]
        self.assertEqual(persisted, blocks)
        self.assertTrue(any("smart_blocks" in e for e in events))


class TestPrepReachesTheComposerTests(unittest.TestCase):
    """`_try_compose_lesson` is the only path that produces a gradeable
    check. Asserting the helpers behave proves nothing if Test Prep never
    calls it, which was the entire bug."""

    def setUp(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "lyo_app" / "api" / "v1" / "stream_lyo2.py"
        ).read_text()
        marker = "if decision.intent == Intent.TEST_PREP:"
        self.branch = source[source.index(marker):]
        self.branch = self.branch[: self.branch.index("# 2c. Structured teaching path.")]

    def test_test_prep_composes_a_lesson(self):
        # The bound await, not the bare name: a call left in the source but
        # short-circuited out of the live path would still contain the name.
        self.assertIn(
            "prep_blocks, prep_lesson = await _try_compose_lesson(", self.branch
        )

    def test_it_composes_under_the_test_prep_surface(self):
        self.assertIn('source_surface="test_prep"', self.branch)

    def test_it_uses_the_structured_topic_not_the_raw_sentence(self):
        self.assertIn("_preferred_prep_topic(", self.branch)

    def test_it_streams_through_the_shared_emitter(self):
        """The emitter persists the blocks. A surface that streamed its own
        shape without persisting would leave its check ungradeable on the
        next request."""
        self.assertIn("_emit_composed_lesson(", self.branch)

    def test_a_failure_to_compose_falls_through_rather_than_dead_ending(self):
        self.assertIn("falling back to prose path", self.branch)


if __name__ == "__main__":
    unittest.main()
