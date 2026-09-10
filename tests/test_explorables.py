"""Representations a learner can move through, and what that is worth.

Every subject was getting the same treatment: prose, then a multiple-choice
question. A number line for fractions and a timeline for a sequence of events
are how those subjects are actually thought about — placing a fraction is a
different act from reading about one.

Two rules do the load-bearing work here. The points come from the lesson the
model is already writing, so an explorable cannot introduce facts the lesson
does not contain. And manipulating one is *exposure*: the learner met the
idea, they have not shown they can use it.
"""

import unittest

import pytest
from pydantic import ValidationError

from lyo_app.ai.lesson_composer import (
    ChatLesson,
    Explorable,
    ExplorablePoint,
    LessonSection,
    SectionKind,
)
from lyo_app.ai.schemas.smart_block import SmartBlock
from lyo_app.api.v1.stream_lyo2 import _lesson_to_smart_blocks
from lyo_app.events.evidence import EVIDENCE_KINDS


def _number_line(**overrides):
    fields = {
        "kind": "number_line",
        "prompt": "Place 3/4 on the line.",
        "points": [
            ExplorablePoint(label="0", value=0.0),
            ExplorablePoint(label="3/4", value=0.75),
            ExplorablePoint(label="1", value=1.0),
        ],
    }
    fields.update(overrides)
    return Explorable(**fields)


def _timeline(**overrides):
    fields = {
        "kind": "timeline",
        "prompt": "Notice what follows 1789.",
        "points": [
            ExplorablePoint(label="Estates-General", year=1789),
            ExplorablePoint(label="Terror begins", year=1793),
        ],
    }
    fields.update(overrides)
    return Explorable(**fields)


# ─── A half-built explorable is refused, not repaired ────────────────────────

class ValidationTests(unittest.TestCase):
    def test_a_number_line_point_without_a_value_has_nowhere_to_sit(self):
        with self.assertRaises(ValidationError):
            _number_line(points=[
                ExplorablePoint(label="0", value=0.0),
                ExplorablePoint(label="somewhere"),
            ])

    def test_a_timeline_point_without_a_year_has_no_moment(self):
        with self.assertRaises(ValidationError):
            _timeline(points=[
                ExplorablePoint(label="Estates-General", year=1789),
                ExplorablePoint(label="later"),
            ])

    def test_points_that_all_share_a_position_are_not_a_track(self):
        """They would stack on one spot, taking the room of a representation
        while showing nothing."""
        with self.assertRaises(ValidationError):
            _number_line(points=[
                ExplorablePoint(label="a", value=1.0),
                ExplorablePoint(label="b", value=1.0),
            ])

    def test_one_point_is_a_dot(self):
        with self.assertRaises(ValidationError):
            _number_line(points=[ExplorablePoint(label="0", value=0.0)])

    def test_a_kind_no_client_can_draw_is_refused(self):
        with self.assertRaises(ValidationError):
            _number_line(kind="hyperbolic_manifold")

    def test_years_before_the_common_era_are_allowed(self):
        explorable = _timeline(points=[
            ExplorablePoint(label="Republic founded", year=-509),
            ExplorablePoint(label="Empire begins", year=-27),
        ])
        self.assertEqual(explorable.points[0].year, -509)


# ─── It reaches the client as a block ────────────────────────────────────────

def _lesson(explorable):
    return ChatLesson(
        skill_id="compare_fractions",
        topic="Fractions",
        sections=[
            LessonSection(
                kind=SectionKind.representation,
                text="A fraction is a position, not just a pair of numbers.",
                explorable=explorable,
            )
        ],
    )


def _explorable_blocks(blocks):
    return [b for b in blocks if b.get("subtype") == "explorable"]


