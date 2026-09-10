"""Grading internals do not travel with the question.

The product's trust rules are explicit: never expose answer keys before
submission, internal expected keywords, or hidden rubrics.

Chat's check block was breaking that. `correct_index` and `explanation` were
serialised into the block and streamed alongside the question, and every
option carried `reveals` — the misconception tag naming what choosing it
would say about the learner.

The client is careful not to grade with them; `CheckBlock.tsx` even carries a
comment saying so. That is not a defence. A learner with the network tab open
could read the answer before choosing, and the misconception tags are internal
diagnosis nobody should be reading about themselves mid-question.
"""

import unittest
from pathlib import Path

from lyo_app.ai.schemas.block_redaction import redact_block, redact_blocks

ROOT = Path(__file__).resolve().parents[1]


def _check_block():
    return {
        "id": "b1",
        "type": "quiz",
        "content": {
            "question": "Which fraction is larger?",
            "correct_index": 1,
            "explanation": "Because halves are bigger than thirds.",
            "hint": "Think about the size of each piece.",
            "bailout_index": 2,
            "options": [
                {"id": "0", "text": "1/3", "reveals": "bigger_denominator_is_bigger"},
                {"id": "1", "text": "1/2"},
                {"id": "2", "text": "Just explain it"},
            ],
        },
        "metadata": {"skill_id": "compare_fractions", "source_surface": "chat"},
    }


class WhatIsRemovedTests(unittest.TestCase):
    def test_the_answer_key_does_not_travel_with_the_question(self):
        content = redact_block(_check_block())["content"]
        self.assertNotIn("correct_index", content)

    def test_the_explanation_is_not_a_spoiler(self):
        content = redact_block(_check_block())["content"]
        self.assertNotIn("explanation", content)

    def test_misconception_tags_stay_internal(self):
        """`reveals` is the server's diagnosis of what picking that option
        would mean. It is not for the learner to read mid-question."""
        content = redact_block(_check_block())["content"]
        for option in content["options"]:
            self.assertNotIn("reveals", option)

    def test_nothing_secret_survives_anywhere_in_the_payload(self):
        serialised = repr(redact_block(_check_block()))
        self.assertNotIn("bigger_denominator_is_bigger", serialised)
        self.assertNotIn("Because halves are bigger", serialised)


class WhatIsKeptTests(unittest.TestCase):
    def test_the_learner_can_still_read_the_question_and_options(self):
        content = redact_block(_check_block())["content"]
        self.assertEqual(content["question"], "Which fraction is larger?")
        self.assertEqual([o["text"] for o in content["options"]], ["1/3", "1/2", "Just explain it"])

    def test_the_hint_survives_because_asking_is_not_failure(self):
        content = redact_block(_check_block())["content"]
        self.assertIn("hint", content)

    def test_the_opt_out_survives_because_it_has_to_be_choosable(self):
        content = redact_block(_check_block())["content"]
        self.assertEqual(content["bailout_index"], 2)

    def test_an_answered_check_still_shows_what_was_right(self):
        """The verdict is written to metadata after the learner answers, and
        legitimately carries the correct index. That is how a reloaded
        conversation still marks the right option."""
        block = _check_block()
        block["metadata"]["result"] = {"correct_index": 1, "explanation": "Because…"}
        redacted = redact_block(block)
        self.assertEqual(redacted["metadata"]["result"]["correct_index"], 1)

    def test_the_block_id_and_skill_survive(self):
        redacted = redact_block(_check_block())
        self.assertEqual(redacted["id"], "b1")
        self.assertEqual(redacted["metadata"]["skill_id"], "compare_fractions")


class SafetyTests(unittest.TestCase):
    def test_the_stored_block_is_not_mutated(self):
        """Grading happens on a later request against what was persisted. A
        redacted block written back to the database is an ungradeable one."""
        block = _check_block()
        redact_block(block)
        self.assertEqual(block["content"]["correct_index"], 1)
        self.assertEqual(block["content"]["options"][0]["reveals"],
                         "bigger_denominator_is_bigger")

    def test_blocks_with_nothing_to_hide_pass_through(self):
        text_block = {"id": "t", "type": "text", "content": {"text": "hello"}}
        self.assertIs(redact_block(text_block), text_block)

    def test_odd_data_does_not_cost_the_learner_their_lesson(self):
        for value in (None, "not a block", 42, {"id": "x"}, {"content": None}):
            redact_block(value)  # must not raise

    def test_order_and_count_are_preserved(self):
        blocks = [{"id": "a", "content": {"text": "x"}}, _check_block()]
        redacted = redact_blocks(blocks)
        self.assertEqual([b["id"] for b in redacted], ["a", "b1"])

    def test_an_empty_message_is_left_alone(self):
        self.assertIsNone(redact_blocks(None))
        self.assertEqual(redact_blocks([]), [])


