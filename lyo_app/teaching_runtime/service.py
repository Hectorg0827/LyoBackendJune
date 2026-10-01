"""State loading, session summarisation, and policy-event recording."""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    LearnerSnapshot,
    SessionSnapshot,
    TeachingAction,
    TeachingContext,
    TeachingDecision,
    TeachingSurface,
)
from .policy import TeachingPolicy

logger = logging.getLogger(__name__)

_QUESTION_RE = re.compile(r"[?？]\s*$")
_DIRECT_RE = re.compile(
    r"\b(just (?:tell|explain|show)|give me (?:the )?answer|tell me directly|"
    r"explain it|just answer|solo dime|expl[ií]camelo|dame la respuesta)\b",
    re.IGNORECASE,
)
_VISUAL_RE = re.compile(
    r"\b(show me|visual|diagram|graph|draw|picture|imagen|diagrama|gr[aá]fica)\b",
    re.IGNORECASE,
)
_CONFUSED_RE = re.compile(
    r"\b(i (?:don't|do not) (?:get|understand)|i'?m confused|doesn'?t make sense|"
    r"lost me|no entiendo|estoy confundid[oa]|no tiene sentido)\b",
    re.IGNORECASE,
)


def session_snapshot(
    *,
    surface: TeachingSurface,
    user_text: str,
    history: Optional[Iterable[Any]] = None,
    state_summary: Optional[Mapping[str, Any]] = None,
) -> SessionSnapshot:
    """Build bounded session state without asking a model to infer control flow."""

    history_list = list(history or [])
    assistant_texts: list[str] = []
    for turn in history_list[-8:]:
        role = getattr(turn, "role", None)
        content = getattr(turn, "content", None)
        if isinstance(turn, Mapping):
            role = turn.get("role", role)
            content = turn.get("content", content)
        if role == "assistant" and content:
            assistant_texts.append(str(content).strip())

    # Until every client echoes teaching_runtime state, use a conservative
    # heuristic. A persisted canonical last_action always wins when available.
    runtime_state = (
        dict((state_summary or {}).get("teaching_runtime") or {})
        if isinstance(state_summary, Mapping)
        else {}
    )
    last_action = None
    try:
        if runtime_state.get("last_action"):
            last_action = TeachingAction(runtime_state["last_action"])
    except (TypeError, ValueError):
        last_action = None

    consecutive_checks = int(runtime_state.get("consecutive_checks") or 0)
    consecutive_explanations = int(runtime_state.get("consecutive_explanations") or 0)
    if not runtime_state:
        for text in reversed(assistant_texts[-3:]):
            if _QUESTION_RE.search(text):
                if consecutive_explanations:
                    break
                consecutive_checks += 1
            else:
                if consecutive_checks:
                    break
                consecutive_explanations += 1

    user_text = user_text or ""
    return SessionSnapshot(
        surface=surface,
        turn_count=sum(
            1
            for turn in history_list
            if (
                (turn.get("role") if isinstance(turn, Mapping) else getattr(turn, "role", None))
                == "user"
            )
        ),
        consecutive_explanations=max(0, min(consecutive_explanations, 8)),
        consecutive_checks=max(0, min(consecutive_checks, 8)),
        last_action=last_action,
        learner_requested_direct_answer=bool(_DIRECT_RE.search(user_text)),
        learner_requested_visual=bool(_VISUAL_RE.search(user_text)),
        learner_expressed_confusion=bool(_CONFUSED_RE.search(user_text)),
    )


