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
    # Reported, not raised: the caller decides what to do about it.
    assert "return ProjectionOutcome.FAILED" in projection
    assert "raise" not in projection.split("except Exception:")[1]


# ─── Chat emits evidence, exactly once ───────────────────────────────────────

def test_chat_check_emits_evidence():
    # The whole point of the shared event stream: a concept demonstrated in
    # Chat has to become visible to the Classroom.
    source = _source("lyo_app/api/v1/stream_lyo2.py")
    assert "log_learning_event(" in source
    assert 'source_surface="chat"' in source
    assert "evidence_from_graded_answer(" in source


def test_chat_check_emits_evidence_once():
    """The chat check must not apply one answer to mastery twice.

    `trace_knowledge` already runs the DKT update for this answer.
    `skill_ids_json` is what asks the event processor to run *another* one, so
    passing it from here would double-count the learner's single answer —
    inflating their mastery on every check they take.

    The evidence still reaches the classroom's table, because the projection
    keys on `concept_id`, not on `skill_ids_json`.
    """
    source = _source("lyo_app/api/v1/stream_lyo2.py")

    check_body = source[source.index("async def check_lyo2_answer") :]
    if "\nasync def " in check_body[1:]:
        check_body = check_body[: check_body.index("\nasync def ", 1)]

    assert "concept_id=skill_id" in check_body, "evidence must name the concept"
    # Assert on the keyword argument, not the bare name: the code comment
    # explaining this rule necessarily mentions `skill_ids_json` in prose, and
    # a substring check would trip on the very explanation it is enforcing.
    assert "skill_ids_json=" not in check_body, (
        "passing skill_ids_json from the chat check double-applies the DKT "
        "update that trace_knowledge already performed"
    )


def test_processor_only_runs_dkt_when_asked():
    # The guard that makes the above safe. If this becomes unconditional,
    # every chat check silently counts twice.
    processor = _source("lyo_app/events/processor.py")
    assert "if event.skill_ids_json:" in processor


def test_a_bailed_out_check_logs_no_evidence():
    # Opting out is not evidence about what the learner knows. The endpoint
    # returns before the mastery block, and the ladder refuses it too.
    assert evidence_from_graded_answer(correct=False, bailed_out=True) is None
    source = _source("lyo_app/api/v1/stream_lyo2.py")
    assert "if bailed_out or not skill_id:" in source


# ─── Failure modes found in review ───────────────────────────────────────────
#
# Three bug_risk findings, each confirmed against the code rather than taken on
# trust. They share a shape: the projection is a secondary write on a live
# request path, so every way it can fail has to leave the primary path intact
# and the failure findable.

def test_new_enum_value_is_added_to_the_postgres_type():
    """EventType gained CLASSROOM_DEMONSTRATION; the database type must too.

    event_type is a SQLAlchemy Enum, which on PostgreSQL is a native
    `eventtype` type. Adding a Python member does not add it to the database
    type, so the first insert carrying it fails with `invalid input value for
    enum eventtype` — which would not surface until the classroom starts
    emitting demonstrations, in production, on a learner's turn.
    """
    migration = _source("alembic/versions/evidence_001_learning_event_evidence.py")
    assert "ADD VALUE IF NOT EXISTS 'CLASSROOM_DEMONSTRATION'" in migration
    # ALTER TYPE ... ADD VALUE cannot run in the transaction that later uses
    # the value.
    assert "autocommit_block()" in migration
    # Other backends store the value as text and need nothing.
    assert 'dialect.name != "postgresql"' in migration

    # And it must actually run. Asserting only that the helper exists would
    # pass just as happily with the call deleted from upgrade().
    upgrade_body = migration[migration.index("def upgrade()") :]
    upgrade_body = upgrade_body[: upgrade_body.index("\ndef ")]
    assert "_add_enum_value_if_postgres()" in upgrade_body


def test_projection_survives_the_insert_race():
    """MasteryState carries uq_user_concept_mastery on (user_id, concept_id).

    Two events for the same learner and concept can both see no row and both
    insert; the loser gets an IntegrityError. Caught and re-read, so the race
    resolves to the winner's row instead of failing.
    """
    projection = _source("lyo_app/events/mastery_projection.py")
    assert "IntegrityError" in projection
    assert "uq_user_concept_mastery" in projection, (
        "the constraint that makes this a real race should be named, so the "
        "handling is not mistaken for defensive noise"
    )


def test_projection_cannot_poison_the_callers_transaction():
    """A failed flush would otherwise leave the AsyncSession unusable.

    The processor commits its own status straight after this runs, so a
    poisoned session would take that commit down too — and then the error
    handler's commit as well.
    """
    projection = _source("lyo_app/events/mastery_projection.py")
    assert "db.begin_nested()" in projection