class EveryExitIsCoveredTests(unittest.TestCase):
    """Redacting in one place is worthless if blocks leave by another door.

    There are three: the streamed lesson, the streamed planner blocks, and the
    conversation reload.
    """

    def test_the_streamed_lesson_is_redacted(self):
        source = (ROOT / "lyo_app" / "api" / "v1" / "stream_lyo2.py").read_text()
        self.assertNotIn('{"type": "smart_blocks", "blocks": lesson_blocks}', source)
        self.assertIn("redact_blocks(lesson_blocks)", source)

    def test_the_streamed_planner_blocks_are_redacted(self):
        source = (ROOT / "lyo_app" / "api" / "v1" / "stream_lyo2.py").read_text()
        self.assertNotIn('{"type": "smart_blocks", "blocks": smart_blocks}', source)
        self.assertIn("redact_blocks(smart_blocks)", source)

    def test_a_reloaded_conversation_is_redacted(self):
        source = (ROOT / "lyo_app" / "chat" / "routes.py").read_text()
        start = source.index("def _message_read(")
        rest = source[start + 1 :]
        # Next top-level definition of any kind, since the following symbol
        # may be a class or an async def rather than a plain def.
        ends = [i for i in (rest.find("\ndef "), rest.find("\nasync def "),
                            rest.find("\nclass ")) if i != -1]
        body = rest[: min(ends)] if ends else rest
        self.assertIn("redact_blocks(", body)

    def test_persistence_still_writes_the_unredacted_block(self):
        """The lesson is persisted from `lesson_blocks`, not from the redacted
        copy, or the check could never be graded."""
        source = (ROOT / "lyo_app" / "api" / "v1" / "stream_lyo2.py").read_text()
        body = source[source.index("async def _emit_composed_lesson("):]
        body = body[: body.index("\ndef ", 1)]
        self.assertIn("blocks=lesson_blocks,", body)
        self.assertNotIn("blocks=redact_blocks(", body)


if __name__ == "__main__":
    unittest.main()


class ThePlannerPathIsClosedTooTests(unittest.TestCase):
    """There was a fourth door.

    An earlier change closed the streamed lesson, the streamed planner blocks
    and the conversation reload, and said so. But the planner also yields the
    same quiz as a legacy `artifact` event carrying `artifact.content`
    directly, so the answer key kept travelling on that path — redacting only
    the block-shaped exits was not enough.
    """

    def setUp(self):
        self.source = (ROOT / "lyo_app" / "api" / "v1" / "stream_lyo2.py").read_text()

    def test_the_artifact_event_is_redacted(self):
        self.assertIn("redact_content(dict(artifact.content)", self.source)

    def test_no_raw_artifact_content_is_tagged_and_sent(self):
        self.assertNotIn(
            "tagged_content = dict(artifact.content) if artifact.content else {}",
            self.source,
        )


class ContentLevelRedactionTests(unittest.TestCase):
    """`redact_content` is what makes the non-block exits coverable."""

    def test_it_strips_the_same_fields(self):
        from lyo_app.ai.schemas.block_redaction import redact_content

        clean = redact_content(_check_block()["content"])
        self.assertNotIn("correct_index", clean)
        self.assertNotIn("explanation", clean)
        for option in clean["options"]:
            self.assertNotIn("reveals", option)

    def test_it_keeps_what_the_learner_needs(self):
        from lyo_app.ai.schemas.block_redaction import redact_content

        clean = redact_content(_check_block()["content"])
        self.assertEqual(clean["question"], "Which fraction is larger?")
        self.assertIn("hint", clean)
        self.assertEqual(clean["bailout_index"], 2)

    def test_it_does_not_mutate_its_input(self):
        from lyo_app.ai.schemas.block_redaction import redact_content

        content = _check_block()["content"]
        redact_content(content)
        self.assertEqual(content["correct_index"], 1)

    def test_content_with_nothing_to_hide_passes_through(self):
        from lyo_app.ai.schemas.block_redaction import redact_content

        plan = {"plan": "study more"}
        self.assertIs(redact_content(plan), plan)
