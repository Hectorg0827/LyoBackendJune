from lyo_app.teaching_runtime.models import (
    LearnerSnapshot,
    PrerequisiteGap,
    SessionSnapshot,
    TeachingAction,
    TeachingContext,
    TeachingSurface,
)
from lyo_app.teaching_runtime.policy import (
    POLICY_VERSION,
    TeachingPolicy,
    canonical_action_for_classroom_move,
)
from lyo_app.teaching_runtime.service import (
    bounded_intervention_metadata,
    record_policy_outcome,
    session_snapshot,
    teaching_policy_outcomes,
)


def context(
    *,
    text="teach me fractions",
    intent="EXPLAIN",
    mastery=None,
    evidence_state="NOT_SEEN",
    strongest=None,
    next_rung=None,
    misconception=None,
    prerequisite_gaps=None,
    attempts=0,
    checks=0,
    explanations=0,
):
    return TeachingContext(
        intent=intent,
        user_text=text,
        learner=LearnerSnapshot(
            concept_id="fractions",
            mastery_score=mastery,
            evidence_state=evidence_state,
            strongest_rung=strongest,
            next_rung=next_rung,
            misconception=misconception,
            prerequisite_gaps=prerequisite_gaps or [],
            attempts=attempts,
        ),
        session=SessionSnapshot(
            surface=TeachingSurface.CHAT,
            consecutive_checks=checks,
            consecutive_explanations=explanations,
        ),
    )


def test_first_contact_diagnoses_instead_of_lecturing():
    decision = TeachingPolicy.decide(context())
    assert decision.action is TeachingAction.DIAGNOSE
    assert decision.interaction_required is True
    assert decision.target_evidence_type == "recognition"
    assert decision.max_exposition_words <= 60
    assert decision.policy_version == POLICY_VERSION


def test_direct_answer_request_overrides_diagnostic():
    decision = TeachingPolicy.decide(context(text="Just explain it to me"))
    assert decision.action is TeachingAction.EXPLAIN
    assert decision.interaction_required is False
    assert "direct" in decision.reason_code


def test_confusion_or_misconception_repairs_before_advancing():
    decision = TeachingPolicy.decide(
        context(
            text="I don't understand this",
            mastery=0.82,
            evidence_state="APPLIED",
            strongest="application",
            misconception="confuses numerator with denominator",
            attempts=4,
        )
    )
    assert decision.action is TeachingAction.REMEDIATE
    assert decision.model_tier == "deliberation"
    assert decision.target_evidence_type == "application"


def test_prerequisite_gap_bridges_before_target_practice():
    decision = TeachingPolicy.decide(
        context(
            mastery=0.88,
            evidence_state="APPLIED",
            strongest="application",
            attempts=5,
            prerequisite_gaps=[
                PrerequisiteGap(
                    concept_id="equivalent-fractions",
                    display_name="Equivalent fractions",
                    evidence_state="RECOGNIZED",
                    strongest_rung="recognition",
                )
            ],
        )
    )
    assert decision.action is TeachingAction.REMEDIATE
    assert decision.reason_code == "prerequisite_gap"
    assert decision.preferred_instrument == "prerequisite_bridge"
    assert decision.target_evidence_type == "application"
    assert "Equivalent fractions" in " ".join(decision.directives)


def test_two_checks_force_modality_change():
    decision = TeachingPolicy.decide(
        context(
            mastery=0.8,
            evidence_state="APPLIED",
            strongest="application",
            attempts=4,
            checks=2,
        )
    )
    assert decision.action is TeachingAction.DEMONSTRATE
    assert decision.reason_code == "avoid_repeated_check_loop"


def test_explanation_is_followed_by_learner_action_not_more_monologue():
    decision = TeachingPolicy.decide(
        context(
            mastery=0.45,
            evidence_state="RECOGNIZED",
            strongest="recognition",
            attempts=2,
            explanations=1,
        )
    )
    assert decision.action is TeachingAction.GUIDE
    assert decision.interaction_required is True
    assert decision.max_exposition_words <= 70


def test_low_mastery_models_before_independent_check():
    decision = TeachingPolicy.decide(
        context(
            mastery=0.2,
            evidence_state="RECOGNIZED",
            strongest="recognition",
            attempts=2,
        )
    )
    assert decision.action is TeachingAction.DEMONSTRATE


def test_developing_mastery_uses_guided_attempt():
    decision = TeachingPolicy.decide(
        context(
            mastery=0.5,
            evidence_state="EXPLAINED",
            strongest="explanation",
            attempts=3,
        )
    )
    assert decision.action is TeachingAction.GUIDE
    assert decision.target_evidence_type == "application"