def test_a_failed_projection_is_not_recorded_as_processed():
    """Marking it processed would hide the failure permanently.

    The DKT update lands but the classroom's mastery does not, so the two
    surfaces disagree for that concept until the event is replayed. A distinct
    status is what lets a replay worker find it; without one the row reads as
    done and nothing can identify it again.
    """
    processor = _source("lyo_app/events/processor.py")

    # Look at the assignment itself. Checking that the constant appears
    # anywhere in the file would pass even with the assignment changed back to
    # PROCESSED, because the constant is still defined at the top.
    assignment = processor[processor.index("event.processed_for_mastery = (") :]
    assignment = assignment[: assignment.index("await db.commit()")]

    assert "PROCESSED_PENDING_PROJECTION" in assignment, (
        "a failed projection must not be recorded as fully processed"
    )
    assert "ProjectionOutcome.FAILED" in assignment


def test_projection_outcomes_distinguish_nothing_to_do_from_failure():
    # An event with no concept is not a failed projection, and must not be
    # marked for replay — most events carry no evidence at all.
    from lyo_app.events.mastery_projection import ProjectionOutcome

    assert ProjectionOutcome.NOTHING_TO_PROJECT != ProjectionOutcome.FAILED
    assert ProjectionOutcome.PROJECTED != ProjectionOutcome.FAILED


# ─── Being taught must never make a learner look worse ───────────────────────
#
# The ladder's `exposure` rung means "instruction was delivered". A graded
# wrong answer lands there too — a learner who missed it has still met the
# idea. Those are different events and the projection has to tell them apart,
# or teaching someone a concept degrades their record of it.
#
# These exercise the fold against a stand-in row, so they check what the code
# does rather than what it says.

class _FakeMastery:
    """Just the columns _fold_evidence touches."""

    def __init__(self, mastery_score=0.5, confidence=0.5, trend="stable"):
        self.mastery_score = mastery_score
        self.confidence = confidence
        self.trend = trend
        self.attempts = 0
        self.correct_count = 0
        self.incorrect_count = 0
        self.last_seen = None
        self.last_correct = None
        self.error_pattern = None
        self.misconception_tags = None


def _fold(**kwargs):
    from lyo_app.events.mastery_projection import _fold_evidence

    row = kwargs.pop("row", None) or _FakeMastery()
    _fold_evidence(
        row,
        kwargs.pop("kind", "exposure"),
        kwargs.pop("confidence", 0.0),
        kwargs.pop("misconception", None),
        attempted=kwargs.pop("attempted", False),
    )
    assert not kwargs, f"unexpected kwargs {kwargs}"
    return row


def test_instruction_only_exposure_does_not_count_as_a_wrong_answer():
    row = _fold(kind="exposure", attempted=False)

    assert row.incorrect_count == 0, "being taught is not getting it wrong"
    assert row.attempts == 0, "being taught is not an attempt"
    assert row.mastery_score == 0.5, "being taught must not move the score"
    assert row.trend == "stable", "being taught must not read as declining"
    # It did happen, though — the learner has now met this concept.
    assert row.last_seen is not None


def test_a_graded_wrong_answer_still_counts_against_the_learner():
    row = _fold(kind="exposure", confidence=0.0, attempted=True)

    assert row.attempts == 1
    assert row.incorrect_count == 1
    assert row.mastery_score < 0.5
    assert row.trend == "declining"


def test_a_correct_demonstration_moves_the_score_up():
    row = _fold(kind="transfer", confidence=1.0, attempted=True)

    assert row.correct_count == 1
    assert row.incorrect_count == 0
    assert row.mastery_score > 0.5
    assert row.trend == "improving"
    assert row.last_correct is not None


def test_a_stronger_rung_moves_the_score_further():
    weak = _fold(kind="recognition", confidence=1.0, attempted=True)
    strong = _fold(kind="transfer", confidence=1.0, attempted=True)

    # The ladder is only meaningful if it changes the outcome.
    assert strong.mastery_score > weak.mastery_score


def test_projection_derives_attempted_from_the_graded_outcome():
    # measurable_outcome is None when the learner was never asked, which is
    # what separates instruction from a failed attempt.
    projection = _source("lyo_app/events/mastery_projection.py")
    assert 'getattr(event, "measurable_outcome", None) is not None' in projection

    # Slice to the call's own closing paren at its indentation, not the first
    # ")" — that one belongs to a nested getattr().
    call = projection[projection.index("_fold_evidence(\n                mastery") :]
    call = call[: call.index("\n            )")]
    assert "attempted=attempted" in call


def test_projection_flushes_inside_its_own_guard():
    # Otherwise a constraint violation surfaces at the processor's later
    # commit — outside this handler, on the session it exists to protect.
    projection = _source("lyo_app/events/mastery_projection.py")
    guarded = projection[projection.index("async with db.begin_nested():\n            mastery") :]
    guarded = guarded[: guarded.index("return ProjectionOutcome.PROJECTED")]
    assert "await db.flush()" in guarded
