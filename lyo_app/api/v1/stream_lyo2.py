import logging
import asyncio
import json
import re
import uuid
import time
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user_or_guest, get_db
from lyo_app.auth.schemas import UserRead
from lyo_app.ai.router import MultimodalRouter
from lyo_app.ai.planner import LyoPlanner
from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai.schemas.lyo2 import RouterRequest, ConversationTurn, UIBlock, UIBlockType, ActionType, PlannedAction, Intent, RouterDecision, LyoPlan
from lyo_app.ai.multimodal import (
    canonical_message_content,
    load_media_attachments,
    recent_media_refs,
)
from lyo_app.ai.schemas.smart_block import (
    EvidenceContract,
    SmartBlock,
    QuizOption,
    SmartBlockType,
)
from lyo_app.ai.lesson_composer import ChatLesson, SectionKind, compose as compose_lesson
try:
    from lyo_app.ai_agents.multi_agent_v2.agents.test_prep_agent import TestPrepAgent
except ModuleNotFoundError as exc:
    logger = logging.getLogger(__name__)
    logger.warning("Test prep agent module unavailable; using fallback clarification flow: %s", exc)

    class _FallbackTestPrepData:
        subject = None
        topics = []
        test_date = None
        readiness = None
        has_materials = False
        missing_critical_info = ["subject", "topics"]
        follow_up_question = (
            "What subject is your test on, and what topics should we focus on? "
            "You can also upload notes, a study guide, or a syllabus."
        )

    class TestPrepAgent:
        async def analyze_test_prep(self, request):
            from types import SimpleNamespace
            return SimpleNamespace(success=True, data=_FallbackTestPrepData())
from lyo_app.services.proactive_engagement import proactive_engagement_service
from lyo_app.ai_agents.optimization.performance_optimizer import ai_performance_optimizer
from lyo_app.chat.models import ChatMode
from lyo_app.ai.schemas.block_redaction import redact_blocks, redact_content
from lyo_app.chat.stores import conversation_store
from lyo_app.chat.persistence import schedule_assistant_message, finish_assistant_messages
from lyo_app.core.ai_resilience import StreamingIncompleteError

# Simple response builder to fix missing import
class LyoResponseBuilder:
    @staticmethod
    def build_command(command_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": command_type,
            "payload": payload
        }

    @staticmethod
    def build(command: Dict[str, Any], request_id: str, conversation_id: str) -> Dict[str, Any]:
        return {
            "command": command,
            "request_id": request_id,
            "conversation_id": conversation_id,
            "timestamp": time.time()
        }

lyo_response_builder = LyoResponseBuilder()

logger = logging.getLogger(__name__)
_PROCESS_STARTED_MONOTONIC = time.monotonic()

def safe_json_serialize(data: Any, event_type: str = "unknown") -> str:
    """
    Safely serialize data to JSON string with comprehensive error handling.

    This prevents iOS crashes from __SwiftValue serialization errors by:
    1. Using default=str to handle non-serializable types
    2. Double-encoding to ensure final output is JSON-safe
    3. Providing detailed error logging for debugging

    Args:
        data: The data to serialize
        event_type: Description of the event type for error logging

    Returns:
        JSON string that is guaranteed to be iOS-safe

    Raises:
        ValueError: If data cannot be made JSON-safe even with fallbacks
    """
    try:
        # First pass: Convert problematic types to strings
        intermediate = json.loads(json.dumps(data, default=str))

        # Second pass: Final JSON serialization
        result = json.dumps(intermediate)

        logger.debug(f"✅ Safe JSON serialization successful for {event_type}")
        return result

    except (TypeError, ValueError, OverflowError) as e:
        logger.error(f"❌ JSON serialization failed for {event_type}: {e}")
        logger.error(f"Problematic data type: {type(data)}")
        logger.error(f"Problematic data sample: {str(data)[:200]}")

        # Ultimate fallback: return a safe error message
        fallback = {
            "type": "serialization_error",
            "message": f"Data serialization failed for {event_type}",
            "error": str(e),
            "timestamp": time.time()
        }

        try:
            return json.dumps(fallback)
        except Exception as fallback_error:
            logger.critical(f"💥 Even fallback serialization failed: {fallback_error}")
            raise ValueError(f"Complete JSON serialization failure: {fallback_error}")

def yield_safe_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """
    Yield a Server-Sent Event with guaranteed JSON safety.

    Args:
        event_type: The SSE event type
        data: The event data payload

    Returns:
        SSE-formatted string ready for streaming
    """
    try:
        safe_json = safe_json_serialize(data, event_type)
        return f"data: {safe_json}\n\n"
    except ValueError as e:
        logger.error(f"Failed to create safe SSE event for {event_type}: {e}")
        # Return a safe error event
        error_data = {
            "type": "error",
            "message": f"Event serialization failed: {event_type}"
        }
        return f"data: {json.dumps(error_data)}\n\n"

import re as _re

