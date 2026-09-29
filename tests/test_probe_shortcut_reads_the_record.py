"""When the record already says where a learner is, the probe may stand down.

Skipping the opening question is the one place the classroom acts on the
learner's stored record without asking them anything, so the conditions have
to be ones the record can actually answer. Two of them could not.

The skill was matched by lowercasing a human title against a store that holds
slugs and UUIDs, so "Compare Fractions" never met `compare_fractions` and the
shortcut quietly never fired outside sessions with a resolved skill identity.
And "no recent failure" read `consecutive_incorrect`, which the canonical
mastery path never sets — it is zero for everyone there, and on the legacy
path it is a lifetime count instead. These pin the canonicalisation and the
populated signal that replaced it.
"""

from datetime import datetime, timedelta

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import GuidedState
from lyo_app.ai_classroom.scene_lifecycle_engine import KnowledgeState
from tests.adaptive_fixtures import context, plan


def a_state(**overrides):
    fields = dict(owner="42", plan=plan(), record_scope="topic")
    fields.update(overrides)
    return GuidedState(**fields)


def known(concept_id, *, mastery=0.9, attempts=4, successes=4, ago=timedelta(days=1)):
    return KnowledgeState(
        concept_id=concept_id, mastery_level=mastery, confidence=0.8,
        total_attempts=attempts, successes=successes,
        last_attempt=datetime.utcnow() - ago,
    )


def shortcut(states, **ctx):
    return AdaptiveSession(None).record_answers_the_probe(
        context(knowledge_states=states, **ctx), a_state(),
    )


# ─── Naming the skill the way the evidence was written ──────────────────────

def test_a_title_meets_the_slug_its_evidence_was_filed_under():
    """The topic is "Fractions"; the record holds `fractions`.

    Evidence goes through `_canonical_concept_id`, which slugifies anything
    that is not a `Concept` row id. Lowercasing alone matched only titles
    whose slug differs by case, which is to say almost none of them.
    """
    assert shortcut([known("fractions")]) is not None


def test_a_multi_word_title_meets_its_slug_too():
    # "Compare fractions" lowercased is "compare fractions", which is not
    # "compare_fractions". This is the case that never once matched.
    assert shortcut([known("compare_fractions")], topic="Compare fractions") is not None


def test_a_resolved_skill_id_is_left_exactly_as_it_is():
    """A UUID names a row and must not be slugified into something else."""
    identity = "d3568c81-06c8-4f5c-99b4-c7a3585e2079"
    state = a_state(identity_required=True, topic_skill_id=identity)
    assert AdaptiveSession(None).record_answers_the_probe(
        context(knowledge_states=[known(identity)]), state) is not None


def test_a_neighbouring_skill_does_not_answer_this_unit_s_probe():
    assert shortcut([known("decimals")]) is None


# ─── A signal the record actually carries ───────────────────────────────────

def test_a_high_score_a_learner_keeps_getting_wrong_does_not_answer_it():
    """Four attempts, one right, and mastery still above the line.

    The DKT leaves a high prior above 0.7 after a single failure, so score
    alone is not evidence of a learner who has this. The old guard was meant
    to catch exactly that and could not: `consecutive_incorrect` is never
    populated on the canonical path.
    """
    assert shortcut([known("fractions", attempts=4, successes=1)]) is None


def test_a_learner_who_gets_it_right_most_of_the_time_still_answers_it():
    assert shortcut([known("fractions", attempts=10, successes=8)]) is not None


def test_one_slip_in_a_long_strong_history_is_not_disqualifying():
    """The legacy path read a lifetime incorrect count, which would bar this.

    A learner with nineteen right out of twenty has this skill. Barring them
    for ever over one wrong answer is the opposite failure to the one above,
    and the same field caused both.
    """
    assert shortcut([known("fractions", attempts=20, successes=19)]) is not None


# ─── The conditions that were already right ─────────────────────────────────

def test_a_weak_record_does_not_answer_it():
    assert shortcut([known("fractions", mastery=0.5)]) is None


def test_a_stale_demonstration_does_not_answer_it():
    assert shortcut([known("fractions", ago=timedelta(days=30))]) is None


def test_a_record_with_no_attempt_behind_it_does_not_answer_it():
    assert shortcut([known("fractions", attempts=0, successes=0)]) is None


def test_no_record_at_all_leaves_the_probe_to_ask():
    assert shortcut([]) is None
