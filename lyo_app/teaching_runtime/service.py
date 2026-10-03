"""State loading, session summarisation, and policy-event recording."""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Mapping, Optional

from prometheus_client import Counter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    LearnerSnapshot,
    PrerequisiteGap,
    SessionSnapshot,
    TeachingAction,
    TeachingContext,
    TeachingDecision,
    TeachingSurface,
)
from .policy import TeachingPolicy

logger = logging.getLogger(__name__)

teaching_policy_decisions = Counter(
    "lyo_teaching_policy_decisions_total",
    "Deterministic teaching-policy decisions by bounded runtime attributes",
    ["surface", "action", "reason", "policy_version"],
)
teaching_policy_outcomes = Counter(
    "lyo_teaching_policy_outcomes_total",
    "Measured learner outcomes attributable to a teaching-policy intervention",
    ["surface", "action", "reason", "evidence_type", "outcome", "policy_version"],
)

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


_CHAT_TOPIC_INTENTS = frozenset({
    "EXPLAIN",
    "COURSE",
    "QUIZ",
    "FLASHCARDS",
    "STUDY_PLAN",
    "TEST_PREP",
})


def teaching_topic_from_text(user_text: str) -> str:
    """Strip explicit learning-workflow wrappers while preserving the topic.

    The result is only an identity seed for the deterministic topic scope. It
    never fuzzy-matches concepts or changes the learner's requested workflow.
    """
    text = (user_text or "").strip()
    topic = re.sub(
        r"^(?:teach me(?: about| on)?|explain(?: to me)?|help me understand|"
        r"show me|walk me through|learn(?: about)?|quiero aprender(?: sobre)?|"
        r"ens[eé][nñ]ame|expl[ií]came|"
        r"(?:create|make|build|give me|i want)(?: me)? (?:a )?course(?: on| about| for)?|"
        r"course(?: on| about)|"
        r"(?:quiz|test) me(?: on| about)?|(?:create|make|give me)(?: a)? quiz(?: on| about| for)?|"
        r"(?:create|make|give me)(?: some)? flashcards(?: on| about| for)?|flashcards(?: on| about| for)?|"
        r"(?:create|make|build|give me)(?: a)? study plan(?: on| about| for)?|study plan(?: on| about| for)?|"
        r"(?:prepare me|help me prepare)(?: for)?(?: my| a)? (?:test|exam)(?: on| about| for)?)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return topic or text


def resolve_chat_teaching_topic(
    *,
    intent: Any,
    user_text: str,
    state_summary: Optional[Mapping[str, Any]] = None,
    router_topic: Optional[str] = None,
    router_subject: Optional[str] = None,
) -> Optional[str]:
    """Resolve concept/topic identity before the teaching policy runs.

    Chat previously did this only for EXPLAIN, so COURSE/QUIZ/etc. entered the
    Learning OS with an empty learner snapshot and could be converted into an
    unrelated diagnostic turn. Router entities are authoritative when present;
    active-course context is the fallback for short continuation requests.
    """
    normalized_intent = str(getattr(intent, "value", intent) or "").upper()
    if normalized_intent not in _CHAT_TOPIC_INTENTS:
        return None

    explicit = str(router_topic or router_subject or "").strip()
    if explicit:
        return explicit

    active_topic = ""
    if isinstance(state_summary, Mapping):
        active_course = state_summary.get("active_course")
        if isinstance(active_course, Mapping):
            active_topic = str(active_course.get("topic") or "").strip()

    raw_text = (user_text or "").strip()
    text_topic = teaching_topic_from_text(raw_text)

    # Preserve the established EXPLAIN continuation behavior: "why?" or
    # "show me" inside a course refers to the active course unless the router
    # supplied a more specific topic. For other workflows, a successfully
    # stripped wrapper is an explicit new topic; otherwise use active context.
    if normalized_intent == "EXPLAIN" and active_topic:
        return active_topic
    if active_topic and text_topic == raw_text:
        return active_topic
    return text_topic or active_topic or None


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
    db: Optional[AsyncSession],
    user_id: Any,
    concept_id: Optional[str],
    topic: Optional[str] = None,
) -> LearnerSnapshot:
    snapshot = LearnerSnapshot(concept_id=concept_id)
    scoped_concept_ids: list[str] = []
    if db is None or not concept_id or user_id in (None, "", 0, "0"):
        return snapshot

    # Evidence first: unlike a single score it tells us what the learner has
    # actually demonstrated (recognition/application/transfer/retention).
    record = None
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
            elif topic:
                # Classroom free-topic concepts live under a deterministic
                # hashed scope. Reuse only evidence in that exact scope; never
                # join on a similar title or guess an alias.
                from lyo_app.ai_classroom.models import Concept
                from lyo_app.ai_classroom.skill_identity import topic_scope

                scope = topic_scope(topic)
                if scope:
                    scoped_concept_ids = list(
                        (
                            await db.execute(
                                select(Concept.id).where(Concept.subject == scope)
                            )
                        ).scalars().all()
                    )
                    scoped = [
                        item
                        for item in record.concepts
                        if item.concept_id in set(scoped_concept_ids)
                    ]
                    if scoped:
                        rank = {
                            None: -1,
                            "exposure": 0,
                            "recognition": 1,
                            "explanation": 2,
                            "application": 3,
                            "transfer": 4,
                            "retention": 5,
                        }
                        # Use the weakest demonstrated scoped concept so a
                        # generic topic chat never overstates what one strong
                        # unit proves about the whole subject.
                        focus = min(
                            scoped,
                            key=lambda item: rank.get(item.best_rung, -1),
                        )
                        snapshot.evidence_state = focus.state
                        snapshot.strongest_rung = focus.best_rung
                        snapshot.next_rung = focus.next_rung
                        snapshot.attempts = max(snapshot.attempts, len(scoped))
                        recent = max(
                            scoped,
                            key=lambda item: item.last_seen or "",
                        )
                        snapshot.misconception = recent.misconception
                        snapshot.last_seen = recent.last_seen
    except Exception as exc:
        logger.warning("Teaching runtime could not read evidence record: %s", type(exc).__name__)

    # Persistent classroom concepts carry explicit prerequisite edges. A weak
    # prerequisite is a different pedagogical problem from weakness on the
    # target concept itself, so surface it separately instead of collapsing
    # both into one mastery score. Legacy slug concepts simply have no graph
    # edges and skip this branch.
    try:
        from lyo_app.events.mastery_projection import is_concept_graph_id

        if is_concept_graph_id(concept_id):
            from lyo_app.ai_classroom.models import Concept, ConceptPrerequisite

            prereq_rows = (
                await db.execute(
                    select(
                        ConceptPrerequisite.prerequisite_id,
                        Concept.display_name,
                        Concept.name,
                    )
                    .join(
                        Concept,
                        Concept.id == ConceptPrerequisite.prerequisite_id,
                    )
                    .where(ConceptPrerequisite.concept_id == concept_id)
                )
            ).all()
            evidence_by_id = {
                item.concept_id: item
                for item in (record.concepts if record and not record.unavailable else [])
            }
            demonstrated = {"application", "transfer", "retention"}
            gaps = []
            for prereq_id, display_name, name in prereq_rows:
                prior = evidence_by_id.get(prereq_id)
                strongest = prior.best_rung if prior is not None else None
                if strongest not in demonstrated:
                    gaps.append(
                        PrerequisiteGap(
                            concept_id=prereq_id,
                            display_name=display_name or name,
                            evidence_state=prior.state if prior is not None else "NOT_SEEN",
                            strongest_rung=strongest,
                        )
                    )
            snapshot.prerequisite_gaps = gaps
    except Exception as exc:
        logger.warning(
            "Teaching runtime could not read prerequisite graph: %s",
            type(exc).__name__,
        )

    try:
        from lyo_app.personalization.models import LearnerMastery
        from lyo_app.personalization.service import _coerce_learner_id

        learner_id = _coerce_learner_id(user_id)
        if learner_id is not None:
            skill_ids = scoped_concept_ids or [concept_id]
            result = await db.execute(
                select(LearnerMastery).where(
                    LearnerMastery.user_id == learner_id,
                    LearnerMastery.skill_id.in_(skill_ids),
                )
            )
            rows = list(result.scalars().all())
            if rows:
                snapshot.mastery_score = max(
                    0.0,
                    min(
                        1.0,
                        sum(float(row.mastery_level or 0.0) for row in rows) / len(rows),
                    ),
                )
                snapshot.attempts = max(
                    snapshot.attempts,
                    sum(max(0, int(row.attempts or 0)) for row in rows),
                )
                snapshot.hints_used = sum(max(0, int(row.hints_used or 0)) for row in rows)
                snapshot.uncertainty = max(
                    0.0,
                    min(
                        1.0,
                        sum(float(row.uncertainty or 0.0) for row in rows) / len(rows),
                    ),
                )
                if not snapshot.misconception:
                    for row in sorted(
                        rows,
                        key=lambda item: item.last_seen.isoformat()
                        if item.last_seen is not None
                        else "",
                        reverse=True,
                    ):
                        misconceptions = list(row.misconceptions or [])
                        if misconceptions:
                            snapshot.misconception = str(misconceptions[-1])[:500]
                            break
                seen = [row.last_seen for row in rows if row.last_seen is not None]
                if snapshot.last_seen is None and seen:
                    snapshot.last_seen = max(seen).isoformat()
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
    topic: Optional[str] = None,
    history: Optional[Iterable[Any]] = None,
    state_summary: Optional[Mapping[str, Any]] = None,
    has_media: bool = False,
    has_current_media: bool = False,
    interaction_contract: Optional[Mapping[str, Any]] = None,
) -> TeachingDecision:
    learner = await load_learner_snapshot(db, user_id, concept_id, topic=topic)
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
        metadata={
            "has_media": bool(has_media),
            "has_current_media": bool(has_current_media),
            "interaction_contract": dict(interaction_contract or {}),
        },
    )
    return TeachingPolicy.decide(context)