def test_strong_mastery_requires_transfer_not_reteaching():
    decision = TeachingPolicy.decide(
        context(
            mastery=0.96,
            evidence_state="APPLIED",
            strongest="application",
            attempts=6,
        )
    )
    assert decision.action is TeachingAction.CHECK_TRANSFER
    assert decision.target_evidence_type == "transfer"


def test_retention_evidence_allows_advance():
    decision = TeachingPolicy.decide(
        context(
            mastery=0.96,
            evidence_state="RETAINED",
            strongest="retention",
            attempts=7,
        )
    )
    assert decision.action is TeachingAction.ADVANCE


def test_course_workflow_is_not_replaced_by_first_contact_diagnosis():
    decision = TeachingPolicy.decide(
        context(text="Create a course on geometry", intent="COURSE")
    )
    assert decision.action is TeachingAction.ANSWER
    assert decision.reason_code == "learner_requested_workflow"


def test_quiz_request_uses_evidence_target_instead_of_generic_diagnosis():
    first = TeachingPolicy.decide(
        context(text="Quiz me on fractions", intent="QUIZ")
    )
    assert first.action is TeachingAction.CHECK_RECALL
    assert first.target_evidence_type == "recognition"

    transfer = TeachingPolicy.decide(
        context(
            text="Quiz me on fractions",
            intent="QUIZ",
            evidence_state="APPLIED",
            strongest="application",
            next_rung="transfer",
            attempts=4,
        )
    )
    assert transfer.action is TeachingAction.CHECK_TRANSFER
    assert transfer.target_evidence_type == "transfer"


def test_flashcard_request_enters_review_not_diagnosis():
    decision = TeachingPolicy.decide(
        context(text="Make flashcards on fractions", intent="FLASHCARDS")
    )
    assert decision.action is TeachingAction.REVIEW
    assert decision.reason_code == "learner_requested_review"


def test_non_instructional_chat_does_not_manufacture_quiz():
    decision = TeachingPolicy.decide(
        TeachingContext(
            intent="GREETING",
            user_text="hey",
            learner=LearnerSnapshot(),
            session=SessionSnapshot(surface=TeachingSurface.CHAT),
        )
    )
    assert decision.action is TeachingAction.ANSWER
    assert decision.interaction_required is False


def test_pause_is_reflex_and_stops_new_task():
    decision = TeachingPolicy.decide(context(text="pause"))
    assert decision.action is TeachingAction.PAUSE
    assert decision.model_tier == "reflex"


def test_session_state_prefers_canonical_client_state():
    snapshot = session_snapshot(
        surface=TeachingSurface.CHAT,
        user_text="continue",
        history=[
            {"role": "user", "content": "teach me"},
            {"role": "assistant", "content": "Old text that should not override state."},
        ],
        state_summary={
            "teaching_runtime": {
                "last_action": "check_application",
                "consecutive_checks": 2,
                "consecutive_explanations": 0,
            }
        },
    )
    assert snapshot.last_action is TeachingAction.CHECK_APPLICATION
    assert snapshot.consecutive_checks == 2
    assert snapshot.consecutive_explanations == 0


def test_classroom_state_maps_to_same_action_vocabulary():
    assert canonical_action_for_classroom_move("diagnose") is TeachingAction.DIAGNOSE
    assert canonical_action_for_classroom_move("guided") is TeachingAction.GUIDE
    assert canonical_action_for_classroom_move("reteach") is TeachingAction.REMEDIATE
    assert canonical_action_for_classroom_move("transfer") is TeachingAction.CHECK_TRANSFER


def test_intervention_metadata_contains_only_bounded_policy_identity():
    decision = TeachingPolicy.decide(
        context(
            mastery=0.5,
            evidence_state="EXPLAINED",
            strongest="explanation",
            attempts=3,
        )
    )
    metadata = bounded_intervention_metadata(decision)
    assert set(metadata) == {
        "action",
        "reason_code",
        "target_evidence_type",
        "preferred_instrument",
        "model_tier",
        "policy_version",
    }
    assert "teach me fractions" not in str(metadata)


def test_policy_outcome_counter_uses_measured_result_not_learner_text():
    intervention = {
        "action": "guide",
        "reason_code": "developing_mastery",
        "policy_version": POLICY_VERSION,
    }
    before = teaching_policy_outcomes.labels(
        "chat", "guide", "developing_mastery",
        "application", "correct", POLICY_VERSION,
    )._value.get()
    record_policy_outcome(
        surface=TeachingSurface.CHAT,
        intervention=intervention,
        evidence_type="application",
        succeeded=True,
    )
    after = teaching_policy_outcomes.labels(
        "chat", "guide", "developing_mastery",
        "application", "correct", POLICY_VERSION,
    )._value.get()
    assert after == before + 1
