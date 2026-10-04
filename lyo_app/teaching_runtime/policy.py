"""Deterministic pedagogical policy for Lyo.

The model is a content engine. This module decides *what teaching move happens
next*. The rules are intentionally conservative: learner control wins, a
mistake triggers remediation rather than advancement, and repeated explanation
or repeated checking forces a modality change.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import TeachingAction, TeachingContext, TeachingDecision

POLICY_VERSION = "learning-os-v1"

_DIRECT_RE = re.compile(
    r"\b(just (?:tell|explain|show)|give me (?:the )?answer|tell me directly|"
    r"explain it|just answer|solo dime|expl[ií]camelo|dame la respuesta)\b",
    re.IGNORECASE,
)
_VISUAL_RE = re.compile(
    r"\b(show me|visual|diagram|graph|draw|picture|imagen|diagrama|gr[aá]fica)\b",
    re.IGNORECASE,
)
_ATTACHMENT_REFERENCE_RE = re.compile(
    r"\b(?:"
    r"what\s+(?:is|are|does|do)\s+(?:this|that|it)|what['’]?s\s+(?:this|that)|"
    r"(?:analy[sz]e|analize|summari[sz]e|review|explain|describe|read|interpret|identify|check)\s+"
    r"(?:this|that|it|the\s+(?:attached\s+)?(?:file|document|pdf|image|photo|screenshot))|"
    r"(?:this|that|the\s+attached)\s+(?:file|document|pdf|image|photo|screenshot)|"
    r"page\s+\d+|"
    r"qu[eé]\s+es\s+esto|qu[eé]\s+dice\s+(?:esto|este\s+documento)|"
    r"(?:analiza|resume|explica|describe|lee|interpreta)\s+(?:esto|este\s+(?:archivo|documento|pdf))"
    r")\b",
    re.IGNORECASE,
)
_CONFUSED_RE = re.compile(
    r"\b(i (?:don't|do not) (?:get|understand)|i'?m confused|doesn'?t make sense|"
    r"lost me|no entiendo|estoy confundid[oa]|no tiene sentido)\b",
    re.IGNORECASE,
)
_STOP_RE = re.compile(
    r"^\s*(stop|pause|enough|quit|cancel|para|detente|pausa)\s*[.!]?\s*$",
    re.IGNORECASE,
)

_WORKFLOW_INTENTS = {
    "COURSE",
    "STUDY_PLAN",
    "TEST_PREP",
    "SUMMARIZE_NOTES",
    "SCHEDULE_REMINDERS",
    "COMMUNITY",
    "MODIFY_ARTIFACT",
}
_REVIEW_INTENTS = {"FLASHCARDS", "WEEKLY_REVIEW", "REFLECT"}


def _decision(
    action: TeachingAction,
    reason: str,
    *,
    interaction: bool = False,
    words: int = 120,
    instrument: Optional[str] = None,
    evidence: Optional[str] = None,
    model_tier: str = "teaching",
    directives: Optional[list[str]] = None,
) -> TeachingDecision:
    return TeachingDecision(
        action=action,
        reason_code=reason,
        interaction_required=interaction,
        max_exposition_words=words,
        preferred_instrument=instrument,
        target_evidence_type=evidence,
        model_tier=model_tier,
        directives=directives or [],
        policy_version=POLICY_VERSION,
    )


class TeachingPolicy:
    """Pure policy: same input state always produces the same next move."""

    @classmethod
    def decide(cls, context: TeachingContext) -> TeachingDecision:
        session = context.session
        learner = context.learner
        text = (context.user_text or "").strip()
        intent = (context.intent or "GENERAL").upper()

        # Learner control is authoritative. The policy may later resume
        # teaching, but it must not turn a direct request into a forced quiz.
        if session.learner_wants_to_stop or _STOP_RE.search(text):
            return _decision(
                TeachingAction.PAUSE,
                "learner_requested_pause",
                words=40,
                model_tier="reflex",
                directives=["Acknowledge the pause. Do not introduce a new task."],
            )

        contract = context.metadata.get("interaction_contract") or {}
        contract_mode = str(contract.get("mode") or "").lower()
        contract_depth = str(contract.get("depth") or "standard").lower()
        contract_answer_first = bool(contract.get("answer_first"))
        contract_words = {"compact": 90, "deep": 260}.get(contract_depth, 170)

        # The interaction contract is upstream of pedagogy: it captures what
        # the learner explicitly asked the product to do. Pedagogy may improve
        # *how* we answer, but may not silently replace an answer/summary/
        # comparison with a diagnostic or quiz.
        if contract_answer_first and contract_mode in {
            "answer", "explain", "summarize", "compare", "search",
        }:
            return _decision(
                TeachingAction.EXPLAIN if contract_mode == "explain" else TeachingAction.ANSWER,
                "interaction_contract_answer_first",
                words=contract_words,
                model_tier="deliberation" if contract_depth == "deep" else "teaching",
                directives=[
                    f"Honor the {contract_mode} request before any assessment.",
                    "Do not ask a diagnostic or comprehension question in this turn.",
                    "Optional learning actions may be offered only after the requested answer.",
                ],
            )
        direct = session.learner_requested_direct_answer or bool(_DIRECT_RE.search(text))
        visual = session.learner_requested_visual or bool(_VISUAL_RE.search(text))
        confused = session.learner_expressed_confusion or bool(_CONFUSED_RE.search(text))
        has_media = bool(context.metadata.get("has_media"))
        has_current_media = bool(context.metadata.get("has_current_media"))
        attachment_referential = bool(_ATTACHMENT_REFERENCE_RE.search(text))

        # Files are objects the learner is asking Lyo to inspect, not concepts
        # that should be diagnosed before they are identified. A newly attached
        # file is authoritative context for the current turn. On later turns we
        # reuse it only when the learner explicitly refers back to the material,
        # so an old attachment cannot hijack an unrelated lesson.
        #
        # Explicit workflows keep ownership: "quiz me on this PDF", "make
        # flashcards", "create a course", and Test Prep still route through
        # their requested workflow rather than this direct-answer path.
        if (
            has_media
            and (has_current_media or attachment_referential)
            and intent not in (_WORKFLOW_INTENTS | _REVIEW_INTENTS | {"QUIZ"})
        ):
            return _decision(
                TeachingAction.ANSWER,
                "attachment_information_request",
                words=220,
                model_tier="teaching",
                directives=[
                    "Inspect the attached material and answer the learner's actual question first.",
                    "Treat demonstratives such as 'this' or 'it' as referring to the attachment.",
                    "Do not ask a diagnostic, comprehension, or calibration question before answering.",
                    "Do not quiz the learner unless they explicitly requested a quiz or test.",
                    "After the direct answer, optional next steps may be offered briefly.",
                ],
            )

        if intent in {"GREETING", "CHAT", "GENERAL", "HELP", "UNKNOWN"} and not (
            confused or learner.concept_id
        ):
            return _decision(
                TeachingAction.ANSWER,
                "non_instructional_turn",
                words=140,
                model_tier="reflex" if intent == "GREETING" else "teaching",
                directives=["Answer naturally; do not manufacture a quiz."],
            )

        if direct:
            return _decision(
                TeachingAction.EXPLAIN,
                "learner_requested_direct_explanation",
                words=180,
                instrument="visual" if visual else None,
                directives=[
                    "Answer directly before asking anything.",
                    "Use one compact example; do not force an assessment in this turn.",
                ],
            )

        # Some router intents own a concrete workflow. The Learning OS may
        # inform that workflow with learner state, but it must not replace the
        # learner's explicit request with an unrelated first-contact diagnosis.
        if intent in _WORKFLOW_INTENTS:
            return _decision(
                TeachingAction.ANSWER,
                "learner_requested_workflow",
                words=120,
                directives=[
                    "Honor the routed workflow exactly; do not replace it with a diagnostic turn."
                ],
            )

        if intent == "QUIZ":
            if learner.next_rung == "transfer":
                return _decision(
                    TeachingAction.CHECK_TRANSFER,
                    "learner_requested_quiz",
                    interaction=True,
                    words=65,
                    instrument="novel_scenario",
                    evidence="transfer",
                )
            if learner.next_rung == "application":
                return _decision(
                    TeachingAction.CHECK_APPLICATION,
                    "learner_requested_quiz",
                    interaction=True,
                    words=65,
                    instrument="short_answer",
                    evidence="application",
                )
            return _decision(
                TeachingAction.CHECK_RECALL,
                "learner_requested_quiz",
                interaction=True,
                words=55,
                instrument="diagnostic_choice",
                evidence="recognition",
            )

        if intent in _REVIEW_INTENTS:
            return _decision(
                TeachingAction.REVIEW,
                "learner_requested_review",
                interaction=True,
                words=70,
                instrument="flashcards" if intent == "FLASHCARDS" else "retrieval",
                directives=[
                    "Honor the review request; use existing evidence to choose what to revisit."
                ],
            )

        if confused or learner.misconception:
            return _decision(
                TeachingAction.REMEDIATE,
                "misconception_or_confusion",
                interaction=True,
                words=100,
                instrument="visual" if visual or learner.misconception else "worked_example",
                evidence="application",
                model_tier="deliberation" if learner.misconception else "teaching",
                directives=[
                    "Address the specific reasoning gap, not merely the correct answer.",
                    "After the repair, give one smaller attempt that tests the repaired step.",
                ],
            )

        if learner.prerequisite_gaps:
            gap = learner.prerequisite_gaps[0]
            gap_name = gap.display_name or gap.concept_id
            return _decision(
                TeachingAction.REMEDIATE,
                "prerequisite_gap",
                interaction=True,
                words=95,
                instrument="prerequisite_bridge",
                evidence="application",
                directives=[
                    f"Bridge the missing prerequisite '{gap_name}' before pushing the target concept.",
                    "Keep the bridge narrow: teach only the prerequisite step needed for the current goal.",
                    "End with one application that verifies the prerequisite can now support the target.",
                ],
            )

        # Anti-quiz-loop and anti-monologue rules. These are policy constraints,
        # not prompt preferences, so callers can inspect and test them.
        if session.consecutive_checks >= 2:
            return _decision(
                TeachingAction.DEMONSTRATE,
                "avoid_repeated_check_loop",
                interaction=False,
                words=110,
                instrument="worked_example",
                directives=[
                    "Change modality: model or demonstrate before asking another question."
                ],
            )
        if session.consecutive_explanations >= 1:
            return _decision(
                TeachingAction.GUIDE,
                "collect_evidence_after_explanation",
                interaction=True,
                words=70,
                instrument="short_answer",
                evidence="application",
                directives=[
                    "Do not add another long explanation.",
                    "Give the learner one concrete action that reveals understanding.",
                ],
            )

        # First contact is calibration, not a beginner lecture. The learner can
        # always bypass this through the direct-answer rule above.
        if learner.evidence_state in {"NOT_SEEN", "EXPOSED"} and learner.attempts == 0:
            return _decision(
                TeachingAction.DIAGNOSE,
                "insufficient_evidence",
                interaction=True,
                words=55,
                instrument="diagnostic_choice",
                evidence="recognition",
                directives=[
                    "Ask one discriminating question before choosing depth.",
                    "Include an explicit opt-out such as 'not sure—show me'.",
                ],
            )

        score = learner.mastery_score
        if score is None:
            # Evidence state is more trustworthy than inventing a numeric score.
            if learner.strongest_rung in {"transfer", "retention"}:
                return _decision(
                    TeachingAction.CHECK_TRANSFER,
                    "strong_evidence_without_numeric_mastery",
                    interaction=True,
                    words=65,
                    instrument="scenario",
                    evidence="transfer",
                )
            return _decision(
                TeachingAction.GUIDE,
                "partial_evidence_without_numeric_mastery",
                interaction=True,
                words=85,
                instrument="guided_attempt",
                evidence=learner.next_rung or "application",
            )

        if score < 0.35:
            return _decision(
                TeachingAction.DEMONSTRATE,
                "low_mastery",
                words=110,
                instrument="visual" if visual else "worked_example",
                evidence="application",
                directives=["Model one example, then hand off a closely matched step."],
            )
        if score < 0.70:
            return _decision(
                TeachingAction.GUIDE,
                "developing_mastery",
                interaction=True,
                words=80,
                instrument="guided_attempt",
                evidence="application",
            )
        if score < 0.90:
            return _decision(
                TeachingAction.CHECK_APPLICATION,
                "ready_for_independent_application",
                interaction=True,
                words=65,
                instrument="short_answer",
                evidence="application",
            )

        if learner.strongest_rung == "retention":
            return _decision(
                TeachingAction.ADVANCE,
                "durable_evidence_present",
                words=60,
                directives=["Connect to the next concept rather than reteaching this one."],
            )

        return _decision(
            TeachingAction.CHECK_TRANSFER,
            "high_mastery_needs_transfer_evidence",
            interaction=True,
            words=65,
            instrument="novel_scenario",
            evidence="transfer",
        )


_CLASSROOM_MOVE_MAP = {
    "diagnose": TeachingAction.DIAGNOSE,
    "orient": TeachingAction.DEMONSTRATE,
    "model": TeachingAction.DEMONSTRATE,
    "guided": TeachingAction.GUIDE,
    "faded": TeachingAction.CHECK_APPLICATION,
    "independent": TeachingAction.CHECK_APPLICATION,
    "transfer": TeachingAction.CHECK_TRANSFER,
    "interleave": TeachingAction.REVIEW,
    "reteach": TeachingAction.REMEDIATE,
    "prerequisite": TeachingAction.REMEDIATE,
    "closing_win": TeachingAction.GUIDE,
}


def canonical_action_for_classroom_move(
    move: Optional[str], phase: Optional[str] = None
) -> TeachingAction:
    """Map the mature classroom state machine onto the shared action language.

    Classroom remains authoritative over its state transitions. This adapter is
    intentionally one-way: it makes the two surfaces observable in one
    vocabulary without replacing classroom correctness with model autonomy.
    """
    key = (move or phase or "").strip().lower()
    return _CLASSROOM_MOVE_MAP.get(key, TeachingAction.EXPLAIN)