def bounded_intervention_metadata(
    decision: TeachingDecision,
) -> dict[str, Optional[str]]:
    """Serializable, low-cardinality intervention identity.

    No learner text, concept title, prompt, or free-form directive enters this
    object. It is safe to persist on an assessment block and later copy onto
    the resulting evidence event.
    """
    return {
        "action": decision.action.value,
        "reason_code": decision.reason_code,
        "target_evidence_type": decision.target_evidence_type,
        "preferred_instrument": decision.preferred_instrument,
        "model_tier": decision.model_tier,
        "policy_version": decision.policy_version,
    }


def record_policy_outcome(
    *,
    surface: TeachingSurface,
    intervention: Optional[Mapping[str, Any]],
    evidence_type: Optional[str],
    succeeded: bool,
) -> None:
    """Prometheus projection for intervention -> measured learner outcome."""
    if not isinstance(intervention, Mapping):
        return
    action = str(intervention.get("action") or "unknown")[:48]
    reason = str(intervention.get("reason_code") or "unknown")[:80]
    version = str(intervention.get("policy_version") or "unknown")[:48]
    evidence = str(evidence_type or "none")[:32]
    teaching_policy_outcomes.labels(
        surface.value,
        action,
        reason,
        evidence,
        "correct" if succeeded else "incorrect",
        version,
    ).inc()


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
    teaching_policy_decisions.labels(
        surface.value,
        decision.action.value,
        decision.reason_code,
        decision.policy_version,
    ).inc()

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
                    **bounded_intervention_metadata(decision),
                },
            ),
        )
    except Exception as exc:
        # A telemetry failure must never block instruction.
        logger.warning("Could not record teaching policy decision: %s", type(exc).__name__)