def _lesson_to_smart_blocks(
    lesson: "ChatLesson",
    source_surface: str = "chat",
    target_evidence_type: Optional[str] = None,
    teaching_intervention: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Render a composed lesson into the block vocabulary clients consume.

    Each lesson beat becomes its own block so the client can style it
    distinctly — that separation is what makes a lesson scannable instead of a
    wall of prose. The check block carries the skill id in metadata so grading
    knows which mastery row to update, and the surface that asked so the
    learner's record can say where the evidence came from. Grading happens on
    a later request that only has the stored block to go on, so anything the
    verdict needs has to be written down here.
    """
    blocks: List[Dict[str, Any]] = []

    for section in lesson.sections:
        if section.kind is SectionKind.trap:
            blocks.append(SmartBlock.callout(section.text, variant="trap").model_dump())
        elif section.kind is SectionKind.reference and section.table_markdown:
            blocks.append(
                SmartBlock.table(section.table_markdown, title=section.text or None).model_dump()
            )
        else:
            # hook/core/representation/example/method all render as text; the
            # subtype carries the beat so the client can style it.
            blocks.append(
                SmartBlock.text(section.text, subtype=section.kind.value).model_dump()
            )
            if section.latex:
                blocks.append(
                    SmartBlock.data_viz(section.latex, fmt="math").model_dump()
                )
            # A representation the learner can move through, when the topic
            # genuinely has that shape. The composer omits it otherwise rather
            # than decorating every lesson with a widget.
            explorable = getattr(section, "explorable", None)
            if explorable is not None:
                blocks.append(
                    SmartBlock.explorable(
                        kind=explorable.kind,
                        prompt=explorable.prompt,
                        points=[p.model_dump(exclude_none=True) for p in explorable.points],
                        concept_id=lesson.skill_id,
                    ).model_dump()
                )

    if lesson.check:
        check = lesson.check
        # Probes can only establish recognition. A taught MCQ may establish
        # application, or transfer only when the policy explicitly requested
        # a novel-scenario check and the composer generated one for that
        # target. Delayed retention and free-form explanation are not claims
        # this renderer can honestly make.
        requested_evidence = "recognition" if lesson.is_probe else target_evidence_type
        awarded_evidence = (
            requested_evidence
            if requested_evidence in {"recognition", "application", "transfer"}
            else ("recognition" if lesson.is_probe else "application")
        )
        confidence_cap = 0.8 if awarded_evidence == "transfer" else 1.0
        evidence_contract = EvidenceContract(
            target_evidence_type=awarded_evidence,
            grading="server",
            award_condition="correct",
            confidence_cap=confidence_cap,
        )
        block = SmartBlock.quiz(
            question=check.question,
            options=[
                QuizOption(id=str(i), text=opt.text, reveals=opt.reveals)
                for i, opt in enumerate(check.options)
            ],
            correct_index=check.correct_index,
            explanation=check.explanation,
            hint=check.hint,
            bailout_index=check.bailout_index,
            evidence_contract=evidence_contract,
        )
        block.metadata = {
            **(block.metadata or {}),
            "skill_id": lesson.skill_id,
            "is_probe": lesson.is_probe,
            "source_surface": source_surface,
            "requested_evidence_type": requested_evidence,
            **(
                {"teaching_intervention": teaching_intervention}
                if teaching_intervention
                else {}
            ),
        }
        blocks.append(block.model_dump())

    return blocks


async def _has_prior_mastery(
    db: AsyncSession, user_id: Optional[str], skill_id: str
) -> bool:
    """Has this learner already been assessed on this skill?

    Decides probe vs. teach: only calibrate the first time. Any failure is
    treated as "no prior evidence", which just means we calibrate again —
    the safe direction to be wrong in.
    """
    if db is None or not user_id:
        return False
    try:
        from sqlalchemy import and_, select as _select

        from lyo_app.personalization.models import LearnerMastery
        from lyo_app.personalization.service import _coerce_learner_id

        pk = _coerce_learner_id(user_id)
        if pk is None:
            return False
        result = await db.execute(
            _select(LearnerMastery).where(
                and_(LearnerMastery.user_id == pk, LearnerMastery.skill_id == skill_id)
            )
        )
        row = result.scalar_one_or_none()
        return bool(row and (row.attempts or 0) > 0)
    except Exception as e:
        logger.warning(f"Could not read prior mastery for {skill_id}: {e}")
        return False


def _lesson_mode_for_teaching_action(action: Any) -> Optional[str]:
    """Translate policy action into an explicit composer mode.

    Only DIAGNOSE may create a first-contact probe. Once the Learning OS has
    chosen any substantive teaching/check/review move, composition must not
    fall back to the legacy Chat-slug mastery lookup and silently downgrade
    stronger Classroom evidence to recognition.
    """
    value = str(getattr(action, "value", action) or "").lower()
    if value == "diagnose":
        return "probe"
    if value in {
        "explain",
        "remediate",
        "demonstrate",
        "guide",
        "check_recall",
        "check_application",
        "check_transfer",
        "review",
        "advance",
    }:
        return "teach"
    return None


async def _try_compose_lesson(
    db: AsyncSession,
    user_id: Optional[str],
    user_text: str,
    topic: Optional[str] = None,
    source_surface: str = "chat",
    force_mode: Optional[str] = None,
    target_evidence_type: Optional[str] = None,
    teaching_intervention: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[ChatLesson]]:
    """Compose a structured lesson, or ([], None) to fall back to prose.

    `topic` skips the regex extraction for callers that already know the
    subject. Test Prep does: its agent pulls subject and topics out of the
    conversation as structured fields, and re-deriving them by pattern-matching
    the raw sentence would only lose what was already parsed properly.
    """
    from lyo_app.ai.lesson_composer import slugify_skill

    topic = (topic or "").strip() or _extract_course_topic(user_text or "")
    if not topic:
        return [], None

    mode = force_mode or (
        "teach" if await _has_prior_mastery(db, user_id, slugify_skill(topic)) else "probe"
    )
    if mode not in {"probe", "teach"}:
        mode = "probe"
    lesson = await compose_lesson(
        topic,
        db=db,
        user_id=user_id,
        mode=mode,
        target_evidence_type=target_evidence_type,
    )
    if lesson is None:
        return [], None
    return _lesson_to_smart_blocks(
        lesson,
        source_surface=source_surface,
        target_evidence_type=target_evidence_type,
        teaching_intervention=teaching_intervention,
    ), lesson


def _to_smart_blocks(
    answer_text: Optional[str], artifact: Optional[UIBlock]
) -> List[Dict[str, Any]]:
    """Convert a plain answer plus optional legacy UIBlock artifact into
    SmartBlock dicts — the unified block vocabulary all three clients render.
    Unknown artifact types are skipped rather than guessed at."""
    blocks: List[Dict[str, Any]] = []
    if answer_text:
        blocks.append(SmartBlock.text(answer_text).model_dump())

    if artifact is None:
        return blocks
    content = artifact.content or {}

    if artifact.type == UIBlockType.QUIZ:
        options: List[QuizOption] = []
        for i, opt in enumerate(content.get("options", [])):
            # Planner output is loose: options arrive as plain strings or as
            # dicts that may lack the "id" QuizOption requires.
            if isinstance(opt, str):
                options.append(QuizOption(id=str(i), text=opt))
            elif isinstance(opt, dict):
                options.append(
                    QuizOption(id=str(opt.get("id", i)), text=str(opt.get("text", "")))
                )
        blocks.append(
            SmartBlock.quiz(
                question=str(content.get("question", "")),
                options=options,
                correct_index=int(content.get("correct_index", 0)),
                explanation=content.get("explanation"),
                hint=content.get("hint"),
            ).model_dump()
        )
    elif artifact.type == UIBlockType.FLASHCARDS:
        for card in content.get("cards", []):
            if isinstance(card, dict):
                blocks.append(
                    SmartBlock.flashcard(
                        front=str(card.get("front", "")),
                        back=str(card.get("back", "")),
                    ).model_dump()
                )
    elif artifact.type == UIBlockType.STUDY_PLAN:
        plan = content.get("plan") or content.get("text") or ""
        if plan:
            blocks.append(SmartBlock.text(str(plan), subtype="summary").model_dump())

    return blocks


def _extract_course_topic(user_text: str) -> str:
    topic = _re.sub(
        r"^(create (a )?course (on|about|for)?|make (a )?course (on|about|for)?|"
        r"build (a )?course (on|about|for)?|teach me( about| on)?|"
        r"i want (a )?course (on|about)?|course on|course about|"
        r"give me a course( on)?|a course on)\s*",
        "", user_text.strip(), flags=_re.IGNORECASE,
    ).strip()
    return topic or user_text.strip()


def _extract_course_level(user_text: str) -> Optional[str]:
    """Return one unambiguous difficulty level explicitly named by the learner.

    Level tokens are matched as whole words so unrelated text such as
    "basically" cannot be mistaken for "basic". Requests that name more than
    one distinct level are intentionally treated as ambiguous and left for the
    course architect to resolve.
    """
    normalized = (user_text or "").casefold()
    level_tokens = {
        "advanced": ("advanced", "avanzado", "avanzada"),
        "intermediate": ("intermediate", "intermedio", "intermedia"),
        "beginner": (
            "beginner",
            "beginning",
            "principiante",
            "basic",
            "básico",
            "basico",
        ),
    }
    matched_levels = {
        level
        for level, tokens in level_tokens.items()
        if any(
            _re.search(rf"\b{_re.escape(token)}\b", normalized)
            for token in tokens
        )
    }
    return next(iter(matched_levels)) if len(matched_levels) == 1 else None


def _normalize_course_payload_for_stream(
    payload: Optional[Dict[str, Any]],
    topic: str,
) -> Dict[str, Any]:
    """Normalize executor course output to the same payload clients receive.

    Executor implementations may return the course under a course key or
    directly as the payload. Missing or unusable payloads are replaced with the
    existing deterministic fallback before progress counts are calculated.
    """
    if isinstance(payload, dict):
        nested_course = payload.get("course")
        if isinstance(nested_course, dict):
            return payload
        if payload and any(
            key in payload
            for key in ("id", "title", "topic", "lessons", "objectives")
        ):
            return {"course": payload}

    return {
        "course": {
            "id": str(uuid.uuid4()),
            "title": topic.title() if topic else "Your Course",
            "topic": topic,
            "level": "beginner",
            "duration": "4 weeks",
            "objectives": [
                f"Understand the fundamentals of {topic}",
                f"Apply key concepts of {topic} in practice",
                f"Build confidence with {topic}",
            ],
            "lessons": [],
        }
    }


def _resolve_course_topic(
    user_text: str,
    history: Optional[List[ConversationTurn]] = None,
    active_topic: Optional[str] = None,
) -> str:
    """Resolve the subject of a new course or a short live-course revision.

    A revision such as "make it advanced" should keep the subject the learner
    was already building, not create a course literally titled "Make It
    Advanced". Explicit topic replacements win; otherwise we recover the most
    recent explicit course request from canonical conversation history.
    """
    text = (user_text or "").strip()

    adjust_match = _re.match(
        r"^adjust this course to\s+(.+?)(?:\.|$)",
        text,
        flags=_re.IGNORECASE,
    )
    if adjust_match:
        return adjust_match.group(1).strip()

    topic_change = _re.search(
        r"\b(?:change|switch)\s+(?:the\s+)?(?:course\s+)?(?:topic\s+)?to\s+"
        r"(.+?)(?:[.!?]|$)",
        text,
        flags=_re.IGNORECASE,
    )
    if topic_change:
        return topic_change.group(1).strip()

    explicit_course_request = _re.match(
        r"^(?:create|make|build|give me|i want)\b.*\bcourse\b",
        text,
        flags=_re.IGNORECASE,
    )
    if explicit_course_request:
        return _extract_course_topic(text)

    if active_topic and active_topic.strip():
        return active_topic.strip()

    for turn in reversed(history or []):
        if (turn.role or "").lower() != "user":
            continue
        prior = (turn.content or "").strip()
        if _re.match(
            r"^(?:create|make|build|give me|i want)\b.*\bcourse\b",
            prior,
            flags=_re.IGNORECASE,
        ):
            return _extract_course_topic(prior)

    return _extract_course_topic(text)

router = APIRouter()

router_agent = MultimodalRouter()
planner_agent = LyoPlanner()
test_prep_agent = TestPrepAgent()

class CheckAnswerRequest(BaseModel):
    """A learner's answer to an in-chat check.

    Deliberately does NOT carry the question or the correct answer: the server
    reads those back from the persisted block, so a client cannot assert its
    own correctness.
    """

    conversation_id: str
    block_id: str
    selected_index: int
    time_taken_ms: int = 0
    hint_used: bool = False


class CheckAnswerResponse(BaseModel):
    correct: bool
    correct_index: int
    # Echoed back so a client can render which option was chosen without
    # having to remember it across a reload.
    selected_index: int
    explanation: Optional[str] = None
    # The confusion this particular wrong answer reveals, when known.
    misconception: Optional[str] = None
    # True when the learner chose the "just explain it" opt-out: not graded,
    # not recorded against mastery.
    bailed_out: bool = False
    skill_id: Optional[str] = None
    evidence_type: Optional[str] = None
    mastery: Optional[float] = None
    next_actions: List[str] = PydanticField(default_factory=list)


class SessionSummarySkill(BaseModel):
    skill_id: str
    mastery: Optional[float] = None
    # The question text of the (latest) attempt, so a recap can say what was
    # actually asked instead of just naming the skill id.
    question: Optional[str] = None
    misconception: Optional[str] = None


class SessionSummaryResponse(BaseModel):
    """What a just-finished conversation's checks show the learner nailed vs. shaky.

    Built only from data the check-grading endpoint already writes: the
    verdict persisted onto each block, plus the LearnerMastery row that
    verdict updated. This is a read, not a new tracking mechanism.
    """

    conversation_id: str
    total_checks: int = 0
    correct_checks: int = 0
    nailed: List[SessionSummarySkill] = PydanticField(default_factory=list)
    shaky: List[SessionSummarySkill] = PydanticField(default_factory=list)


class DueReviewItem(BaseModel):
    skill_id: str
    skill_name: Optional[str] = None
    days_overdue: int = 0
    mastery_level: Optional[float] = None
    last_misconception: Optional[str] = None


class DueReviewsResponse(BaseModel):
    items: List[DueReviewItem] = PydanticField(default_factory=list)


def _find_check_block(
    messages: List[Any], block_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Locate a persisted quiz block by id. Returns (block, skill_id)."""
    block, skill_id, _ = _locate_check_block(messages, block_id)
    return block, skill_id


def _locate_check_block(
    messages: List[Any], block_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[Any]]:
    """As _find_check_block, but also returns the owning message.

    The message is needed to persist the verdict back onto the block, so a
    reloaded conversation shows the check as already answered rather than
    offering it again.
    """
    for message in messages:
        for block in (getattr(message, "blocks", None) or []):
            if not isinstance(block, dict) or block.get("id") != block_id:
                continue
            if block.get("type") != SmartBlockType.quiz.value:
                return None, None, None
            metadata = block.get("metadata") or {}
            return block, metadata.get("skill_id"), message
    return None, None, None


def _surface_of(block: Optional[Dict[str, Any]]) -> str:
    """Which surface asked this question.

    Grading runs on a later request than the one that produced the block, so
    the surface has to come from what was written down at composition time.
    A block from before this field existed, or carrying a value the ladder
    does not recognise, reads as "chat" — the surface that composed every
    lesson block until Test Prep started composing its own.

    This is provenance, not scoring: it changes what a learner's history can
    tell them about *where* they proved something, never whether they did.
    """
    from lyo_app.events.evidence import SOURCE_SURFACES

    surface = ((block or {}).get("metadata") or {}).get("source_surface")
    return surface if surface in SOURCE_SURFACES else "chat"


def _teaching_intervention_of(
    block: Optional[Dict[str, Any]],
) -> Optional[Dict[str, str]]:
    raw = ((block or {}).get("metadata") or {}).get("teaching_intervention")
    if not isinstance(raw, dict):
        return None
    allowed = {
        "action": 48,
        "reason_code": 80,
        "target_evidence_type": 32,
        "preferred_instrument": 48,
        "model_tier": 32,
        "policy_version": 48,
    }
    cleaned: Dict[str, str] = {}
    for key, limit in allowed.items():
        value = raw.get(key)
        if value is not None:
            cleaned[key] = str(value)[:limit]
    return cleaned or None


def _check_evidence_contract(block: Optional[Dict[str, Any]]) -> EvidenceContract:
    """Read the server-authored evidence contract from a persisted check.

    Legacy blocks predate contracts and therefore fall back to recognition,
    the weakest positive claim. Even a malformed/newer contract cannot make
    this multiple-choice endpoint award explanation or delayed retention.
    """
    raw = ((block or {}).get("metadata") or {}).get("evidence_contract")
    try:
        contract = EvidenceContract.model_validate(raw or {})
    except Exception:
        return EvidenceContract(
            target_evidence_type="recognition",
            grading="server",
            award_condition="correct",
            confidence_cap=1.0,
        )

    if contract.grading != "server" or contract.award_condition != "correct":
        return EvidenceContract(
            target_evidence_type="recognition",
            grading="server",
            award_condition="correct",
            confidence_cap=1.0,
        )
    if contract.target_evidence_type not in {"recognition", "application", "transfer"}:
        return contract.model_copy(update={"target_evidence_type": "recognition"})
    return contract


def _preferred_prep_topic(
    subject: Optional[str], topics: Optional[List[str]]
) -> str:
    """What to teach first for an upcoming test.

    The first named topic beats the subject heading above it: "cellular
    respiration" is something a lesson can actually teach and check, where
    "Biology" is a shelf. Falls back to the subject when no topic was named,
    and to "" when neither was — the caller then leaves Test Prep on the prose
    path rather than composing a lesson about nothing.
    """
    for topic in topics or []:
        if (topic or "").strip():
            return topic.strip()
    return (subject or "").strip()


def _voice_ready_payload(
    text: str,
    *,
    message_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    segments_delivered: int = 0,
) -> Dict[str, Any]:
    """Delivery hint for clients that can start TTS before the SSE turn closes.

    This is not a second model result. It carries the exact canonical Chat text
    that will also be rendered/persisted for the turn.
    """
    from lyo_app.teaching_runtime.voice_delivery import prepare_spoken_text

    payload: Dict[str, Any] = {
        "type": "voice_ready",
        "text": text,
        "spoken_text": prepare_spoken_text(text) or text,
        "final": True,
    }
    if segments_delivered:
        payload.update(speak=False, delivery="segments", sequence=segments_delivered)
    if message_id:
        payload["message_id"] = message_id
    if latency_ms is not None:
        payload["latency_ms"] = max(0, int(latency_ms))
    return payload


def _voice_friendly_lesson_text(raw: str) -> str:
    """Speech rendering for structured lesson fallback text."""
    from lyo_app.teaching_runtime.voice_delivery import prepare_spoken_text

    return prepare_spoken_text(raw)


async def _emit_composed_lesson(
    db: AsyncSession,
    lesson: "ChatLesson",
    lesson_blocks: List[Dict[str, Any]],
    collected_bricks: List[Dict[str, Any]],
    persistent_conversation: Any,
    assistant_client_message_id: Optional[str],
    mode_used: str,
    voice_delivery: bool = False,
    voice_ready_delivery: bool = True,
):
    """Stream one composed lesson to the client and persist it.

    Shared by every intent that teaches a lesson with a server-gradeable
    check, so a second surface cannot drift into emitting a slightly
    different shape — in particular one whose blocks are not persisted, which
    would leave its check ungradeable on the next request.
    """
    # Clients that do not render blocks yet (iOS, Android) read this
    # plain-text event, so the lesson degrades instead of disappearing.
    lesson_text = lesson.to_plain_text()
    if voice_delivery:
        lesson_text = _voice_friendly_lesson_text(lesson_text)
    answer_brick = {
        "type": "answer",
        "message_id": assistant_client_message_id,
        "generation_status": "completed",
        "speak": not (voice_delivery and voice_ready_delivery),
        "block": {
            "type": "TutorMessageBlock",
            "content": {"text": lesson_text},
            "priority": 0,
        },
    }
    pending_writes = []
    if persistent_conversation:
        pending_writes.append(schedule_assistant_message(
            db,
            persistent_conversation.id,
            store=conversation_store,
            content=lesson_text,
            mode_used=mode_used,
            client_message_id=assistant_client_message_id,
            blocks=lesson_blocks,
        ))
    try:
        if voice_delivery and voice_ready_delivery and lesson_text:
            # Start speech before SmartBlocks/actions/persistence finish. The text is
            # identical to the answer below, so voice stays a delivery layer over
            # the canonical teaching turn.
            yield yield_safe_sse_event(
                "voice_ready",
                _voice_ready_payload(
                    lesson_text,
                    message_id=assistant_client_message_id,
                ),
            )
        collected_bricks.append(answer_brick)
        yield yield_safe_sse_event("answer", answer_brick)
        # Redacted on the way out only. The persisted copy keeps the answer key,
        # because grading happens on a later request against what was stored.
        yield yield_safe_sse_event(
            "smart_blocks",
            {"type": "smart_blocks", "blocks": redact_blocks(lesson_blocks)},
        )

        if lesson.next_directions:
            actions_brick = {
                "type": "actions",
                "blocks": [{
                    "type": "CTARow",
                    "content": {"actions": lesson.next_directions},
                    "priority": 0,
                }],
            }
            collected_bricks.append(actions_brick)
            yield yield_safe_sse_event("actions", actions_brick)
    finally:
        await finish_assistant_messages(pending_writes)


def _grade_check_block(
    block: Dict[str, Any], selected_index: int
) -> Tuple[bool, bool, Optional[str], int, Optional[str]]:
    """Pure grading over a stored block.

    Returns (correct, bailed_out, misconception, correct_index, explanation).
    Kept separate from the route so the decision this endpoint exists to make
    is directly testable.
    """
    content = block.get("content") or {}
    options = content.get("options") or []
    try:
        correct_index = int(content.get("correct_index"))
    except (TypeError, ValueError):
        correct_index = -1
    bailout_index = content.get("bailout_index")

    bailed_out = bailout_index is not None and selected_index == bailout_index
    # Fail closed. A block with a missing or malformed correct_index sentinels
    # to -1, and without this guard a client sending selected_index=-1 would
    # match the sentinel and be told it was correct.
    correct = (
        (not bailed_out)
        and correct_index >= 0
        and selected_index == correct_index
    )

    misconception = None
    if not correct and not bailed_out and 0 <= selected_index < len(options):
        option = options[selected_index]
        if isinstance(option, dict):
            misconception = option.get("reveals")

    return correct, bailed_out, misconception, correct_index, content.get("explanation")


async def _persist_check_result(
    db: AsyncSession,
    message: Optional[Any],
    block_id: str,
    result: "CheckAnswerResponse",
) -> None:
    """Record the verdict on the stored block.

    Without this the grade lives only in client memory, so reloading the
    conversation re-enables an already-answered check and loses the learner's
    selection. Best-effort: a bookkeeping failure must not fail the answer.
    """
    if message is None:
        return
    try:
        blocks = list(getattr(message, "blocks", None) or [])
        updated = []
        changed = False
        for block in blocks:
            if isinstance(block, dict) and block.get("id") == block_id:
                metadata = dict(block.get("metadata") or {})
                metadata["result"] = result.model_dump()
                block = {**block, "metadata": metadata}
                changed = True
            updated.append(block)
        if not changed:
            return
        # Reassign rather than mutate: a JSON column tracks changes by
        # identity, so an in-place edit would never be written.
        message.blocks = updated
        await db.commit()
    except Exception as e:
        logger.warning(f"Could not persist check result for {block_id}: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


@router.post("/chat/check", response_model=CheckAnswerResponse)
async def check_lyo2_answer(
    request: CheckAnswerRequest,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
):
    """Grade an in-chat check against the stored block and record the result.

    This is the structural fix for chat praising a wrong answer: correctness is
    decided here, from the question the server itself emitted — not by a model
    re-reading the transcript, and not by the client.
    """
    authenticated_user_id = (
        str(current_user.id) if getattr(current_user, "id", 0) not in (0, "0", None) else None
    )
    if not authenticated_user_id:
        raise HTTPException(status_code=401, detail="Sign in to answer checks")

    conversation = await conversation_store.get_owned_conversation(
        db, request.conversation_id, authenticated_user_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await conversation_store.get_messages(db, conversation.id, limit=50)
    block, skill_id, owning_message = _locate_check_block(messages, request.block_id)
    if block is None:
        # Either the id was invented, or it names a block that is not a check.
        raise HTTPException(status_code=404, detail="No such check in this conversation")

    correct, bailed_out, misconception, correct_index, explanation = _grade_check_block(
        block, request.selected_index
    )
    evidence_contract = _check_evidence_contract(block)

    response = CheckAnswerResponse(
        correct=correct,
        correct_index=correct_index,
        selected_index=request.selected_index,
        explanation=explanation,
        misconception=misconception,
        bailed_out=bailed_out,
        skill_id=skill_id,
        evidence_type=evidence_contract.target_evidence_type,
    )

    # Persist the verdict onto the block so a reloaded conversation shows the
    # check as already answered instead of offering it again.
    await _persist_check_result(db, owning_message, request.block_id, response)

    # An opt-out is not evidence about what the learner knows, so it is not
    # recorded. Everything else updates mastery.
    if bailed_out or not skill_id:
        return response

    try:
        from lyo_app.personalization.schemas import KnowledgeTraceRequest
        from lyo_app.personalization.service import personalization_engine

        trace = await personalization_engine.trace_knowledge(
            db,
            KnowledgeTraceRequest(
                learner_id=authenticated_user_id,
                skill_id=skill_id,
                item_id=request.block_id,
                correct=correct,
                time_taken_seconds=max(0.0, request.time_taken_ms / 1000.0),
                hints_used=1 if request.hint_used else 0,
            ),
        )
        response.mastery = trace.get("new_mastery")

        if misconception:
            await personalization_engine.record_misconception(
                db, authenticated_user_id, skill_id, misconception
            )
    except Exception as e:
        # The learner still gets an honest verdict even if bookkeeping fails.
        logger.error(f"Failed to record check result for {skill_id}: {e}", exc_info=True)

    # Log the same answer as evidence on the shared event stream.
    #
    # This is what lets the Classroom see what Chat taught: the event
    # processor projects evidence into ai_classroom.MasteryState, which the
    # classroom's scene engine reads and which nothing on the live path was
    # writing. Without this the two surfaces keep separate records of the same
    # learner.
    #
    # `skill_ids_json` is deliberately omitted. It is what asks the processor
    # to run a DKT update, and `trace_knowledge` above has already done that
    # for this answer — passing it here would apply the learner's single
    # answer to their mastery twice. `concept_id` carries the evidence, and
    # the projection keys on that. See test_chat_check_emits_evidence_once.
    try:
        from lyo_app.events.evidence import evidence_from_graded_answer
        from lyo_app.events.models import EventType
        from lyo_app.events.processor import log_learning_event
        from lyo_app.events.schemas import LearningEventCreate

        evidence = evidence_from_graded_answer(
            correct=correct,
            bailed_out=bailed_out,
            misconception=misconception,
            hints_used=1 if request.hint_used else 0,
            evidence_type=evidence_contract.target_evidence_type,
            base_confidence=evidence_contract.confidence_cap,
        )
        intervention = _teaching_intervention_of(block)
        if evidence is not None:
            from lyo_app.teaching_runtime.models import TeachingSurface
            from lyo_app.teaching_runtime.service import record_policy_outcome

            record_policy_outcome(
                surface=TeachingSurface.CHAT,
                intervention=intervention,
                evidence_type=evidence["kind"],
                succeeded=correct,
            )
            evidence_metadata: Dict[str, Any] = {
                "conversation_id": str(request.conversation_id)[:128],
            }
            if intervention:
                evidence_metadata["teaching_intervention"] = intervention
            if 0 < request.time_taken_ms < 3_600_000:
                evidence_metadata["response_time_seconds"] = round(
                    request.time_taken_ms / 1000.0, 3
                )
            await log_learning_event(
                db,
                LearningEventCreate(
                    user_id=int(authenticated_user_id),
                    event_type=EventType.QUIZ_ANSWER,
                    measurable_outcome=1.0 if correct else 0.0,
                    concept_id=skill_id,
                    evidence_type=evidence["kind"],
                    evidence_confidence=evidence["confidence"],
                    hints_used=1 if request.hint_used else 0,
                    misconception=misconception,
                    source_surface=_surface_of(block),
                    metadata_json=evidence_metadata,
                ),
            )
    except Exception as e:
        # Same posture as the mastery bookkeeping above: the learner's verdict
        # is already decided and returned. Evidence logging is what makes the
        # next lesson better, not what makes this answer correct.
        logger.error(
            f"Failed to log check evidence for {skill_id}: {e}", exc_info=True
        )

    return response


def _collect_session_attempts(
    messages: List[Any],
) -> Tuple[Dict[str, Dict[str, Any]], int, int]:
    """Latest graded attempt per skill answered in this conversation.

    Pure over the same `message.blocks` shape `_locate_check_block` reads, so
    it is testable without a database. A skill answered more than once
    summarizes on its most recent attempt (later blocks overwrite earlier
    ones), matching how a retry should read in a recap: how it ended, not how
    it started. Bailed-out checks are not evidence of anything and are
    excluded, same as they are from mastery itself.
    """
    attempts: Dict[str, Dict[str, Any]] = {}
    total_checks = 0
    correct_checks = 0
    for message in messages:
        for block in (getattr(message, "blocks", None) or []):
            if not isinstance(block, dict) or block.get("type") != SmartBlockType.quiz.value:
                continue
            metadata = block.get("metadata") or {}
            result = metadata.get("result")
            skill_id = metadata.get("skill_id")
            if not result or not skill_id or result.get("bailed_out"):
                continue
            total_checks += 1
            if result.get("correct"):
                correct_checks += 1
            content = block.get("content") or {}
            attempts[skill_id] = {
                "question": content.get("question"),
                "correct": bool(result.get("correct")),
                "misconception": result.get("misconception"),
            }
    return attempts, total_checks, correct_checks


def _classify_session_attempts(
    attempts: Dict[str, Dict[str, Any]],
    masteries: Dict[str, float],
) -> Tuple[List[SessionSummarySkill], List[SessionSummarySkill]]:
    """Split this session's attempted skills into nailed vs. shaky.

    Nailed requires both "got it just now" and "the mastery estimate agrees"
    — a lucky guess on a skill still tracked as weak stays in shaky, and a
    momentary slip on an otherwise-solid skill does not erase it from nailed
    only because mastery has not fully caught up yet.
    """
    nailed: List[SessionSummarySkill] = []
    shaky: List[SessionSummarySkill] = []
    for skill_id, attempt in attempts.items():
        mastery = masteries.get(skill_id)
        entry = SessionSummarySkill(
            skill_id=skill_id,
            mastery=mastery,
            question=attempt["question"],
            misconception=attempt["misconception"],
        )
        is_nailed = attempt["correct"] and (mastery is None or mastery >= 0.6)
        (nailed if is_nailed else shaky).append(entry)
    return nailed, shaky


@router.get("/chat/{conversation_id}/summary", response_model=SessionSummaryResponse)
async def get_chat_session_summary(
    conversation_id: str,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
):
    """Session-close recap: what this conversation's checks show the learner nailed vs. shaky.

    Reads only what /chat/check already wrote — the verdict persisted onto
    each block, and the LearnerMastery row that verdict updated.
    """
    authenticated_user_id = (
        str(current_user.id) if getattr(current_user, "id", 0) not in (0, "0", None) else None
    )
    if not authenticated_user_id:
        raise HTTPException(status_code=401, detail="Sign in to see a session summary")

    conversation = await conversation_store.get_owned_conversation(
        db, conversation_id, authenticated_user_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # The unbounded read, not get_messages()'s default 50-message window —
    # a session-close recap must cover every check answered in the
    # conversation, not just the most recent 50 messages of it.
    messages = await conversation_store.get_all_messages(db, conversation.id)
    attempts, total_checks, correct_checks = _collect_session_attempts(messages)

    masteries: Dict[str, float] = {}
    if attempts:
        from lyo_app.personalization.models import LearnerMastery

        mastery_result = await db.execute(
            select(LearnerMastery).where(
                and_(
                    LearnerMastery.user_id == int(authenticated_user_id),
                    LearnerMastery.skill_id.in_(list(attempts.keys())),
                )
            )
        )
        masteries = {row.skill_id: row.mastery_level for row in mastery_result.scalars().all()}

    nailed, shaky = _classify_session_attempts(attempts, masteries)

    return SessionSummaryResponse(
        conversation_id=conversation.id,
        total_checks=total_checks,
        correct_checks=correct_checks,
        nailed=nailed,
        shaky=shaky,
    )


@router.get("/chat/reviews/due", response_model=DueReviewsResponse)
async def get_due_chat_reviews(
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
):
    """Spaced-repetition items ready to resurface, enriched for a client nudge.

    Every check answered through /chat/check has updated a SM-2 schedule
    since checks shipped (`PersonalizationEngine._update_repetition_schedule`)
    — nothing has read it back out for chat until now. Guests have no
    mastery record to schedule against, so they always get an empty list
    rather than an error.
    """
    authenticated_user_id = (
        str(current_user.id) if getattr(current_user, "id", 0) not in (0, "0", None) else None
    )
    if not authenticated_user_id:
        return DueReviewsResponse(items=[])

    from lyo_app.personalization.service import personalization_engine

    due = await personalization_engine.get_due_reviews(db, int(authenticated_user_id))
    return DueReviewsResponse(
        items=[
            DueReviewItem(
                skill_id=item["skill_id"],
                skill_name=item.get("skill_name"),
                days_overdue=item["days_overdue"],
                mastery_level=item["mastery_level"],
                last_misconception=item["last_misconception"],
            )
            for item in due
        ]
    )


@router.post("/chat/stream")
async def stream_lyo2_chat(
    request: RouterRequest,
    fastapi_request: Request,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db)
):
    """
    Lyo 2.0 Streaming Chat Endpoint (SSE).
    Returns a stream of UI blocks as they are ready.
    """
    trace_id = str(uuid.uuid4())
    logger.info(f"🚀 [STREAM] Starting session {trace_id} for user {current_user.id}")
    
    async def event_generator() -> AsyncGenerator[str, None]:
        start_time = time.time()
        request_started = time.monotonic()
        process_uptime_ms = int(
            (time.monotonic() - _PROCESS_STARTED_MONOTONIC) * 1000
        )
        latency_metrics: Dict[str, Any] = {
            "process_uptime_ms": process_uptime_ms,
            "cold_start_suspected": process_uptime_ms < 60_000,
        }
        memory_task = None
        current_time_for_prompt = ""
        freshness_decision = None
        fast_intent = None
        supports_text_delta = False
        pending_writes = []
        assistant_write_scheduled = False
        voice_state = request.resolved_voice_session.model_dump()
        voice_active = request.resolved_voice_session.active
        voice_hints_enabled = voice_active and voice_state["delivery"] in {"ready", "segments"}

        def persist_answer(text, mode_used, **metadata):
            nonlocal assistant_write_scheduled
            if persistent_conversation and text and not assistant_write_scheduled:
                assistant_write_scheduled = True
                pending_writes.append(schedule_assistant_message(
                    db, persistent_conversation.id, store=conversation_store, content=text,
                    mode_used=mode_used, client_message_id=assistant_client_message_id,
                    **metadata,
                ))

        try:
            display_content = canonical_message_content(request.text, request.media)
            media_attachments = await load_media_attachments(request.media)
            if not request.text and request.media:
                request.text = "Please analyze the attached material and respond to what it contains."

            # Resolve one server-owned conversation before any AI work.  The
            # bearer identity, never a client-supplied user_id, owns the row.
            persistent_conversation = None
            assistant_client_message_id = trace_id
            replayed_assistant = None
            authenticated_user_id = (
                str(current_user.id) if getattr(current_user, "id", 0) not in (0, "0", None) else None
            )
            if authenticated_user_id:
                if request.conversation_id:
                    persistent_conversation = await conversation_store.get_owned_conversation(
                        db, request.conversation_id, authenticated_user_id
                    )
                    if persistent_conversation is None:
                        # A new client can begin with a provisional local UUID.
                        # Adopt a server UUID and announce it below.
                        persistent_conversation = await conversation_store.create_conversation(
                            db,
                            session_id=request.session_id or request.device_id or trace_id,
                            user_id=authenticated_user_id,
                            topic=(request.text or "New Chat")[:200],
                        )
                        request.conversation_id = persistent_conversation.id
                else:
                    persistent_conversation = await conversation_store.create_conversation(
                        db,
                        session_id=request.session_id or request.device_id or trace_id,
                        user_id=authenticated_user_id,
                        topic=(request.text or "New Chat")[:200],
                    )
                    request.conversation_id = persistent_conversation.id

                # Server history is canonical.  Clients can omit local history
                # and resume seamlessly after reinstall, refresh, or device swap.
                persisted_history = await conversation_store.get_messages(
                    db, persistent_conversation.id, limit=30
                )
                request.conversation_history = [
                    ConversationTurn(role=message.role, content=message.content)
                    for message in persisted_history
                    if message.role in ("user", "assistant", "system")
                    and getattr(message, "generation_status", "completed") == "completed"
                    and not (
                        request.client_message_id
                        and message.client_message_id == request.client_message_id
                    )
                ]
                if request.client_message_id:
                    assistant_client_message_id = str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{persistent_conversation.id}:{request.client_message_id}:assistant",
                        )
                    )
                    replayed_assistant = await conversation_store.get_message_by_client_id(
                        db,
                        persistent_conversation.id,
                        assistant_client_message_id,
                    )
                if display_content:
                    await conversation_store.add_message(
                        db,
                        persistent_conversation.id,
                        role="user",
                        content=display_content,
                        mode_used=ChatMode.GENERAL.value,
                        client_message_id=request.client_message_id,
                    )
                yield yield_safe_sse_event(
                    "conversation",
                    {
                        "type": "conversation",
                        "conversation_id": persistent_conversation.id,
                    },
                )
                if replayed_assistant:
                    replay_complete = getattr(replayed_assistant, "generation_status", "completed") == "completed"
                    if voice_hints_enabled and replay_complete:
                        yield yield_safe_sse_event(
                            "voice_ready",
                            {**_voice_ready_payload(
                                replayed_assistant.content,
                                message_id=assistant_client_message_id,
                            ), "replayed": True},
                        )
                    yield yield_safe_sse_event(
                        "answer",
                        {
                            "type": "answer",
                            "block": {
                                "type": "TutorMessageBlock",
                                "content": {"text": replayed_assistant.content},
                                "priority": 0,
                            },
                            "replayed": True,
                            "message_id": assistant_client_message_id,
                            "generation_status": "completed" if replay_complete else "incomplete",
                            "speak": replay_complete and not voice_hints_enabled,
                        },
                    )
                    if not replay_complete:
                        yield yield_safe_sse_event("voice_incomplete", {
                            "type": "voice_incomplete", "message_id": assistant_client_message_id,
                            "generation_status": "incomplete", "replayed": True, "speak": False,
                        })
                    yield "data: [DONE]\n\n"
                    return

            historical_media = []
            if not media_attachments:
                historical_media = recent_media_refs(request.conversation_history)
                media_attachments = await load_media_attachments(
                    historical_media, missing_ok=True
                )

            from lyo_app.teaching_runtime.model_usage import (
                bind_model_usage,
                learning_event_usage_recorder,
            )

            def _model_usage_scope(tier: str, surface: str = "chat"):
                conversation_key = (
                    getattr(persistent_conversation, "id", None)
                    or request.conversation_id
                    or request.session_id
                    or request.device_id
                )
                return bind_model_usage(
                    learning_event_usage_recorder(
                        user_id=authenticated_user_id,
                        surface=surface,
                        session_id=conversation_key,
                        model_tier=tier,
                    )
                )

            collected_bricks = []
            
            skeleton_brick = {"type": "skeleton", "blocks": ["answer", "artifact"]}
            collected_bricks.append(skeleton_brick)
            yield yield_safe_sse_event("skeleton", skeleton_brick)
            await asyncio.sleep(0.01) # Yield to event loop
            
            # 2. Fast-lane eligibility, freshness, and authoritative time.
            from lyo_app.chat.fast_path import fast_route_intent
            from lyo_app.chat.freshness import current_time_context, decide_freshness

            current_time_for_prompt = current_time_context(request.timezone)
            freshness_decision = decide_freshness(request.text or "")
            fast_intent = fast_route_intent(
                request.text or "",
                has_media=bool(media_attachments),
                forced_intent=request.forced_intent,
            )
            request.state_summary = {
                **(request.state_summary or {}),
                "current_time_context": current_time_for_prompt,
                "freshness_mode": freshness_decision.mode.value,
            }
            stream_caps = (
                request.state_summary.get("stream_capabilities", {})
                if isinstance(request.state_summary, dict)
                else {}
            )
            supports_text_delta = bool(
                isinstance(stream_caps, dict)
                and stream_caps.get("text_delta")
            )

            # Ordinary chat does not pay the optimizer/cache setup cost.
            # Workflow/teaching paths retain the existing behavior.
            cache_key = None
            opt_config = {}
            if fast_intent is None:
                optimizer_started = time.monotonic()
                await ai_performance_optimizer.initialize()
                opt_data = await ai_performance_optimizer.optimize_request(
                    agent_type=request.forced_intent.value if request.forced_intent else "general",
                    request_data=request.model_dump()
                )
                latency_metrics["optimizer_ms"] = int(
                    (time.monotonic() - optimizer_started) * 1000
                )
                cache_key = opt_data.get("cache_key")
                cached_full_resp = None
                if not authenticated_user_id:
                    cached_full_resp = await ai_performance_optimizer.cache_manager.get(
                        "full_response", key=cache_key
                    )
                if cached_full_resp:
                    logger.info(f"✨ [STREAM][{trace_id}] Full cache hit! Yielding optimized response.")
                    cached_voice_active = voice_hints_enabled
                    if cached_voice_active:
                        cached_spoken_text = ""
                        for brick in cached_full_resp:
                            if not isinstance(brick, dict) or brick.get("type") != "answer":
                                continue
                            block = brick.get("block")
                            content = block.get("content") if isinstance(block, dict) else None
                            if isinstance(content, dict) and isinstance(content.get("text"), str):
                                cached_spoken_text = content["text"].strip()
                                if cached_spoken_text:
                                    break
                        if cached_spoken_text:
                            yield yield_safe_sse_event(
                                "voice_ready",
                                _voice_ready_payload(
                                    cached_spoken_text,
                                    message_id=assistant_client_message_id,
                                    latency_ms=int((time.time() - start_time) * 1000),
                                ),
                            )
                    for brick in cached_full_resp:
                        if isinstance(brick, dict) and brick.get("type") == "answer":
                            brick = {
                                **brick,
                                "message_id": assistant_client_message_id,
                                "speak": not voice_hints_enabled,
                            }
                        yield f"data: {json.dumps(brick)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                opt_config = opt_data.get("processing_config", {})

            # 2. Layer A: Routing
            logger.info(f"🔍 [STREAM][{trace_id}] Starting Routing...")
            r_start = time.time()

            # Known intake continuations need no additional LLM router call.
            # This is also what makes short replies such as "Friday" reliable.
            continuing_prep = False
            cancelled_prep = (request.text or "").strip().lower() in {"cancel", "stop test prep", "exit test prep"}
            if authenticated_user_id:
                from lyo_app.study_plans.routes import owned_profile
                saved_prep = await owned_profile(db, int(authenticated_user_id))
                saved_workflow = dict(saved_prep.workflow_state or {}) if saved_prep else {}
                continuing_prep = bool(saved_prep and not saved_prep.intake_complete and
                    saved_workflow.get("conversation_id") == str(request.conversation_id))
                if continuing_prep and cancelled_prep:
                    saved_workflow.pop("conversation_id", None)
                    saved_prep.workflow_state = saved_workflow
                    await db.commit()
                    continuing_prep = False
                lower_text = (request.text or "").strip().lower()
                explicit_prep = any(phrase in lower_text for phrase in
                    ("i have a test", "i have an exam", "tengo un examen", "prepare for my test", "prepare for my exam"))
                if not request.forced_intent and not cancelled_prep and (continuing_prep or explicit_prep):
                    request.forced_intent = Intent.TEST_PREP
            
            if request.forced_intent:
                logger.info(f"🎯 [STREAM][{trace_id}] Bypassing router. Forced intent: {request.forced_intent.value}")
                decision = RouterDecision(
                    intent=request.forced_intent,
                    confidence=1.0,
                    needs_clarification=False,
                    suggested_tier="MEDIUM"
                )
                latency_metrics["router_path"] = "forced"
            elif fast_intent is not None:
                logger.info(
                    f"⚡ [STREAM][{trace_id}] Deterministic route: {fast_intent.value}"
                )
                decision = RouterDecision(
                    intent=fast_intent,
                    confidence=1.0,
                    needs_clarification=False,
                    suggested_tier="TINY",
                )
                latency_metrics["router_path"] = "deterministic"
            else:
                try:
                    # 2b. Fetch Proactive Nudges (New for Phase 16).
                    #
                    # Keep this context out of request.text. request.text is the
                    # learner-authored surface and is reused for visible titles,
                    # course topics, persistence and executor prompts. Mutating it
                    # here leaked strings such as "[Proactive Context: ...]" into
                    # the course card. The router gets an internal copy while the
                    # planner receives the same data through USER STATE.
                    proactive_context = ""
                    routing_request = request
                    try:
                        nudges = await proactive_engagement_service.get_pending_nudges_for_user(current_user.id, db)
                        if nudges:
                            proactive_context = "\n**Proactive System Nudges (Incorporate these into your greeting if relevant):**\n"
                            for n in nudges:
                                proactive_context += f"- [{n.nudge_type}] {n.title}: {n.message}\n"
                            request.state_summary = {
                                **(request.state_summary or {}),
                                "proactive_context": proactive_context,
                            }
                            routing_request = request.model_copy(
                                update={
                                    "text": (
                                        f"[Internal proactive context: {proactive_context}]\n"
                                        + (request.text or "")
                                    )
                                }
                            )
                    except Exception as ne:
                        logger.warning(f"Failed to fetch proactive nudges: {ne}")

                    with _model_usage_scope("orchestration"):
                        routing_response = await asyncio.wait_for(
                            router_agent.route(
                                routing_request,
                                media_attachments=media_attachments,
                            ),
                            timeout=35.0,
                        )
                    decision = routing_response.decision
                except asyncio.TimeoutError:
                    logger.error(f"❌ [STREAM][{trace_id}] Routing timed out after 35s")
                    yield f"data: {json.dumps({'type': 'error', 'message': 'My magical circuits got a little crossed while thinking about that. Could we try again?'})}\n\n"
                    return
                
            latency_metrics["routing_ms"] = int((time.time() - r_start) * 1000)
            logger.info(f"✅ [STREAM][{trace_id}] Routing complete ({time.time()-r_start:.2f}s): {decision.intent} (confidence={decision.confidence})")

            # Shared Learning OS policy. Routing says what the learner wants;
            # this deterministic layer says what pedagogical move should happen
            # next. It reads the same durable evidence the Classroom receives.
            from lyo_app.ai.lesson_composer import slugify_skill
            from lyo_app.teaching_runtime import (
                DeliveryMode,
                InteractionMode,
                TeachingAction,
                TeachingSurface,
                decide_for_chat,
                interaction_contract_for_request,
                record_policy_decision,
                resolve_chat_teaching_topic,
            )

            voice_context = request.resolved_voice_session
            interaction_contract = interaction_contract_for_request(
                text=request.text or "",
                routed_intent=decision.intent,
                has_media=bool(media_attachments),
                has_current_media=bool(request.media),
                voice_mode=voice_context.active,
                voice_interrupted_previous_turn=voice_context.interrupted_previous_turn,
            )
            interaction_contract_payload = {
                "mode": interaction_contract.mode.value,
                "depth": interaction_contract.depth.value,
                "delivery_mode": interaction_contract.delivery_mode.value,
                "voice_interrupted_previous_turn": interaction_contract.voice_interrupted_previous_turn,
                "fast_lane": interaction_contract.fast_lane,
                "workflow_intent": (
                    interaction_contract.workflow_intent.value
                    if interaction_contract.workflow_intent is not None
                    else None
                ),
                "attachment_authoritative": interaction_contract.attachment_authoritative,
                "reason_code": interaction_contract.reason_code,
                "directives": list(interaction_contract.directives),
            }
            if voice_context.active:
                interaction_contract_payload["voice_session"] = voice_context.model_dump(exclude_none=True)

            # A handoff such as "Use this for Test Prep" or "Teach this in
            # Classroom" inherits the most recent Lyo-owned attachment instead
            # of forcing the learner to upload the same material again.
            if (
                not request.media
                and historical_media
                and (
                    interaction_contract.attachment_authoritative
                    or interaction_contract.workflow_intent in {Intent.TEST_PREP, Intent.COURSE}
                )
            ):
                request.media = historical_media

            # Explicit learner language is more authoritative than a coarse
            # router guess. Workflows can therefore correct the router before
            # any pedagogical or planner decision is made.
            if (
                interaction_contract.workflow_intent is not None
                and interaction_contract.workflow_intent != decision.intent
            ):
                decision = decision.model_copy(
                    update={
                        "intent": interaction_contract.workflow_intent,
                        "confidence": 1.0,
                        "needs_clarification": False,
                        "clarification_question": None,
                    }
                )

            yield yield_safe_sse_event(
                "interaction_contract",
                {"type": "interaction_contract", **interaction_contract_payload},
            )

            _policy_topic = resolve_chat_teaching_topic(
                intent=decision.intent,
                user_text=request.text or "",
                state_summary=request.state_summary,
                router_topic=getattr(getattr(decision, "entities", None), "topic", None),
                router_subject=getattr(getattr(decision, "entities", None), "subject", None),
            )
            _teaching_concept_id = (
                slugify_skill(_policy_topic) if _policy_topic else None
            )

            teaching_decision = await decide_for_chat(
                db=db,
                user_id=authenticated_user_id,
                user_text=request.text or "",
                intent=decision.intent.value if decision.intent else "GENERAL",
                concept_id=_teaching_concept_id,
                topic=_policy_topic,
                history=request.conversation_history,
                state_summary=request.state_summary,
                has_media=bool(media_attachments),
                has_current_media=bool(request.media),
                interaction_mode=interaction_contract.mode.value,
                response_depth=interaction_contract.depth.value,
            )
            await record_policy_decision(
                db,
                user_id=authenticated_user_id,
                trace_id=trace_id,
                surface=TeachingSurface.CHAT,
                decision=teaching_decision,
                concept_id=_teaching_concept_id,
            )
            yield yield_safe_sse_event(
                "teaching_policy",
                {
                    "type": "teaching_policy",
                    **teaching_decision.model_dump(mode="json"),
                },
            )

            # Ordinary chat: no planner, no simulated stream. The model begins
            # producing visible deltas immediately after deterministic policy.
            if (
                fast_intent is not None
                and decision.intent in {Intent.CHAT, Intent.GREETING}
                and interaction_contract.workflow_intent is None
                and interaction_contract.delivery_mode != DeliveryMode.VOICE
                and not media_attachments
                and not decision.needs_clarification
            ):
                # Conversation history is sufficient working memory on the
                # reflex lane. Durable-memory synthesis belongs to teaching
                # and planner-driven turns and must not delay ordinary chat.
                personal_memory = ""

                history = [
                    {"role": turn.role, "content": turn.content}
                    for turn in request.conversation_history
                ] if request.conversation_history else []

                executor = LyoExecutor(db)
                model_metadata: Dict[str, Any] = {}
                streamed_text = ""
                first_delta = True
                enable_search = bool(
                    freshness_decision
                    and freshness_decision.google_search_enabled
                )
                search_required = bool(
                    freshness_decision
                    and freshness_decision.mode.value == "require"
                )
                if search_required:
                    yield yield_safe_sse_event(
                        "search_status",
                        {
                            "type": "search_status",
                            "status": "searching",
                            "message": "Checking current information…",
                        },
                    )

                model_started = time.monotonic()
                stream_failure = None
                try:
                    async with asyncio.timeout(60.0):
                        with _model_usage_scope(
                            str(
                                getattr(
                                    teaching_decision,
                                    "model_tier",
                                    None,
                                )
                                or "reflex"
                            )
                        ):
                            async for chunk in executor.stream_text(
                                original_request=request.text or "",
                                conversation_history=history,
                                teaching_decision=teaching_decision.model_dump(
                                    mode="json"
                                ),
                                interaction_contract=interaction_contract_payload,
                                personal_memory=personal_memory,
                                current_time_context=current_time_for_prompt,
                                enable_google_search=enable_search,
                                search_required=search_required,
                                metadata_sink=model_metadata,
                            ):
                                if not chunk:
                                    continue
                                if first_delta:
                                    first_delta = False
                                    if supports_text_delta:
                                        latency_metrics["server_ttft_ms"] = int(
                                            (
                                                time.monotonic()
                                                - request_started
                                            )
                                            * 1000
                                        )
                                streamed_text += chunk
                                if supports_text_delta:
                                    yield yield_safe_sse_event(
                                        "text_delta",
                                        {
                                            "type": "text_delta",
                                            "content": chunk,
                                        },
                                    )
                except StreamingIncompleteError as exc:
                    # The resilience layer preserves exactly what the learner
                    # already saw. Reconcile from its canonical partial text in
                    # case a provider failed between the final yield and error.
                    partial = str(exc.partial_text or "").strip()
                    if partial and len(partial) > len(streamed_text):
                        streamed_text = partial
                    stream_failure = "provider_interrupted"
                    latency_metrics["stream_incomplete"] = True
                except asyncio.TimeoutError:
                    # Provider reads are bounded at the route level as well as
                    # by provider clients. Any text already emitted remains a
                    # valid incomplete answer and must not disappear.
                    stream_failure = "timeout"
                    latency_metrics["stream_timeout"] = True

                latency_metrics["model_total_ms"] = int(
                    (time.monotonic() - model_started) * 1000
                )
                if model_metadata.get("model_ttft_ms") is not None:
                    latency_metrics["provider_ttft_ms"] = model_metadata[
                        "model_ttft_ms"
                    ]
                latency_metrics["provider"] = model_metadata.get("provider")
                latency_metrics["freshness_mode"] = (
                    freshness_decision.mode.value
                    if freshness_decision
                    else "none"
                )

                generation_status = (
                    "incomplete" if stream_failure else "completed"
                )
                if streamed_text:
                    if "server_ttft_ms" not in latency_metrics:
                        latency_metrics["server_ttft_ms"] = int(
                            (time.monotonic() - request_started) * 1000
                        )
                    persist_answer(
                        streamed_text,
                        (
                            decision.intent.value.lower()
                            if decision.intent
                            else ChatMode.GENERAL.value
                        ),
                        action_triggered=(
                            "stream_incomplete"
                            if stream_failure
                            else None
                        ),
                    )
                    yield yield_safe_sse_event(
                        "answer",
                        {
                            "type": "answer",
                            "message_id": assistant_client_message_id,
                            "generation_status": generation_status,
                            "speak": not voice_hints_enabled,
                            "block": {
                                "type": "TutorMessageBlock",
                                "content": {"text": streamed_text},
                                "priority": 0,
                            },
                            "final_snapshot": True,
                        },
                    )
                elif stream_failure:
                    yield yield_safe_sse_event(
                        "error",
                        {
                            "type": "error",
                            "message": (
                                "The response timed out. Please retry."
                                if stream_failure == "timeout"
                                else (
                                    "The response was interrupted before "
                                    "it could begin. Please retry."
                                )
                            ),
                        },
                    )
                    latency_metrics["total_ms"] = int(
                        (time.monotonic() - request_started) * 1000
                    )
                    yield yield_safe_sse_event(
                        "latency",
                        {
                            "type": "latency",
                            "metrics": latency_metrics,
                        },
                    )
                    yield "data: [DONE]\n\n"
                    return

                grounded_sources = list(model_metadata.get("sources") or [])
                if grounded_sources:
                    source_items = [
                        {
                            "label": str(source.get("title") or "Web source"),
                            "detail": "Live web source",
                            "url": str(source.get("url") or ""),
                        }
                        for source in grounded_sources
                        if isinstance(source, dict) and source.get("url")
                    ]
                    if source_items:
                        yield yield_safe_sse_event(
                            "smart_blocks",
                            {
                                "type": "smart_blocks",
                                "blocks": [{
                                    "id": f"sources-{trace_id[:8]}",
                                    "schema_version": 1,
                                    "type": "interactive",
                                    "subtype": "sourceNavigator",
                                    "content": {
                                        "title": "Sources used",
                                        "items": source_items,
                                    },
                                    "metadata": {
                                        "role": "grounding",
                                        "freshness": freshness_decision.mode.value
                                        if freshness_decision else "none",
                                    },
                                }],
                            },
                        )
                    yield yield_safe_sse_event(
                        "sources",
                        {"type": "sources", "sources": grounded_sources},
                    )

                latency_metrics["total_ms"] = int(
                    (time.monotonic() - request_started) * 1000
                )
                yield yield_safe_sse_event(
                    "latency",
                    {"type": "latency", "metrics": latency_metrics},
                )
                yield "data: [DONE]\n\n"
                logger.info(
                    f"⚡ [STREAM][{trace_id}] Fast chat complete in "
                    f"{latency_metrics['total_ms']}ms "
                    f"(TTFT={latency_metrics.get('server_ttft_ms')}ms, "
                    f"provider={latency_metrics.get('provider')})"
                )
                return

            # Chat is an adapter onto the same account-owned intake as Test Prep.
            # Continue only the conversation that began intake; ordinary new chats
            # must never be hijacked by an unfinished exam elsewhere.
            if authenticated_user_id and not cancelled_prep and decision.intent == Intent.TEST_PREP:
                from lyo_app.study_plans.chat import process_chat_turn
                # The authenticated intake/plan path returns before the generic
                # Test Prep block below. Bind attribution here so intake and
                # generate_plan model calls join the learner's Test Prep session.
                with _model_usage_scope("teaching", "test_prep"):
                    text = await process_chat_turn(request, current_user, db)
                persist_answer(text, ChatMode.TEST_PREP.value)
                if (
                    text
                    and interaction_contract.delivery_mode == DeliveryMode.VOICE
                    and voice_hints_enabled
                ):
                    yield yield_safe_sse_event(
                        "voice_ready",
                        _voice_ready_payload(
                            text,
                            message_id=assistant_client_message_id,
                            latency_ms=int((time.time() - start_time) * 1000),
                        ),
                    )
                yield yield_safe_sse_event("answer", {"type": "answer", "message_id": assistant_client_message_id, "speak": not voice_hints_enabled, "block": {
                    "type": "TutorMessageBlock", "content": {"text": text}, "priority": 0}})
                yield "data: [DONE]\n\n"
                return

            course_effective_text = request.text or ""
            if decision.intent == Intent.COURSE:
                _active_course = (
                    request.state_summary.get("active_course", {})
                    if isinstance(request.state_summary, dict)
                    else {}
                )
                _active_topic = (
                    _active_course.get("topic")
                    if isinstance(_active_course, dict)
                    and isinstance(_active_course.get("topic"), str)
                    else None
                )
                _active_level = (
                    _active_course.get("difficulty")
                    if isinstance(_active_course, dict)
                    and isinstance(_active_course.get("difficulty"), str)
                    else None
                )
                _topic = _resolve_course_topic(
                    request.text or "", request.conversation_history, _active_topic
                )
                _explicit_level = _extract_course_level(request.text or "")
                if not _explicit_level and _active_level:
                    normalized_active_level = _active_level.lower().strip()
                    if normalized_active_level in {"beginner", "intermediate", "advanced"}:
                        _explicit_level = normalized_active_level
                course_effective_text = (
                    f'Create or revise a course on "{_topic}". '
                    f'Apply this learner request: "{request.text or ""}".'
                )
                _preview_course = {
                    "id": str(uuid.uuid4()),
                    "title": _topic.title() if _topic else "Your Course",
                    "topic": _topic,
                    "objectives": [
                        f"Understand the core concepts of {_topic}",
                        "Apply your knowledge with guided exercises",
                        "Build skills through structured practice",
                    ],
                }
                if _explicit_level:
                    _preview_course["level"] = _explicit_level
                    _preview_course["difficulty"] = _explicit_level.capitalize()
                _preview_oc = {"course": _preview_course}

                yield yield_safe_sse_event(
                    "course_generation",
                    {
                        "type": "course_generation",
                        "phase": "intent",
                        "progress": 10,
                        "message": "Understanding your request",
                    },
                )

                oc_event_data = {
                    'type': 'open_classroom',
                    'preview': True,
                    'block': {
                        'type': 'OpenClassroomBlock',
                        'content': {'type': 'OPEN_CLASSROOM', **_preview_oc},
                    },
                }
                yield yield_safe_sse_event("open_classroom_preview", oc_event_data)
                
                # v2: emit lyo_command for iOS v2 pipeline
                try:
                    cmd = lyo_response_builder.build_command("open_classroom", _preview_oc)
                    lyo_resp = lyo_response_builder.build(command=cmd, request_id=trace_id, conversation_id=trace_id)
                    brick_data = {"type": "lyo_command", "response": lyo_resp}
                    collected_bricks.append(brick_data)
                    yield yield_safe_sse_event("lyo_command", brick_data)
                except (TypeError, ValueError) as e:
                    logger.error(f"JSON serialization error for lyo_command: {e}")
                    # Continue without this brick
                    
                logger.info(f"🏫 [STREAM][{trace_id}] Fast course preview sent for: '{_topic[:60]}'")
            
            if (
                decision.needs_clarification
                and decision.confidence > 0.3
                and not interaction_contract.attachment_authoritative
            ):
                # Only ask for clarification if the router is reasonably confident
                # that it truly cannot understand. Low-confidence clarifications
                # from fallback routing should not block the pipeline.
                logger.info(f"🤔 [STREAM][{trace_id}] Needs clarification: {decision.clarification_question}")
                persist_answer(decision.clarification_question, ChatMode.GENERAL.value)
                if (
                    decision.clarification_question
                    and interaction_contract.delivery_mode == DeliveryMode.VOICE
                    and voice_hints_enabled
                ):
                    yield yield_safe_sse_event(
                        "voice_ready",
                        _voice_ready_payload(
                            decision.clarification_question,
                            message_id=assistant_client_message_id,
                            latency_ms=int((time.time() - start_time) * 1000),
                        ),
                    )
                yield f"data: {json.dumps({'type': 'clarification', 'text': decision.clarification_question, 'message_id': assistant_client_message_id, 'speak': not voice_hints_enabled})}\n\n"
                return
                
            # Intercept TEST_PREP intent to gather structured details
            if decision.intent == Intent.TEST_PREP:
                logger.info(f"📚 [STREAM][{trace_id}] Analyzing Test Prep intent...")
                prep_result = await test_prep_agent.analyze_test_prep(request)
                if prep_result.success and prep_result.data:
                    data = prep_result.data
                    if data.missing_critical_info and data.follow_up_question:
                        # Yield a clarification if critical info is missing
                        logger.info(f"🤔 [STREAM][{trace_id}] Test Prep needs clarification: missing {data.missing_critical_info}")
                        persist_answer(data.follow_up_question, ChatMode.TEST_PREP.value)
                        if (
                            data.follow_up_question
                            and interaction_contract.delivery_mode == DeliveryMode.VOICE
                            and voice_hints_enabled
                        ):
                            yield yield_safe_sse_event(
                                "voice_ready",
                                _voice_ready_payload(
                                    data.follow_up_question,
                                    message_id=assistant_client_message_id,
                                    latency_ms=int((time.time() - start_time) * 1000),
                                ),
                            )
                        yield f"data: {json.dumps({'type': 'clarification', 'text': data.follow_up_question, 'message_id': assistant_client_message_id, 'speak': not voice_hints_enabled})}\n\n"
                        return
                    # Optionally attach extracted data back to the request for the planner
                    request.text += f"\n[System: Extracted Test details: Subject={data.subject}, Topics={data.topics}, Date={data.test_date}]"

                    # Teach and check, rather than only planning.
                    #
                    # Until now Test Prep gathered subject, topics and date and
                    # then handed off to the prose planner, which produces no
                    # server-gradeable question. So a learner could work through
                    # a whole test-prep session and the learner model would
                    # record nothing: not because logging was missing, but
                    # because nothing was ever graded. The Classroom could not
                    # see what they were shaky on, and neither could they.
                    #
                    # The topic comes from the agent's structured extraction
                    # rather than from re-reading the sentence: it already
                    # parsed this out properly, and the first named topic is
                    # more useful to teach than the subject heading above it —
                    # "cellular respiration" beats "Biology".
                    prep_topic = _preferred_prep_topic(data.subject, data.topics)
                    if prep_topic:
                        with _model_usage_scope("teaching", "test_prep"):
                            prep_blocks, prep_lesson = await _try_compose_lesson(
                                db,
                                authenticated_user_id,
                                request.text,
                                topic=prep_topic,
                                source_surface="test_prep",
                            )
                        if prep_lesson is not None:
                            async for event in _emit_composed_lesson(
                                db,
                                prep_lesson,
                                prep_blocks,
                                collected_bricks,
                                persistent_conversation,
                                assistant_client_message_id,
                                ChatMode.TEST_PREP.value,
                                voice_delivery=(
                                    interaction_contract.delivery_mode == DeliveryMode.VOICE
                                ),
                                voice_ready_delivery=voice_hints_enabled,
                            ):
                                yield event

                            yield "data: [DONE]\n\n"
                            logger.info(
                                f"📚 [STREAM][{trace_id}] Served test-prep lesson "
                                f"(topic={prep_topic}, skill={prep_lesson.skill_id}, "
                                f"probe={prep_lesson.is_probe}) in "
                                f"{time.time()-start_time:.2f}s"
                            )
                            return
                        # Composition unavailable: fall through to the planner
                        # rather than dead-ending the learner's request.
                        logger.info(
                            f"📋 [STREAM][{trace_id}] Test-prep lesson unavailable "
                            f"for {prep_topic!r}; falling back to prose path"
                        )

            # 2c. Structured teaching path.
            # A self-contained "explain X" is taught right here as a lesson
            # with a server-gradeable check. Multi-session topics stay on the
            # COURSE path above and hand off to the classroom instead.
            if (
                decision.intent == Intent.EXPLAIN
                and request.text
                and interaction_contract.mode == InteractionMode.TEACH
                and not (
                    freshness_decision
                    and freshness_decision.mode.value == "require"
                )
            ):
                _force_lesson_mode = _lesson_mode_for_teaching_action(
                    teaching_decision.action
                )
                if _force_lesson_mode is not None:
                    from lyo_app.teaching_runtime.service import (
                        bounded_intervention_metadata,
                    )

                    with _model_usage_scope(teaching_decision.model_tier):
                        lesson_blocks, lesson = await _try_compose_lesson(
                            db,
                            authenticated_user_id,
                            request.text,
                            force_mode=_force_lesson_mode,
                            target_evidence_type=teaching_decision.target_evidence_type,
                            teaching_intervention=bounded_intervention_metadata(
                                teaching_decision
                            ),
                        )
                    if lesson is not None:
                        async for event in _emit_composed_lesson(
                            db,
                            lesson,
                            lesson_blocks,
                            collected_bricks,
                            persistent_conversation,
                            assistant_client_message_id,
                            ChatMode.GENERAL.value,
                            voice_delivery=(
                                interaction_contract.delivery_mode == DeliveryMode.VOICE
                            ),
                            voice_ready_delivery=voice_hints_enabled,
                        ):
                            yield event

                        yield "data: [DONE]\n\n"
                        logger.info(
                            f"📚 [STREAM][{trace_id}] Served composed lesson "
                            f"(skill={lesson.skill_id}, probe={lesson.is_probe}, "
                            f"blocks={len(lesson_blocks)}) in {time.time()-start_time:.2f}s"
                        )
                        return
                    logger.info(
                        f"📋 [STREAM][{trace_id}] Lesson composition unavailable; "
                        "falling back to prose path"
                    )

            # 3. Layer B: Planning
            logger.info(f"📋 [STREAM][{trace_id}] Starting Planning (Intent: {decision.intent})...")
            p_start = time.time()

            # Memory synthesis uses this request's DB session, so only overlap
            # it with the model-only planner — never with other DB operations.
            if (
                authenticated_user_id
                and not media_attachments
                and interaction_contract.mode
                in {InteractionMode.EXPLAIN, InteractionMode.TEACH, InteractionMode.CONTINUE}
            ):
                async def _load_planner_parallel_memory():
                    try:
                        from lyo_app.services.memory_synthesis import memory_synthesis_service
                        return await memory_synthesis_service.get_relevant_memory_for_prompt(
                            int(authenticated_user_id),
                            request.text or "",
                            db,
                        )
                    except Exception as memory_exc:
                        logger.debug(
                            "Planner-parallel memory lookup unavailable: %s",
                            type(memory_exc).__name__,
                        )
                        return ""

                memory_task = asyncio.create_task(_load_planner_parallel_memory())

            try:
                # OPTIMIZATION: Attachment information requests are already
                # resolved by the deterministic teaching policy. Sending them
                # through the planner adds latency and gives a second model a
                # chance to manufacture an assessment the learner never asked
                # for, so execute one grounded generation step directly.
                if (
                    interaction_contract.fast_lane
                    and interaction_contract.workflow_intent is None
                    and teaching_decision.action in {TeachingAction.ANSWER, TeachingAction.EXPLAIN}
                ):
                    logger.info(
                        f"⚡ [STREAM][{trace_id}] Contract fast lane: "
                        f"{interaction_contract.mode.value}; skipping planner"
                    )
                    plan = LyoPlan(steps=[
                        PlannedAction(
                            action_type=ActionType.GENERATE_TEXT,
                            description=(
                                "Honor the interaction contract directly without "
                                "introducing another workflow"
                            ),
                            parameters={"content": None},
                        )
                    ])
                elif decision.intent in [Intent.GREETING, Intent.CHAT] and decision.confidence > 0.7:
                    logger.info(f"⚡ [STREAM][{trace_id}] Fast Path: Skipping Planner for {decision.intent}")
                    plan = LyoPlan(steps=[
                        PlannedAction(
                            action_type=ActionType.GENERATE_TEXT,
                            description=f"Handle {decision.intent.value} request directly",
                            parameters={"content": None}
                        )
                    ])
                else:
                    planning_request = (
                        request.model_copy(update={"text": course_effective_text})
                        if decision.intent == Intent.COURSE
                        else request
                    )
                    with _model_usage_scope("orchestration"):
                        plan = await asyncio.wait_for(
                            planner_agent.plan(planning_request, decision), timeout=25.0
                        )
            except asyncio.TimeoutError:
                logger.error(f"❌ [STREAM][{trace_id}] Planning timed out after 25s")
                # Fallback plan
                plan = LyoPlan(steps=[
                    PlannedAction(
                        action_type=ActionType.GENERATE_TEXT,
                        description="Fallback generation after planner timeout",
                        parameters={"content": None}
                    )
                ])
            
            latency_metrics["planning_ms"] = int((time.time() - p_start) * 1000)

            if (
                freshness_decision
                and freshness_decision.mode.value == "require"
                and not any(
                    step.action_type == ActionType.SEARCH_WEB
                    for step in plan.steps
                )
            ):
                plan.steps.insert(
                    0,
                    PlannedAction(
                        action_type=ActionType.SEARCH_WEB,
                        description="Ground explicitly current information in live web results",
                        parameters={"query": request.text or "", "limit": 5},
                    ),
                )
                latency_metrics["search_injected"] = True
                logger.info(
                    f"🌐 [STREAM][{trace_id}] Injected SEARCH_WEB for freshness-required turn"
                )

            logger.info(f"✅ [STREAM][{trace_id}] Planning complete ({time.time()-p_start:.2f}s): {len(plan.steps)} steps")
            if decision.intent == Intent.COURSE:
                yield yield_safe_sse_event(
                    "course_generation",
                    {
                        "type": "course_generation",
                        "phase": "planning",
                        "progress": 30,
                        "message": "Course plan ready",
                    },
                )

            # ── Ensure a GENERATE_TEXT step exists ─────────────────────
            # The LLM planner sometimes omits GENERATE_TEXT steps.
            # Ensure one exists so the executor always produces final_text.
            _has_text_step = any(
                s.action_type == ActionType.GENERATE_TEXT for s in plan.steps
            )
            if not _has_text_step:
                plan.steps.append(PlannedAction(
                    action_type=ActionType.GENERATE_TEXT,
                    description=f"Auto-injected text generation for intent {decision.intent}",
                    parameters={"content": None},
                ))
                logger.info(
                    f"📌 [STREAM][{trace_id}] Injected GENERATE_TEXT step "
                    f"(intent={decision.intent})"
                )

            # 4. Layer C: Execution (Simulated Streaming)
            if decision.intent == Intent.COURSE:
                yield yield_safe_sse_event(
                    "course_generation",
                    {
                        "type": "course_generation",
                        "phase": "execution",
                        "progress": 45,
                        "message": "Starting course generation",
                    },
                )
            logger.info(f"⚡ [STREAM][{trace_id}] Starting Execution...")
            e_start = time.time()
            executor = LyoExecutor(db)
            
            # Build conversation history for multi-turn context
            history = [
                {"role": turn.role, "content": turn.content}
                for turn in request.conversation_history
            ] if request.conversation_history else []
            
            personal_memory = ""
            if (
                authenticated_user_id
                and not media_attachments
                and interaction_contract.mode
                in {InteractionMode.EXPLAIN, InteractionMode.TEACH, InteractionMode.CONTINUE}
            ):
                try:
                    memory_wait_started = time.monotonic()
                    if memory_task is not None:
                        personal_memory = await asyncio.wait_for(
                            memory_task, timeout=0.45
                        )
                    else:
                        from lyo_app.services.memory_synthesis import memory_synthesis_service
                        personal_memory = await asyncio.wait_for(
                            memory_synthesis_service.get_relevant_memory_for_prompt(
                                int(authenticated_user_id),
                                request.text or "",
                                db,
                            ),
                            timeout=0.45,
                        )
                    latency_metrics["memory_wait_ms"] = int(
                        (time.monotonic() - memory_wait_started) * 1000
                    )
                except Exception as memory_exc:
                    logger.debug(
                        "Selective memory lookup unavailable: %s",
                        type(memory_exc).__name__,
                    )
                    personal_memory = ""

            execution_task = None
            voice_sequence = 0
            canonical_voice_parts = []
            answer_mode = decision.intent.value.lower() if decision.intent else ChatMode.GENERAL.value

            def persist_completed_voice(task):
                if not task.cancelled() and task.exception() is None:
                    persist_answer(task.result().answer_block.content.get("text", ""), answer_mode)

            try:
                voice_generate_steps = sum(
                    1 for step in plan.steps
                    if step.action_type == ActionType.GENERATE_TEXT
                )
                voice_can_stream = (
                    interaction_contract.delivery_mode == DeliveryMode.VOICE
                    and interaction_contract.workflow_intent is None
                    and voice_generate_steps == 1
                    and isinstance(voice_state, dict)
                    and voice_state.get("delivery") == "segments"
                )
                if voice_can_stream:
                    from lyo_app.teaching_runtime.voice_delivery import (
                        VoiceSegmenter,
                        prepare_spoken_text,
                    )

                    voice_segments: asyncio.Queue[str] = asyncio.Queue()
                    voice_segmenter = VoiceSegmenter()

                    async def _on_voice_text_delta(delta: str) -> None:
                        canonical_voice_parts.append(delta)
                        for segment in voice_segmenter.feed(delta):
                            await voice_segments.put(segment)

                    with _model_usage_scope(teaching_decision.model_tier):
                        execution_task = asyncio.create_task(
                            executor.execute(
                                user_id=str(current_user.id),
                                plan=plan,
                                original_request=(
                                    course_effective_text
                                    if decision.intent == Intent.COURSE
                                    else request.text or ""
                                ),
                                conversation_history=history,
                                intent=decision.intent.value if decision.intent else None,
                                media_attachments=media_attachments,
                                teaching_decision=teaching_decision.model_dump(mode="json"),
                                interaction_contract=interaction_contract_payload,
                                personal_memory=personal_memory,
                                current_time_context=current_time_for_prompt,
                                text_delta_callback=_on_voice_text_delta,
                            )
                        )

                    execution_task.add_done_callback(persist_completed_voice)

                    # Keep the canonical SSE request open while model deltas
                    # become speakable phrases. The final answer still follows
                    # through the normal answer event and is persisted once.
                    deadline = asyncio.get_running_loop().time() + 60.0
                    while not execution_task.done():
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            execution_task.cancel()
                            await asyncio.gather(execution_task, return_exceptions=True)
                            raise asyncio.TimeoutError
                        try:
                            segment = await asyncio.wait_for(
                                voice_segments.get(),
                                timeout=min(0.10, remaining),
                            )
                        except asyncio.TimeoutError:
                            continue
                        voice_sequence += 1
                        yield yield_safe_sse_event(
                            "voice_text_segment",
                            {
                                "type": "voice_text_segment",
                                "text": segment,
                                "spoken_text": prepare_spoken_text(segment) or segment,
                                "sequence": voice_sequence,
                                "message_id": assistant_client_message_id,
                            },
                        )

                    execution_response = await execution_task

                    # The last model phrase often has no terminal punctuation.
                    # Flush it only after generation has completed so clients
                    # never wait for the full final-answer event to hear it.
                    for segment in voice_segmenter.flush():
                        await voice_segments.put(segment)
                    while not voice_segments.empty():
                        segment = voice_segments.get_nowait()
                        voice_sequence += 1
                        yield yield_safe_sse_event(
                            "voice_text_segment",
                            {
                                "type": "voice_text_segment",
                                "text": segment,
                                "spoken_text": prepare_spoken_text(segment) or segment,
                                "sequence": voice_sequence,
                                "message_id": assistant_client_message_id,
                            },
                        )
                else:
                    with _model_usage_scope(teaching_decision.model_tier):
                        execution_response = await asyncio.wait_for(
                            executor.execute(
                                user_id=str(current_user.id),
                                plan=plan,
                                original_request=(
                                    course_effective_text
                                    if decision.intent == Intent.COURSE
                                    else request.text or ""
                                ),
                                conversation_history=history,
                                intent=decision.intent.value if decision.intent else None,
                                media_attachments=media_attachments,
                                teaching_decision=teaching_decision.model_dump(mode="json"),
                                interaction_contract=interaction_contract_payload,
                                personal_memory=personal_memory,
                                current_time_context=current_time_for_prompt,
                            ),
                            timeout=60.0,
                        )
            except (asyncio.CancelledError, GeneratorExit):
                if execution_task is not None and execution_task.done():
                    persist_completed_voice(execution_task)
                if canonical_voice_parts and not assistant_write_scheduled:
                    persist_answer("".join(canonical_voice_parts).strip(), answer_mode,
                                   action_triggered="voice_incomplete")
                raise
            except (StreamingIncompleteError, asyncio.TimeoutError) as exc:
                partial = (exc.partial_text if isinstance(exc, StreamingIncompleteError)
                           else "".join(canonical_voice_parts)).strip()
                if partial:
                    persist_answer(partial, answer_mode, action_triggered="voice_incomplete")
                    yield yield_safe_sse_event("answer", {
                        "type": "answer", "message_id": assistant_client_message_id,
                        "generation_status": "incomplete", "speak": False,
                        "block": {"type": "TutorMessageBlock", "content": {"text": partial}, "priority": 0},
                    })
                    yield yield_safe_sse_event("voice_incomplete", {
                        "type": "voice_incomplete", "message_id": assistant_client_message_id,
                        "generation_status": "incomplete", "speak": False,
                        "sequence": voice_sequence,
                        "message": "The response was interrupted before it completed. Please retry.",
                    })
                else:
                    yield yield_safe_sse_event("error", {
                        "type": "error", "message": "The response timed out. Please retry.",
                    })
                yield "data: [DONE]\n\n"
                return
            finally:
                # GeneratorExit from body_iterator.aclose() bypasses ordinary
                # exception handlers. Always stop and join the owned executor.
                if execution_task is not None and not execution_task.done():
                    execution_task.cancel()
                    await asyncio.gather(execution_task, return_exceptions=True)

            latency_metrics["execution_ms"] = int((time.time() - e_start) * 1000)
            logger.info(f"✅ [STREAM][{trace_id}] Execution complete ({time.time()-e_start:.2f}s)")
            if decision.intent == Intent.COURSE:
                topic_text = _resolve_course_topic(
                    request.text or "",
                    request.conversation_history,
                    (
                        request.state_summary.get("active_course", {}).get("topic")
                        if isinstance(request.state_summary, dict)
                        and isinstance(request.state_summary.get("active_course"), dict)
                        else None
                    ),
                )
                _raw_course_payload = execution_response.open_classroom_payload
                _normalized_course_payload = _normalize_course_payload_for_stream(
                    _raw_course_payload,
                    topic_text,
                )
                if _normalized_course_payload is not _raw_course_payload:
                    execution_response = execution_response.model_copy(
                        update={"open_classroom_payload": _normalized_course_payload}
                    )
                    if not (
                        isinstance(_raw_course_payload, dict)
                        and _raw_course_payload
                    ):
                        logger.warning(
                            f"⚠️ [STREAM][{trace_id}] COURSE intent but no usable "
                            "open_classroom_payload — using synthesised fallback "
                            f"for topic: '{topic_text[:60]}'"
                        )

                _generated_course = _normalized_course_payload["course"]
                _generated_lessons = _generated_course.get("lessons", [])
                if not isinstance(_generated_lessons, list):
                    _generated_lessons = []
                _lesson_count = len(_generated_lessons)
                _outline = []
                for lesson in _generated_lessons:
                    if not isinstance(lesson, dict):
                        continue
                    _outline.append({
                        "title": str(lesson.get("title") or "Lesson"),
                        "description": str(lesson.get("description") or ""),
                    })
                yield yield_safe_sse_event(
                    "course_generation",
                    {
                        "type": "course_generation",
                        "phase": "lessons",
                        "progress": 82,
                        "message": "Course outline created",
                        "completed_lessons": _lesson_count,
                        "total_lessons": _lesson_count,
                        "outline": _outline,
                    },
                )
            
            # ── Emit plain-text answer event ─────────────────────────
            raw_llm_text = execution_response.answer_block.content.get("text", "")
            voice_delivery = interaction_contract.delivery_mode == DeliveryMode.VOICE

            # The interaction contract already shapes spoken responses. Voice
            # must not wait behind a second, non-authoritative prose optimizer
            # after the canonical model answer is complete.
            if not voice_delivery:
                raw_llm_text = await ai_performance_optimizer.optimize_response(
                    agent_type=decision.intent.value,
                    response=raw_llm_text,
                    context={
                        "user_id": current_user.id,
                        "intent": decision.intent.value,
                        "current_mood": "neutral"
                    }
                )

            persist_answer(
                raw_llm_text,
                decision.intent.value.lower() if decision.intent else ChatMode.GENERAL.value,
            )
            if raw_llm_text and voice_delivery and voice_hints_enabled:
                yield yield_safe_sse_event(
                    "voice_ready",
                    _voice_ready_payload(
                        raw_llm_text,
                        message_id=assistant_client_message_id,
                        latency_ms=int((time.time() - start_time) * 1000),
                        segments_delivered=voice_sequence,
                    ),
                )

            if raw_llm_text:
                answer_brick = {
                    "type": "answer",
                    "message_id": assistant_client_message_id,
                    "generation_status": "completed",
                    "speak": not voice_hints_enabled,
                    "block": {
                        "type": "TutorMessageBlock",
                        "content": {"text": raw_llm_text},
                        "priority": 0
                    }
                }
                collected_bricks.append(answer_brick)
                yield yield_safe_sse_event("answer", answer_brick)
                logger.info(f"📝 [STREAM][{trace_id}] Emitted answer event ({len(raw_llm_text)} chars)")
            
            if execution_response.artifact_block:
                # Send agent-tagged artifact event
                artifact = execution_response.artifact_block
                artifact_type = artifact.type
                
                # Map artifact types to agent roles for cinematic reveal
                agent_tag_map = {
                    UIBlockType.QUIZ: "quiz",
                    UIBlockType.STUDY_PLAN: "content",
                    UIBlockType.FLASHCARDS: "content",
                }
                agent_tag = agent_tag_map.get(artifact_type, "content")
                
                # Tag the artifact content with agent marker.
                #
                # Redacted like every other way out. This legacy event carries
                # the same quiz the `smart_blocks` event below does, and
                # redacting only that one left the answer key, the explanation
                # and the option misconception tags streaming out here — an
                # earlier change closed three doors and missed this fourth.
                tagged_content = redact_content(dict(artifact.content) if artifact.content else {})
                tagged_content["_agent"] = agent_tag
                
                tagged_artifact = UIBlock(
                    type=artifact.type,
                    content=tagged_content,
                    version_id=artifact.version_id
                )

                # Safe JSON serialization using the new helper
                artifact_event_data = {'type': 'artifact', 'block': tagged_artifact.model_dump()}
                yield yield_safe_sse_event("artifact", artifact_event_data)

            # Unified SmartBlock emission: same content as the legacy
            # answer/artifact events above, in the versioned block vocabulary
            # shared by all three clients. Additive — v1 consumers ignore it.
            smart_blocks = _to_smart_blocks(
                raw_llm_text, execution_response.artifact_block
            )
            sources = list(execution_response.metadata.get("sources") or [])
            if sources:
                source_items = []
                for source in sources:
                    if not isinstance(source, dict):
                        continue
                    page_count = source.get("page_count")
                    detail = str(source.get("mime_type") or "attachment")
                    if isinstance(page_count, int) and page_count > 0:
                        detail += f" • {page_count} page" + ("s" if page_count != 1 else "")
                    source_items.append({
                        "label": str(source.get("name") or "Attachment"),
                        "detail": detail,
                        "url": str(source.get("url") or ""),
                    })
                if source_items:
                    smart_blocks.append({
                        "id": f"sources-{trace_id[:8]}",
                        "schema_version": 1,
                        "type": "interactive",
                        "subtype": "sourceNavigator",
                        "content": {
                            "title": "Sources used",
                            "items": source_items,
                        },
                        "metadata": {"role": "grounding"},
                    })

            if smart_blocks:
                yield yield_safe_sse_event(
                    "smart_blocks",
                    {"type": "smart_blocks", "blocks": redact_blocks(smart_blocks)},
                )

            if sources:
                yield yield_safe_sse_event(
                    "sources",
                    {"type": "sources", "sources": sources},
                )

            # Send the normalized open_classroom payload (course creation trigger).
            # COURSE payloads were normalized immediately after execution so the
            # lesson milestone and the client consume the exact same data.
            if execution_response.open_classroom_payload:
                try:
                    from lyo_app.ai_classroom.conversation_flow import get_conversation_manager, ConversationSession
                    cm = get_conversation_manager()
                    
                    oc_payload = execution_response.open_classroom_payload
                    # Ensure oc_payload has a 'course' dict (sometimes it's nested in payload, sometimes it's direct)
                    if isinstance(oc_payload, dict) and "course" in oc_payload:
                        cinfo = oc_payload["course"]
                        s_id = cinfo.get("id")
                        c_topic = cinfo.get("topic")
                        
                        if s_id:
                            sess = ConversationSession(
                                session_id=str(s_id),
                                user_id=getattr(request, "user_id", "guest_session")
                            )
                            sess.current_topic = c_topic
                            sess.current_course_id = str(s_id)
                            cm._sessions[str(s_id)] = sess
                            logger.info(f"💾 Stored ConversationSession({s_id}) for topic '{c_topic}'")
                except Exception as e:
                    logger.error(f"Failed to save cm session: {e}", exc_info=True)

                if decision.intent == Intent.COURSE:
                    yield yield_safe_sse_event(
                        "course_generation",
                        {
                            "type": "course_generation",
                            "phase": "finalizing",
                            "progress": 95,
                            "message": "Preparing your classroom",
                        },
                    )

                logger.info(f"🏫 [STREAM][{trace_id}] Sending open_classroom event")
                oc_brick = {
                    "type": "open_classroom",
                    "block": {
                        "type": "OpenClassroomBlock",
                        "content": {
                            "type": "OPEN_CLASSROOM",
                            **execution_response.open_classroom_payload
                        },
                        "priority": 0
                    }
                }
                collected_bricks.append(oc_brick)
                yield f"data: {json.dumps(oc_brick)}\n\n"
                
            # Emit v1 actions event
            action_labels = []
            for action_block in execution_response.next_actions:
                if action_block.content and "actions" in action_block.content:
                    action_labels.extend(action_block.content["actions"])
            if action_labels:
                actions_brick = {
                    "type": "actions",
                    "blocks": [{"type": "CTARow", "content": {"actions": action_labels}, "priority": 0}]
                }
                collected_bricks.append(actions_brick)
                yield f"data: {json.dumps(actions_brick)}\n\n"
            
            # --- Cache the full response (Phase 17) ---
            if (
                not authenticated_user_id
                and 'cache_key' in locals()
                and cache_key
                and collected_bricks
            ):
                try:
                    await ai_performance_optimizer.cache_manager.set(
                        "full_response", 
                        key=cache_key, 
                        value=collected_bricks,
                        expire=3600 * 12 # Cache for 12 hours
                    )
                    logger.info(f"💾 [STREAM][{trace_id}] Persisted full response to cache.")
                except Exception as e:
                    logger.warning(f"⚠️ Cache save failed: {e}")

            await finish_assistant_messages(pending_writes)

            # Completion signal
            if decision.intent == Intent.COURSE:
                yield yield_safe_sse_event(
                    "course_generation",
                    {
                        "type": "course_generation",
                        "phase": "ready",
                        "progress": 100,
                        "message": "Course ready",
                    },
                )
            latency_metrics["total_ms"] = int(
                (time.monotonic() - request_started) * 1000
            )
            yield yield_safe_sse_event(
                "latency",
                {"type": "latency", "metrics": latency_metrics},
            )
            yield "data: [DONE]\n\n"
            logger.info(f"🏁 [STREAM][{trace_id}] Total session time: {time.time()-start_time:.2f}s")

        except Exception as e:
            logger.error(f"💥 [STREAM][{trace_id}] Critical failure: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            await finish_assistant_messages(pending_writes)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
