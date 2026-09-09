"""The evidence ladder, and its agreement with the client.

Pure logic plus source assertions — no database and no app imports beyond the
evidence module itself, matching the style of test_canonical_learning_contract.
"""

from pathlib import Path

from lyo_app.events.evidence import (
    EVIDENCE_KINDS,
    MASTERY_CONFIDENCE_FLOOR,
    MASTERY_REQUIRES,
    confidence_after_hints,
    derive_mastery_state,
    evidence_from_graded_answer,
    is_stronger_evidence,
    normalize_evidence_kind,
)

ROOT = Path(__file__).resolve().parents[1]


def _strong(kind):
    return {"kind": kind, "confidence": 1.0}


# ─── The ladder ──────────────────────────────────────────────────────────────

def test_application_is_stronger_than_exposure():
    assert is_stronger_evidence("application", "exposure")
    assert not is_stronger_evidence("exposure", "application")


def test_transfer_is_stronger_than_recognition():
    assert is_stronger_evidence("transfer", "recognition")
    assert not is_stronger_evidence("recognition", "transfer")


def test_classroom_wire_vocabulary_maps_onto_the_ladder():
    # sdui_models.py emits these four and calls retention "retrieval".
    assert normalize_evidence_kind("explanation") == "explanation"
    assert normalize_evidence_kind("application") == "application"
    assert normalize_evidence_kind("transfer") == "transfer"
    assert normalize_evidence_kind("retrieval") == "retention"


def test_unrecognised_evidence_never_advances_a_rung():
    # A new server-side type must not be silently scored as exposure, and
    # certainly not as transfer.
    assert normalize_evidence_kind("vibes") is None
    assert derive_mastery_state([{"kind": "vibes", "confidence": 1.0}]) == "NOT_SEEN"


# ─── Mastery is not granted cheaply ──────────────────────────────────────────

def test_one_correct_answer_cannot_create_full_mastery():
    evidence = evidence_from_graded_answer(correct=True)
    assert derive_mastery_state([evidence]) == "RECOGNIZED"


def test_being_taught_is_not_evidence_of_anything():
    assert derive_mastery_state([{"kind": "exposure", "confidence": 0.0}]) == "EXPOSED"
    assert derive_mastery_state([]) == "NOT_SEEN"


def test_mastery_requires_application_transfer_and_retention_together():
    # Any two of the three is not enough, however confident.
    assert derive_mastery_state([_strong("application"), _strong("transfer")]) != "MASTERED"
    assert derive_mastery_state([_strong("application"), _strong("retention")]) != "MASTERED"
    assert derive_mastery_state([_strong("transfer"), _strong("retention")]) != "MASTERED"

    assert derive_mastery_state(
        [_strong("application"), _strong("transfer"), _strong("retention")]
    ) == "MASTERED"


def test_shaky_evidence_reaches_the_rung_but_not_mastery():
    shaky = MASTERY_CONFIDENCE_FLOOR - 0.01
    evidence = [
        {"kind": "application", "confidence": 1.0},
        {"kind": "transfer", "confidence": shaky},
        {"kind": "retention", "confidence": 1.0},
    ]
    # The learner did transfer it — that is recorded — but a barely-scraped
    # transfer is not proof of durable mastery.
    assert derive_mastery_state(evidence) == "RETAINED"


def test_delayed_retrieval_is_what_moves_a_concept_to_retained():
    assert derive_mastery_state([_strong("application")]) == "APPLIED"
    assert derive_mastery_state([_strong("application"), _strong("retention")]) == "RETAINED"


# ─── Skipping and hints are not failure ──────────────────────────────────────

def test_a_skipped_question_is_neutral_not_incorrect():
    assert evidence_from_graded_answer(correct=False, bailed_out=True) is None
    # And so it cannot read as evidence of failure.
    assert derive_mastery_state([]) == "NOT_SEEN"


def test_hints_damp_confidence_without_demoting_the_rung():
    unaided = evidence_from_graded_answer(correct=True)
    helped = evidence_from_graded_answer(correct=True, hints_used=2)

    assert helped["kind"] == "recognition"
    assert helped["confidence"] < unaided["confidence"]
    assert helped["confidence"] > 0


def test_more_help_means_less_confidence():
    assert confidence_after_hints(1.0, hints_used=1) > confidence_after_hints(1.0, hints_used=3)
    assert confidence_after_hints(1.0, "nudge") > confidence_after_hints(1.0, "full_example")
    assert confidence_after_hints(1.0) == 1.0


# ─── Misconceptions ──────────────────────────────────────────────────────────

def test_a_wrong_answer_records_the_misconception_and_only_exposure():
    wrong = evidence_from_graded_answer(
        correct=False, misconception="treats the denominator as additive"
    )
    assert wrong["misconception"] == "treats the denominator as additive"
    assert derive_mastery_state([wrong]) == "EXPOSED"


def test_a_misconception_survives_a_correct_retry():
    # Remediation needs to know what was wrong, not just that it is now right.
    right = evidence_from_graded_answer(
        correct=True, misconception="confuses mass and weight"
    )
    assert right["misconception"] == "confuses mass and weight"


def test_a_declared_evidence_type_outranks_the_recognition_default():
    # A transfer prompt answered correctly is a transfer, not a recognition.
    transferred = evidence_from_graded_answer(correct=True, evidence_type="transfer")
    assert derive_mastery_state([transferred]) == "TRANSFERRED"


# ─── The client and server must mean the same thing ──────────────────────────
#
# These are the definitions that would diverge silently: the ladder's order
# decides what counts as stronger proof, and the mastery rule decides what the
# word "mastered" means to a learner. If the two repos disagree, a learner's
# progress means one thing to the server and another on screen.

def test_ladder_order_is_the_one_the_client_uses():
    assert EVIDENCE_KINDS == (
        "exposure",
        "recognition",
        "explanation",
        "application",
        "transfer",
        "retention",
    )


def test_mastery_rule_is_the_one_the_client_uses():
    assert MASTERY_REQUIRES == ("application", "transfer", "retention")
    assert MASTERY_CONFIDENCE_FLOOR == 0.7


# ─── The projection exists and is wired ──────────────────────────────────────

def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_processor_projects_evidence_into_the_classrooms_mastery_table():
    # The link that was missing: the classroom reads ai_classroom.MasteryState
    # but nothing on the live path wrote it, so it could not see what chat
    # taught. Losing this call silently restores that split.
    processor = _source("lyo_app/events/processor.py")
    assert "project_event_to_mastery_state(db, event)" in processor


def test_processor_still_updates_the_mastery_chat_depends_on():
    # The projection is additive. Chat's spaced repetition reads
    # personalization.LearnerMastery, and removing this DKT update would break
    # the one mastery path that actually works today.
    processor = _source("lyo_app/events/processor.py")
    assert "personalization_engine.dkt.update_mastery" in processor


def test_evidence_type_is_normalized_before_storage():
    # Stored normalized so every reader sees one vocabulary, and an
    # unrecognised type lands as NULL rather than a guess.
    processor = _source("lyo_app/events/processor.py")
    assert "evidence_type=normalize_evidence_kind(event_in.evidence_type)" in processor


def test_projection_never_fails_the_learners_turn():
    # The evidence is already durable on the event row, so a failed projection
    # is replayable. Losing the learner's answer because a secondary table was
    # unavailable would be the worse outcome.
    projection = _source("lyo_app/events/mastery_projection.py")
    assert "except Exception:" in projection
    assert "return False" in projection
