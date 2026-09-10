"""Phase E: a study plan reports the learner, not the learner's self-report.

Three things are pinned here, all of which were wrong on the live routes:

* the client cannot declare its own session score;
* a plan's "mastery" comes from the canonical record, not from averaging
  session scores;
* readiness exists at all, and distinguishes "not started" from "measured at
  zero" everywhere a learner would see the difference.
"""

from datetime import date, datetime, timedelta

import pytest

from lyo_app.study_plans.session_outcome import (
    MINIMUM_WINDOW,
    SessionOutcome,
    outcome_from_evidence,
    was_graded,
    window_start,
)
from lyo_app.study_plans.topic_standing import (
    DEFAULT_WEIGHT,
    TopicStanding,
    build_standings,
    concept_id_for_topic,
    days_until,
    readiness_fraction,
    topic_name,
    topic_weight,
    weakest_topics,
)


# ─── Naming a topic the way the rest of the product names it ────────────────

def test_a_topic_reaches_the_concept_chat_would_have_created():
    from lyo_app.ai.lesson_composer import slugify_skill

    for topic in ["Quadratic Equations", "quadratic equations", "Quadratic  Equations!"]:
        assert concept_id_for_topic(topic) == slugify_skill(topic)
    # The point of the shared slug: three spellings, one record.
    assert (
        concept_id_for_topic("Quadratic Equations")
        == concept_id_for_topic("quadratic equations!")
    )


def test_a_topic_entry_is_read_however_intake_stored_it():
    assert topic_name({"name": "Photosynthesis"}) == "Photosynthesis"
    assert topic_name("Photosynthesis") == "Photosynthesis"
    assert topic_name({"topic": "Photosynthesis"}) == "Photosynthesis"
    assert topic_name({}) is None
    assert topic_name({"name": "   "}) is None
    assert topic_name(None) is None


def test_an_unusable_weight_never_subtracts_from_readiness():
    assert topic_weight({"weight": 3}) == 3.0
    assert topic_weight({"weight": "nonsense"}) == DEFAULT_WEIGHT
    assert topic_weight({"weight": -5}) == DEFAULT_WEIGHT
    assert topic_weight({"weight": 0}) == DEFAULT_WEIGHT
    assert topic_weight({}) == DEFAULT_WEIGHT
    assert topic_weight("bare string") == DEFAULT_WEIGHT


# ─── Never assessed is not assessed at zero ─────────────────────────────────

def test_a_topic_with_no_record_has_no_mastery_rather_than_zero():
    standings = build_standings([{"name": "Mitosis"}], {})
    assert len(standings) == 1
    assert standings[0].mastery is None
    assert standings[0].assessed is False


def test_being_taught_a_topic_is_not_a_result_on_it():
    # The projection creates a row the moment a concept is delivered, with no
    # attempt behind it. Reading that row as a score would report a lesson as
    # a failed test.
    standings = build_standings(
        [{"name": "Mitosis"}], {"mitosis": (0.0, 0)}
    )
    assert standings[0].mastery is None
    assert standings[0].attempts == 0


def test_a_measured_zero_is_reported_as_zero():
    standings = build_standings([{"name": "Mitosis"}], {"mitosis": (0.0, 3)})
    assert standings[0].mastery == 0.0
    assert standings[0].assessed is True


def test_one_topic_spelled_two_ways_is_one_topic():
    standings = build_standings(
        [{"name": "Mitosis", "weight": 2}, {"name": "mitosis!", "weight": 9}],
        {"mitosis": (0.8, 4)},
    )
    # Otherwise it counts twice toward readiness and lists twice on screen.
    assert len(standings) == 1
    # The first spelling wins, name and weight together. Letting the later one
    # overwrite would silently re-weight a topic — here from 2 to 9, a change
    # big enough to move readiness — because someone typed it twice.
    assert standings[0].topic == "Mitosis"
    assert standings[0].weight == 2.0