async def load_learner_snapshot(
    db: Optional[AsyncSession], user_id: Any, concept_id: Optional[str]
) -> LearnerSnapshot:
    snapshot = LearnerSnapshot(concept_id=concept_id)
    if db is None or not concept_id or user_id in (None, "", 0, "0"):
        return snapshot

    # Evidence first: unlike a single score it tells us what the learner has
    # actually demonstrated (recognition/application/transfer/retention).
    try:
        from lyo_app.events.concept_record import learner_record

        record = await learner_record(db, user_id, limit=100)
        if not record.unavailable:
            match = next((c for c in record.concepts if c.concept_id == concept_id), None)
            if match is not None:
                snapshot.evidence_state = match.state
                snapshot.strongest_rung = match.best_rung
                snapshot.next_rung = match.next_rung
                snapshot.misconception = match.misconception
                snapshot.last_seen = match.last_seen
    except Exception as exc:
        logger.warning("Teaching runtime could not read evidence record: %s", type(exc).__name__)

    try:
        from lyo_app.personalization.models import LearnerMastery
        from lyo_app.personalization.service import _coerce_learner_id

        learner_id = _coerce_learner_id(user_id)
        if learner_id is not None:
            result = await db.execute(
                select(LearnerMastery).where(
                    LearnerMastery.user_id == learner_id,
                    LearnerMastery.skill_id == concept_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                snapshot.mastery_score = max(0.0, min(1.0, float(row.mastery_level or 0.0)))
                snapshot.attempts = max(0, int(row.attempts or 0))
                snapshot.hints_used = max(0, int(row.hints_used or 0))
                snapshot.uncertainty = max(0.0, min(1.0, float(row.uncertainty or 0.0)))
                if not snapshot.misconception:
                    misconceptions = list(row.misconceptions or [])
                    if misconceptions:
                        snapshot.misconception = str(misconceptions[-1])[:500]
                if snapshot.last_seen is None and row.last_seen is not None:
                    snapshot.last_seen = row.last_seen.isoformat()
    except Exception as exc:
        logger.warning("Teaching runtime could not read numeric mastery: %s", type(exc).__name__)

    return snapshot


async def decide_for_chat(
    *,
    db: Optional[AsyncSession],
    user_id: Any,
    user_text: str,
    intent: str,
    concept_id: Optional[str] = None,
    history: Optional[Iterable[Any]] = None,
    state_summary: Optional[Mapping[str, Any]] = None,
) -> TeachingDecision:
    learner = await load_learner_snapshot(db, user_id, concept_id)
    session = session_snapshot(
        surface=TeachingSurface.CHAT,
        user_text=user_text,
        history=history,
        state_summary=state_summary,
    )
    context = TeachingContext(
        intent=intent,
        user_text=user_text,
        learner=learner,
        session=session,
        has_active_course=bool(
            isinstance(state_summary, Mapping) and state_summary.get("active_course")
        ),
    )
    return TeachingPolicy.decide(context)


async def record_policy_decision(
    db: Optional[AsyncSession],
    *,
    user_id: Any,
    trace_id: str,
    surface: TeachingSurface,
    decision: TeachingDecision,
    concept_id: Optional[str] = None,
) -> None:
    """Durably record the intervention, never learner text.

    Graded LearningEvents already record the learner's observable result. This
    event records what Lyo chose to do immediately before that result, creating
    the intervention -> outcome trail needed for later policy evaluation.
    """
    if db is None or user_id in (None, "", 0, "0"):
        return
    try:
        from lyo_app.events.models import EventType
        from lyo_app.events.processor import log_learning_event
        from lyo_app.events.schemas import LearningEventCreate

        await log_learning_event(
            db,
            LearningEventCreate(
                user_id=int(user_id),
                event_type=EventType.AI_SESSION,
                concept_id=concept_id,
                # Policy decisions are not demonstrations; recording a concept
                # here must not advance the learner on the evidence ladder.
                evidence_type=None,
                evidence_confidence=None,
                source_surface=surface.value,
                metadata_json={
                    "event_kind": "teaching_policy_decision",
                    "trace_id": str(trace_id),
                    "action": decision.action.value,
                    "reason_code": decision.reason_code,
                    "target_evidence_type": decision.target_evidence_type,
                    "preferred_instrument": decision.preferred_instrument,
                    "model_tier": decision.model_tier,
                    "policy_version": decision.policy_version,
                },
            ),
        )
    except Exception as exc:
        # A telemetry failure must never block instruction.
        logger.warning("Could not record teaching policy decision: %s", type(exc).__name__)