class EmissionTests(unittest.TestCase):
    def test_a_lesson_with_an_explorable_ships_one(self):
        blocks = _lesson_to_smart_blocks(_lesson(_number_line()))
        found = _explorable_blocks(blocks)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["content"]["kind"], "number_line")
        self.assertEqual(len(found[0]["content"]["points"]), 3)

    def test_a_lesson_without_one_ships_none(self):
        """Most topics have neither shape. The composer omits it rather than
        decorating every lesson with a widget."""
        blocks = _lesson_to_smart_blocks(_lesson(None))
        self.assertEqual(_explorable_blocks(blocks), [])

    def test_the_prose_still_ships_alongside_it(self):
        """The explorable is a second way to see the idea, not a replacement
        for saying it."""
        blocks = _lesson_to_smart_blocks(_lesson(_number_line()))
        text = " ".join(
            b["content"].get("text", "") for b in blocks if b.get("type") == "text"
        )
        self.assertIn("A fraction is a position", text)

    def test_the_concept_travels_with_it(self):
        """Engagement has to be recorded against something."""
        blocks = _lesson_to_smart_blocks(_lesson(_timeline()))
        self.assertEqual(
            _explorable_blocks(blocks)[0]["metadata"]["concept_id"], "compare_fractions"
        )

    def test_it_rides_an_existing_block_type(self):
        """A tenth top-level type would render as nothing on a client that has
        not shipped support. An unknown *subtype* falls back to the generic
        interactive renderer instead."""
        block = _explorable_blocks(_lesson_to_smart_blocks(_lesson(_number_line())))[0]
        self.assertEqual(block["type"], "interactive")
        self.assertEqual(block["subtype"], "explorable")

    def test_empty_positions_are_not_shipped_as_nulls(self):
        """A number line's points have no `year`, and sending `year: null` for
        each invites a client to plot them at zero."""
        block = _explorable_blocks(_lesson_to_smart_blocks(_lesson(_number_line())))[0]
        for point in block["content"]["points"]:
            self.assertNotIn("year", point)


# ─── What it is worth ────────────────────────────────────────────────────────

class EvidenceTests(unittest.TestCase):
    def test_moving_one_is_exposure(self):
        """Named here as well as on the client, because the two have to agree
        and because it is the whole safety argument: if engagement could award
        a rung, a lesson becomes a slider a learner can drag to mastery."""
        self.assertEqual(EVIDENCE_KINDS[0], "exposure")

    def test_the_block_carries_no_grading_fields_at_all(self):
        block = _explorable_blocks(_lesson_to_smart_blocks(_lesson(_number_line())))[0]
        serialised = repr(block)
        for field in ("correct_index", "evidence_type", "evidence_confidence",
                      "measurable_outcome"):
            self.assertNotIn(field, serialised)


if __name__ == "__main__":
    unittest.main()


class AnUnusableExplorableCostsOnlyItselfTests(unittest.TestCase):
    """The decoration must not take the teaching down with it.

    `Explorable` refuses points that cannot be placed, and the intent was that
    the lesson still ships without it. But the validation is nested inside
    `ChatLesson`, so the raise propagated and `compose` discarded the entire
    structured lesson — including its gradeable check — in favour of prose.
    """

    def test_a_bad_explorable_is_dropped_and_the_lesson_survives(self):
        from lyo_app.ai.lesson_composer import _drop_unusable_explorables

        raw = {
            "sections": [
                {
                    "kind": "representation",
                    "text": "A fraction is a position.",
                    # No `value`: nowhere to place it.
                    "explorable": {
                        "kind": "number_line",
                        "prompt": "Place it",
                        "points": [{"label": "a"}, {"label": "b", "value": 1}],
                    },
                }
            ],
            "check": {"question": "kept"},
        }
        _drop_unusable_explorables(raw)

        self.assertNotIn("explorable", raw["sections"][0])
        self.assertEqual(raw["sections"][0]["text"], "A fraction is a position.")
        self.assertEqual(raw["check"], {"question": "kept"})

    def test_a_good_explorable_is_left_alone(self):
        from lyo_app.ai.lesson_composer import _drop_unusable_explorables

        raw = {
            "sections": [
                {
                    "kind": "representation",
                    "text": "x",
                    "explorable": {
                        "kind": "timeline",
                        "prompt": "Notice the order",
                        "points": [
                            {"label": "a", "year": 1789},
                            {"label": "b", "year": 1799},
                        ],
                    },
                }
            ]
        }
        _drop_unusable_explorables(raw)
        self.assertIn("explorable", raw["sections"][0])

    def test_it_runs_before_the_lesson_is_validated(self):
        """Checking after validation would be checking after the raise."""
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "lyo_app" / "ai" / "lesson_composer.py"
        ).read_text()
        self.assertLess(
            source.index("_drop_unusable_explorables(raw)"),
            source.index("lesson = ChatLesson.model_validate(raw)"),
        )

    def test_odd_shapes_do_not_raise(self):
        from lyo_app.ai.lesson_composer import _drop_unusable_explorables

        for raw in ({}, {"sections": None}, {"sections": ["not a dict"]},
                    {"sections": [{"kind": "core", "text": "x"}]}):
            _drop_unusable_explorables(raw)