# ─── Readiness ──────────────────────────────────────────────────────────────

def _standing(topic, weight, mastery, attempts=3):
    return TopicStanding(
        topic=topic,
        concept_id=concept_id_for_topic(topic),
        weight=weight,
        mastery=mastery,
        attempts=attempts if mastery is not None else 0,
    )


def test_readiness_is_weighted_by_how_much_of_the_exam_a_topic_is():
    heavy_known = [_standing("A", 9.0, 1.0), _standing("B", 1.0, 0.0)]
    heavy_unknown = [_standing("A", 1.0, 1.0), _standing("B", 9.0, 0.0)]
    assert readiness_fraction(heavy_known) == pytest.approx(0.9)
    assert readiness_fraction(heavy_unknown) == pytest.approx(0.1)


def test_an_untouched_topic_counts_against_readiness():
    # For a single concept "not assessed" is unknown. For "am I ready on
    # Friday", a topic you have shown nothing on is one you are not ready for.
    assert readiness_fraction([_standing("A", 1.0, 1.0), _standing("B", 1.0, None)]) == pytest.approx(0.5)


def test_readiness_is_none_only_when_there_are_no_topics():
    assert readiness_fraction([]) is None
    assert readiness_fraction([_standing("A", 1.0, None)]) == pytest.approx(0.0)


def test_readiness_stays_inside_zero_and_one():
    # A stored score outside range must not produce a readiness above 100%.
    over = build_standings([{"name": "A"}], {"a": (5.0, 2)})
    assert over[0].mastery == 1.0
    assert readiness_fraction(over) == pytest.approx(1.0)


def test_days_remaining_goes_negative_once_the_test_has_passed():
    today = date(2026, 5, 10)
    assert days_until(date(2026, 5, 17), today) == 7
    assert days_until(date(2026, 5, 10), today) == 0
    assert days_until(date(2026, 5, 3), today) == -7
    assert days_until(None, today) is None


def test_focus_names_unopened_topics_before_shaky_ones():
    standings = [
        _standing("shaky", 1.0, 0.2),
        _standing("untouched", 1.0, None),
        _standing("solid", 1.0, 0.9),
    ]
    assert [s.topic for s in weakest_topics(standings)][0] == "untouched"
    assert [s.topic for s in weakest_topics(standings, limit=2)] == ["untouched", "shaky"]


def test_among_untouched_topics_the_heavier_one_comes_first():
    standings = [_standing("minor", 1.0, None), _standing("major", 8.0, None)]
    assert [s.topic for s in weakest_topics(standings)] == ["major", "minor"]


def test_weight_breaks_the_tie_between_unopened_and_failed():
    # Both have nothing demonstrated. Sending the learner to the one-percent
    # topic they had not started, ahead of the forty-percent topic they got
    # entirely wrong, is how you lose them the exam.
    standings = [
        _standing("barely_counts", 1.0, None),
        _standing("most_of_the_paper", 8.0, 0.0),
    ]
    assert [s.topic for s in weakest_topics(standings)][0] == "most_of_the_paper"


# ─── The client cannot score itself ─────────────────────────────────────────

def test_the_complete_route_no_longer_accepts_a_score():
    import inspect

    from lyo_app.study_plans.routes import complete_session

    params = inspect.signature(complete_session).parameters
    # A learner could POST ?performance_score=1.0 and the dashboard would
    # report it as their mastery.
    assert "performance_score" not in params


def test_only_a_graded_demonstration_moves_the_score():
    # A wrong answer and a lesson delivered both sit on the exposure rung at
    # zero confidence. `measurable_outcome` is what tells them apart.
    assert was_graded(0.0) is True
    assert was_graded(1.0) is True
    assert was_graded(None) is False


