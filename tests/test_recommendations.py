""""For you" has to mean something.

Home's "Recommended For You" rendered `courses.list(0, 4)` — the first four
rows of the catalogue, identical for every learner. A comment in the page said
so plainly. It is a milder version of the fabrication this product was cleaned
up to remove: not invented data, but a claim about the learner that nothing
behind it supports.
"""

import unittest

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from lyo_app.personalization.recommendations import (
    REASON_DUE,
    REASON_WEAK,
    RecommendationList,
    build_recommendations,
    recommendations_for_user,
)


def _due(skill_id, days_overdue=0, mastery=0.4, misconception=None):
    return {
        "skill_id": skill_id,
        "days_overdue": days_overdue,
        "mastery_level": mastery,
        "last_misconception": misconception,
    }


# ─── What gets recommended, and in what order ────────────────────────────────

class OrderingTests(unittest.TestCase):
    def test_a_fading_memory_comes_before_a_weak_one(self):
        """The schedule says that memory is going now. Nothing on the weak
        list is more time-sensitive than that."""
        result = build_recommendations(
            due_reviews=[_due("photosynthesis")],
            weaknesses=["quadratics"],
            skills={"quadratics": 0.1},
        )
        self.assertEqual([i.concept_id for i in result.items],
                         ["photosynthesis", "quadratics"])

    def test_a_concept_is_never_recommended_twice(self):
        """Being due is the more specific and more urgent thing to say about a
        concept that is also weak."""
        result = build_recommendations(
            due_reviews=[_due("quadratics")],
            weaknesses=["quadratics"],
            skills={"quadratics": 0.1},
        )
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].reason, REASON_DUE)

    def test_the_list_is_capped(self):
        result = build_recommendations(
            due_reviews=[_due(f"skill_{i}") for i in range(10)],
            weaknesses=[f"weak_{i}" for i in range(10)],
            skills={},
            limit=3,
        )
        self.assertEqual(len(result.items), 3)

    def test_duplicates_within_the_due_list_collapse(self):
        result = build_recommendations(
            due_reviews=[_due("quadratics"), _due("quadratics", days_overdue=9)],
            weaknesses=[],
            skills={},
        )
        self.assertEqual(len(result.items), 1)


# ─── The reason is the point ─────────────────────────────────────────────────

class ReasonTests(unittest.TestCase):
    def test_a_known_slip_is_named_rather_than_a_generic_nudge(self):
        result = build_recommendations(
            due_reviews=[_due("quadratics", misconception="sign_error")],
            weaknesses=[], skills={},
        )
        self.assertIn("sign error", result.items[0].detail)

    def test_being_overdue_is_stated_in_days(self):
        result = build_recommendations(
            due_reviews=[_due("quadratics", days_overdue=3)], weaknesses=[], skills={}
        )
        self.assertIn("3 days", result.items[0].detail)

    def test_one_day_is_not_pluralised(self):
        result = build_recommendations(
            due_reviews=[_due("quadratics", days_overdue=1)], weaknesses=[], skills={}
        )
        self.assertIn("1 day ", result.items[0].detail + " ")
        self.assertNotIn("1 days", result.items[0].detail)

    def test_a_weak_concept_says_why_it_is_here(self):
        result = build_recommendations(
            due_reviews=[], weaknesses=["quadratics"], skills={"quadratics": 0.1}
        )
        self.assertEqual(result.items[0].reason, REASON_WEAK)
        self.assertTrue(result.items[0].detail)

    def test_a_learner_is_never_shown_our_database_keys(self):
        """Concepts are keyed `compare_fractions`. Showing that to a learner
        is showing them our schema."""
        result = build_recommendations(
            due_reviews=[_due("x", misconception="bigger_denominator_is_bigger")],
            weaknesses=[], skills={},
        )
        self.assertNotIn("_", result.items[0].detail)


# ─── What is not claimed ─────────────────────────────────────────────────────

class HonestyTests(unittest.TestCase):
    def test_no_history_means_no_recommendations(self):
        """Home has an honest empty state. Filling it with the catalogue and
        calling it "for you" is what this replaces."""
        self.assertEqual(build_recommendations([], [], {}), RecommendationList())

    def test_never_assessed_is_null_not_zero(self):
        """"Never assessed" and "assessed at zero" are different claims about
        a learner."""
        result = build_recommendations(
            due_reviews=[], weaknesses=["untouched"], skills={}
        )
        self.assertIsNone(result.items[0].mastery)

    def test_a_known_mastery_is_carried_through(self):
        result = build_recommendations(
            due_reviews=[], weaknesses=["quadratics"], skills={"quadratics": 0.2}
        )
        self.assertAlmostEqual(result.items[0].mastery, 0.2)

    def test_entries_naming_no_concept_are_skipped(self):
        result = build_recommendations(
            due_reviews=[_due(None), {}, None], weaknesses=[None, ""], skills={}
        )
        self.assertEqual(result.items, [])

    def test_days_overdue_is_never_negative(self):
        result = build_recommendations(
            due_reviews=[_due("quadratics", days_overdue=-4)], weaknesses=[], skills={}
        )
        self.assertEqual(result.items[0].days_overdue, 0)


# ─── Against the engine ──────────────────────────────────────────────────────

async def test_a_guest_gets_nothing_rather_than_an_error():
    assert await recommendations_for_user(MagicMock(), "guest-abc") == RecommendationList()
    assert await recommendations_for_user(MagicMock(), None) == RecommendationList()


async def test_a_failing_source_costs_that_source_not_the_page():
    """Home renders this. One broken query should not blank the section, let
    alone the page."""
    engine = MagicMock()
    engine.get_due_reviews = AsyncMock(side_effect=RuntimeError("down"))
    engine.get_mastery_profile = AsyncMock(
        return_value=MagicMock(weaknesses=["quadratics"], skills={"quadratics": 0.1})
    )

    with patch("lyo_app.personalization.service.personalization_engine", engine):
        result = await recommendations_for_user(MagicMock(), 1)

    assert [i.concept_id for i in result.items] == ["quadratics"]


async def test_both_sources_failing_is_still_not_an_error():
    engine = MagicMock()
    engine.get_due_reviews = AsyncMock(side_effect=RuntimeError("down"))
    engine.get_mastery_profile = AsyncMock(side_effect=RuntimeError("also down"))

    with patch("lyo_app.personalization.service.personalization_engine", engine):
        assert await recommendations_for_user(MagicMock(), 1) == RecommendationList()


async def test_the_real_sources_are_the_ones_consulted():
    """No fifth recommender: this reads the schedule and the profile the rest
    of the product already writes."""
    engine = MagicMock()
    engine.get_due_reviews = AsyncMock(return_value=[_due("photosynthesis")])
    engine.get_mastery_profile = AsyncMock(
        return_value=MagicMock(weaknesses=[], skills={})
    )

    with patch("lyo_app.personalization.service.personalization_engine", engine):
        result = await recommendations_for_user(MagicMock(), 7)

    engine.get_due_reviews.assert_awaited_once()
    engine.get_mastery_profile.assert_awaited_once()
    assert result.items[0].concept_id == "photosynthesis"


if __name__ == "__main__":
    unittest.main()