def test_a_click_on_an_explorable_is_not_a_failed_attempt():
    # Client-posted events are sanitized to exposure at 0.0 confidence with no
    # measurable outcome. Scoring those as zeros would let moving a slider
    # drag a learner's session to the floor.
    outcome = outcome_from_evidence(
        [("exposure", 0.0, None), ("exposure", 0.0, None)]
    )
    assert outcome.score is None
    assert outcome.graded == 0
    assert outcome.seen == 2


def test_a_wrong_answer_is_a_graded_zero():
    outcome = outcome_from_evidence([("exposure", 0.0, 0.0)])
    assert outcome.score == 0.0
    assert outcome.graded == 1


def test_the_score_is_the_mean_of_what_was_graded():
    outcome = outcome_from_evidence(
        [
            ("application", 1.0, 1.0),
            ("exposure", 0.0, 0.0),
            ("exposure", 0.0, None),  # taught, not asked
        ]
    )
    assert outcome.score == pytest.approx(0.5)
    assert outcome.graded == 2
    assert outcome.seen == 1


def test_an_unrecognised_evidence_type_scores_nothing():
    outcome = outcome_from_evidence([("telepathy", 1.0, 1.0)])
    assert outcome.score is None
    assert outcome.graded == 0
    assert outcome.seen == 0


def test_a_graded_row_with_an_unreadable_confidence_still_counts():
    outcome = outcome_from_evidence([("application", "banana", 1.0)])
    assert outcome.graded == 1
    assert outcome.score == 0.0


def test_nothing_graded_means_no_score_not_a_zero():
    outcome = outcome_from_evidence([])
    assert outcome.measured is False
    assert outcome.score is None
    assert SessionOutcome(score=0.0, graded=1, seen=0).measured is True


# ─── The window a session's evidence comes from ─────────────────────────────

def test_evidence_from_before_the_session_began_is_not_this_session():
    now = datetime(2026, 5, 10, 12, 0)
    scheduled = datetime(2026, 5, 10, 11, 30)
    assert window_start(scheduled, 30, now) == scheduled


def test_a_session_left_open_for_days_does_not_sweep_up_the_week():
    now = datetime(2026, 5, 17, 12, 0)
    scheduled = datetime(2026, 5, 10, 11, 30)  # a week earlier
    started = window_start(scheduled, 30, now)
    assert started > scheduled
    assert now - started == MINIMUM_WINDOW


def test_a_long_session_gets_a_window_longer_than_the_minimum():
    now = datetime(2026, 5, 17, 12, 0)
    scheduled = datetime(2026, 5, 1, 0, 0)
    # 120 minutes with the overrun factor is 8 hours, well past the floor.
    assert now - window_start(scheduled, 120, now) == timedelta(hours=8)


def test_a_session_with_no_duration_still_has_a_window():
    now = datetime(2026, 5, 17, 12, 0)
    scheduled = datetime(2026, 5, 1, 0, 0)
    assert now - window_start(scheduled, None, now) == MINIMUM_WINDOW
    assert now - window_start(scheduled, 0, now) == MINIMUM_WINDOW


# ─── The plan reports the record, not itself ────────────────────────────────

def test_plan_stats_no_longer_average_session_scores():
    import inspect

    from lyo_app.study_plans import routes

    source = inspect.getsource(routes.get_plan_stats)
    body = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    # The old computation: sum(scores)/len(scores) over completed sessions.
    assert "performance_score" not in body
    assert "standings_for_profile" in body


def test_a_session_read_carries_the_concept_the_classroom_would_teach():
    from lyo_app.study_plans.schemas import StudySessionRead

    session = StudySessionRead(
        id="s1",
        study_plan_id="p1",
        user_id=1,
        scheduled_at=datetime(2026, 5, 10, 16, 0),
        duration_minutes=45,
        topic="Quadratic Equations",
        session_type="learn",
        module_id=None,
        status="scheduled",
        completed_at=None,
        performance_score=None,
        user_notes=None,
        agent_notes=None,
    )
    assert session.concept_id == concept_id_for_topic("Quadratic Equations")
    assert "concept_id" in session.model_dump()
