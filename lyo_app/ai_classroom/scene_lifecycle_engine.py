"""
Lyo AI Classroom - Scene Lifecycle Engine
========================================

The live path assembles context, restores the learner's guided state, and runs
one adaptive teaching turn before persisting and streaming existing SDUI types.
The live engine owns persistence and streaming; AdaptiveSession owns teaching.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from uuid import uuid4
from weakref import WeakValueDictionary

from pydantic import BaseModel, Field
from sqlalchemy import select, func as sa_func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.ai_classroom.sdui_models import (
    Scene, SceneType, Component, ComponentType,
    TeacherMessage, CTAButton, InputField, ExampleBlock,
    AudioMood, ActionIntent, ClassroomMode, HintLevel,
)
# Pure vocabulary module — no app imports — so this is safe at module scope.
from lyo_app.events.evidence import strongest_hint_level

logger = logging.getLogger(__name__)

# Per-session guided state and progress, restored across live engine instances.
_SESSION_PROGRESS: Dict[str, Dict[str, Any]] = {}
_TURN_LOCKS = WeakValueDictionary()


def session_progress_key(user_id: str, session_id: str) -> str:
    return json.dumps([str(user_id), str(session_id)], ensure_ascii=False)

_HESITATION_PHRASES = (
    "not sure", "not really sure", "not certain", "unsure",
    "no idea", "i don't know", "i dont know", "idk", "no clue",
    "i'm confused", "im confused", "confused",
    "i'm stuck", "im stuck", "stuck",
    "i give up", "give up",
    "help me", "i need help", "can you help",
    "not following", "i'm lost", "im lost", "lost me",
)


def detect_hesitation(text: Optional[str]) -> bool:
    """Compatibility classifier; live teaching handles help in AdaptiveTeacher."""
    if not text:
        return False
    normalized = text.strip().lower()
    if not normalized:
        return False
    return any(phrase in normalized for phrase in _HESITATION_PHRASES)


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎭 PHASE 1: TRIGGER SYSTEM (Listen)
# ═══════════════════════════════════════════════════════════════════════════════════

class TriggerType(str, Enum):
    """Types of events that can trigger scene generation"""
    USER_ACTION = "user_action"           # User taps, submits, clicks
    SYSTEM_TIMEOUT = "system_timeout"     # Inactivity timeout
    MASTERY_THRESHOLD = "mastery_threshold"  # Mastery state change
    ACHIEVEMENT_UNLOCK = "achievement_unlock"  # Progress milestone
    PEER_INTERVENTION = "peer_intervention"   # AI student should speak
    FRUSTRATION_DETECTED = "frustration_detected"  # Multiple wrong answers
    CELEBRATION_DUE = "celebration_due"   # Success streak achieved


class Trigger(BaseModel):
    """Event that initiates a new scene lifecycle"""

    trigger_id: str = Field(default_factory=lambda: str(uuid4()))
    trigger_type: TriggerType
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Trigger payload
    user_id: str
    session_id: str
    course_id: Optional[str] = None

    # Event-specific data
    action_data: Optional[Dict[str, Any]] = None
    component_id: Optional[str] = None

    # Context hints for the Director
    urgency: int = Field(default=0, ge=0, le=10, description="0=background, 10=immediate")
    expected_scene_types: List[SceneType] = Field(default_factory=list)


class TriggerListener:
    """Listens for events that should trigger scene generation"""

    def __init__(self):
        self.handlers: Dict[TriggerType, List[Callable]] = {}
        self.timeout_tasks: Dict[str, asyncio.Task] = {}

    def register_handler(self, trigger_type: TriggerType, handler: Callable):
        """Register a handler for a specific trigger type"""
        if trigger_type not in self.handlers:
            self.handlers[trigger_type] = []
        self.handlers[trigger_type].append(handler)

    async def emit_trigger(self, trigger: Trigger) -> None:
        """Emit a trigger to all registered handlers"""
        handlers = self.handlers.get(trigger.trigger_type, [])
        logger.info(f"🎯 Trigger emitted: {trigger.trigger_type} → {len(handlers)} handlers")

        for handler in handlers:
            try:
                await handler(trigger)
            except Exception as e:
                logger.error(f"❌ Handler failed for {trigger.trigger_type}: {e}")

    def schedule_timeout(self, session_id: str, delay_seconds: int = 30) -> None:
        """Schedule a timeout trigger if user is inactive"""
        if session_id in self.timeout_tasks:
            self.timeout_tasks[session_id].cancel()

        async def timeout_handler():
            await asyncio.sleep(delay_seconds)
            await self.emit_trigger(Trigger(
                trigger_type=TriggerType.SYSTEM_TIMEOUT,
                user_id="system",
                session_id=session_id,
                urgency=3
            ))

        self.timeout_tasks[session_id] = asyncio.create_task(timeout_handler())

    def cancel_timeout(self, session_id: str) -> None:
        """Cancel pending timeout for active user"""
        if session_id in self.timeout_tasks:
            self.timeout_tasks[session_id].cancel()
            del self.timeout_tasks[session_id]


# ═══════════════════════════════════════════════════════════════════════════════════
# 🧠 PHASE 2: CONTEXT ASSEMBLY (Think)
# ═══════════════════════════════════════════════════════════════════════════════════

class KnowledgeState(BaseModel):
    """User's current learning state for specific concepts"""

    concept_id: str
    concept_name: Optional[str] = None
    mastery_level: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    last_attempt: Optional[datetime] = None
    consecutive_correct: int = 0
    consecutive_incorrect: int = 0
    total_attempts: int = 0


class FrustrationMetrics(BaseModel):
    """Quantified user frustration indicators"""

    frustration_score: float = Field(default=0.0, ge=0.0, le=1.0)
    consecutive_hints: int = 0
    consecutive_failures: int = 0
    time_spent_struggling_seconds: int = 0
    last_success: Optional[datetime] = None

    # Behavioral indicators
    response_time_variance: float = 0.0  # High variance = confusion
    rapid_clicking: bool = False         # Impatience indicator


class PeerState(BaseModel):
    """State of AI peer students in the session"""

    peer_name: str
    last_spoke: Optional[datetime] = None
    total_interventions: int = 0
    suppression_until: Optional[datetime] = None  # Cooldown period
    personality_trait: str = "supportive"


class ContextSnapshot(BaseModel):
    """Complete context assembled before Director makes decisions"""

    # User state
    user_id: str
    session_id: str
    current_scene_id: Optional[str] = None

    # Course / topic context
    topic: Optional[str] = None
    course_id: Optional[str] = None
    lesson_id: Optional[str] = None
    course_title: Optional[str] = None
    lesson_index: int = 0
    lesson_title: Optional[str] = None
    lesson_content: Optional[str] = None
    total_lessons: int = 0
    learning_objective: Optional[str] = None
    course_complete: bool = False
    classroom_mode: ClassroomMode = ClassroomMode.SOLO
    target_duration_minutes: int = Field(default=10, ge=3, le=60)
    language_code: str = Field(
        default="en-US",
        description="BCP-47 locale used for lesson generation and speech",
    )
    source_attributions: List[str] = Field(default_factory=list)
    review_due_items: List[str] = Field(default_factory=list)
    scheduled_due_items: List[str] = Field(default_factory=list)

    # Current learner input + durable personalization context
    learner_signal: Optional[str] = None
    learner_message: Optional[str] = None
    learner_response: Optional[str] = None
    learner_context: str = ""
    hint_level: Optional[HintLevel] = None
    misconception_tag: Optional[str] = None
    remediation_hint: Optional[str] = None
    answer_feedback: Optional[str] = None

    # Knowledge state
    knowledge_states: List[KnowledgeState] = Field(default_factory=list)
    overall_progress: float = Field(default=0.0, ge=0.0, le=1.0)

    # Emotional/behavioral state
    frustration: FrustrationMetrics = Field(default_factory=FrustrationMetrics)
    engagement_level: float = Field(default=0.5, ge=0.0, le=1.0)

    # Peer management
    active_peers: List[PeerState] = Field(default_factory=list)
    peer_cooldown_active: bool = False

    # Session context
    session_duration_minutes: int = 0
    scenes_completed: int = 0
    last_interaction: Optional[datetime] = None

    # Adaptive parameters
    preferred_difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    learning_velocity: float = Field(default=0.5, ge=0.0, le=2.0)
    attention_span_estimate: int = Field(default=300, description="Estimated attention span in seconds")


class TeachingBeat(BaseModel):
    """One learner-gated teaching turn, never a multi-character script."""

    speech: str = Field(..., min_length=3, max_length=700)
    board_title: str = Field(..., min_length=1, max_length=100)
    board_content: str = Field(..., min_length=1, max_length=1200)
    example_type: str = Field(default="real_world")


class ContextAssembler:
    """Builds comprehensive context snapshots for scene generation"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def assemble_context(self, trigger: Trigger) -> ContextSnapshot:
        """Build complete context snapshot from trigger and user state"""
        logger.info(f"🧠 Assembling context for user {trigger.user_id}")

        # Start with base context
        context = ContextSnapshot(
            user_id=trigger.user_id,
            session_id=trigger.session_id,
            last_interaction=trigger.timestamp
        )

        # Resolve topic / course from ConversationManager session
        context.topic, context.course_id, context.course_title, context.lesson_index = \
            await self._resolve_topic(trigger)

        # Hydrate guided-classroom position from the existing ClassroomSession
        # JSON context. This survives worker restarts without a schema migration.
        progress = _SESSION_PROGRESS.setdefault(
            session_progress_key(trigger.user_id, trigger.session_id), {"scene": 0, "covered": [], "mastered_lessons": []}
        )
        if not progress.get("_hydrated"):
            persisted = await self._load_persisted_session_progress(trigger)
            if persisted:
                progress.update(persisted)
            progress["_hydrated"] = True
        if "current_lesson_index" in progress:
            context.lesson_index = int(progress["current_lesson_index"] or 0)
        context.course_id = str(progress.get("course_id") or context.course_id or "") or None
        context.lesson_id = str(progress.get("lesson_id") or "") or None
        context.course_complete = bool(progress.get("course_complete", False))

        # Apply explicit launch identity before resolving content. A lesson URL
        # must open that authored lesson, rather than silently teaching index 0.
        action_data = trigger.action_data or {}
        # A failed first plan has no GuidedState yet. Keep the requested
        # filing scope across Retry and worker restarts so a transient model
        # error does not silently turn a free-topic pathway into a topic card.
        progress.setdefault(
            "record_scope", "unit" if action_data.get("record_scope") == "unit" else "topic"
        )
        explicit_course_id = action_data.get("course_id")
        explicit_lesson_id = action_data.get("lesson_id")
        if explicit_course_id:
            context.course_id = str(explicit_course_id)
            progress["course_id"] = context.course_id
        elif context.course_id:
            progress["course_id"] = context.course_id

        # Resolve current lesson content from the DB
        (
            resolved_lesson_id,
            context.lesson_index,
            context.lesson_title,
            context.lesson_content,
            context.total_lessons,
        ) = await self._resolve_current_lesson(
            context.course_id,
            context.lesson_index,
            requested_lesson_id=(
                str(explicit_lesson_id) if explicit_lesson_id else None
            ),
        )
        context.lesson_id = resolved_lesson_id or (
            str(explicit_lesson_id) if explicit_lesson_id else context.lesson_id
        )
        progress["current_lesson_index"] = context.lesson_index
        if context.lesson_id:
            progress["lesson_id"] = context.lesson_id
        # If lesson gave us a more specific topic, use it
        if context.lesson_title and not context.topic:
            context.topic = context.lesson_title
        if context.course_title or context.lesson_title:
            context.source_attributions = [
                "Course material"
                + (f": {context.course_title}" if context.course_title else "")
                + (f" — {context.lesson_title}" if context.lesson_title else "")
            ]

        # Preserve the learner-selected pace for the entire classroom
        # session. These values arrive on the welcome trigger and must
        # remain available on later WebSocket actions.
        explicit_objective = action_data.get("objective")
        if explicit_objective:
            progress["learning_objective"] = str(explicit_objective)

        # The per-scene teaching objective must track the CURRENT lesson,
        # not freeze on whatever generic prompt the learner typed at course
        # creation (e.g. "Learn the basic concepts of algebra"). That prompt
        # used to win here for the whole session, so every later lesson's
        # transfer question and rubric keywords were derived from it instead
        # of the actual lesson content — producing junk pseudo-concepts like
        # "learn"/"basic"/"concepts" ("Revise your application of Learn the
        # basic concepts..."). Prefer the resolved lesson_title when one
        # exists; fall back to the course-creation objective only for
        # freeform sessions with no discrete lesson to resolve.
        context.learning_objective = (
            context.lesson_title
            or progress.get("learning_objective")
            or context.topic
        )

        difficulty = action_data.get("difficulty")
        if difficulty:
            progress["difficulty"] = str(difficulty).lower()
        difficulty_map = {"beginner": 0.3, "intermediate": 0.6, "advanced": 0.85}
        context.preferred_difficulty = difficulty_map.get(
            progress.get("difficulty"), context.preferred_difficulty
        )

        mode = action_data.get("mode")
        requested_intent = action_data.get("action_intent")
        if requested_intent == ActionIntent.REQUEST_REVIEW:
            mode = ClassroomMode.REVIEW.value
        if mode:
            try:
                progress["classroom_mode"] = ClassroomMode(str(mode).lower()).value
            except ValueError:
                progress["classroom_mode"] = ClassroomMode.SOLO.value
        try:
            context.classroom_mode = ClassroomMode(
                progress.get("classroom_mode", ClassroomMode.SOLO.value)
            )
        except ValueError:
            context.classroom_mode = ClassroomMode.SOLO

        # Review mode re-opens the oldest skipped checkpoint against its own
        # authored lesson, while preserving the learner's normal course cursor.
        review_queue = list(progress.get("review_queue", []))
        if context.classroom_mode == ClassroomMode.REVIEW and review_queue:
            review_item = review_queue[0]
            try:
                context.lesson_index = int(review_item.get("lesson_index", context.lesson_index))
            except (TypeError, ValueError):
                pass
            requested_review_lesson_id = (
                str(review_item.get("lesson_id"))
                if review_item.get("lesson_id")
                else None
            )
            (
                resolved_review_lesson_id,
                context.lesson_index,
                context.lesson_title,
                context.lesson_content,
                context.total_lessons,
            ) = await self._resolve_current_lesson(
                context.course_id,
                context.lesson_index,
                requested_lesson_id=requested_review_lesson_id,
            )
            context.lesson_id = (
                resolved_review_lesson_id
                or requested_review_lesson_id
                or context.lesson_id
            )
            context.learning_objective = (
                review_item.get("objective")
                or context.lesson_title
                or context.learning_objective
            )
            context.source_attributions = [
                "Course material"
                + (f": {context.course_title}" if context.course_title else "")
                + (f" — {context.lesson_title}" if context.lesson_title else "")
            ]

        duration = action_data.get("duration_minutes")
        if duration is not None:
            try:
                progress["target_duration_minutes"] = max(3, min(60, int(duration)))
            except (TypeError, ValueError):
                pass
        context.target_duration_minutes = int(
            progress.get("target_duration_minutes", context.target_duration_minutes)
        )

        language = action_data.get("language") or action_data.get("language_code")
        if language:
            progress["language_code"] = str(language)
        from lyo_app.tts.service import TTSService
        context.language_code = TTSService.normalize_language(
            progress.get("language_code", "auto"),
            " ".join(
                value for value in (
                    context.lesson_title,
                    context.lesson_content,
                    context.topic,
                ) if value
            ),
            "en-US",
        )
        progress["language_code"] = context.language_code

        hint_level = action_data.get("hint_level")
        if hint_level:
            try:
                context.hint_level = HintLevel(str(hint_level))
                hint_counts = progress.setdefault("hint_counts", {})
                lesson_key = str(context.lesson_index)
                hint_counts[lesson_key] = int(hint_counts.get(lesson_key, 0)) + 1
                # `context` is rebuilt on every action, so by the time the
                # learner submits an answer `context.hint_level` is whatever
                # that submission carried — nothing. The rung has to outlive
                # the request that asked for it, or grading can only ever see
                # a count and a full worked example scores like a nudge.
                hint_levels = progress.setdefault("hint_levels", {})
                hint_levels[lesson_key] = strongest_hint_level(
                    hint_levels.get(lesson_key), context.hint_level.value
                )
            except ValueError:
                context.hint_level = HintLevel.NUDGE

        answer_data = action_data.get("answer_data", {})
        context.misconception_tag = answer_data.get("misconception_tag")
        context.remediation_hint = answer_data.get("remediation_hint")
        context.answer_feedback = answer_data.get("feedback")

        raw_intent = action_data.get("source_intent") or action_data.get("action_intent")
        context.learner_signal = (
            raw_intent.value if isinstance(raw_intent, ActionIntent) else raw_intent
        )
        message = action_data.get("message")
        if context.learner_signal == ActionIntent.ASK_QUESTION.value:
            context.learner_message = message
        else:
            context.learner_response = message
        context.learner_context = await self._get_learner_context(
            trigger.user_id, context.lesson_title or context.topic
        )
        skipped_review = [
            str(item.get("objective") or item.get("lesson_title") or "").strip()
            for item in review_queue
        ]
        context.review_due_items = list(dict.fromkeys(
            item for item in skipped_review if item
        ))
        # Spaced items can be mixed into an ordinary unit. Keep their origin
        # separate from the skipped queue: a recent revisit is not retention.
        context.scheduled_due_items = await self._get_due_review_items(trigger.user_id)
        context.review_due_items = list(dict.fromkeys(
            item for item in [*context.review_due_items, *context.scheduled_due_items] if item
        ))

        # Gather knowledge states
        context.knowledge_states = await self._get_knowledge_states(trigger.user_id)

        # Calculate frustration metrics
        context.frustration = await self._calculate_frustration(trigger)

        # Get peer states
        context.active_peers = await self._get_peer_states(trigger.session_id)

        # Session analytics
        context.session_duration_minutes = await self._get_session_duration(trigger.session_id)
        context.scenes_completed = await self._count_completed_scenes(trigger.session_id)

        # Behavioral analysis
        context.engagement_level = await self._calculate_engagement(trigger.user_id)
        context.learning_velocity = await self._calculate_learning_velocity(trigger.user_id)

        logger.info(f"✅ Context assembled: topic={context.topic!r}, "
                   f"{len(context.knowledge_states)} concepts, "
                   f"frustration={context.frustration.frustration_score:.2f}, "
                   f"engagement={context.engagement_level:.2f}")

        return context

    async def _load_persisted_session_progress(
        self, trigger: Trigger
    ) -> Dict[str, Any]:
        """Load the latest durable guided-classroom state for this learner."""
        try:
            user_id = int(trigger.user_id)
            from lyo_app.classroom.models import ClassroomSession
            result = await self.db.execute(
                select(ClassroomSession)
                .where(
                    and_(
                        ClassroomSession.user_id == user_id,
                        ClassroomSession.title == trigger.session_id,
                        ClassroomSession.session_type == "guided_ai",
                    )
                )
                .order_by(desc(ClassroomSession.updated_at))
                .limit(1)
            )
            session = result.scalars().first()
            return dict(session.context or {}) if session else {}
        except (ValueError, TypeError):
            return {}
        except Exception as e:
            from lyo_app.ai_classroom.adaptive_teaching import TeachingUnavailable
            raise TeachingUnavailable("Saved classroom state could not be loaded") from e

    async def _resolve_topic(
        self, trigger: Trigger
    ) -> tuple:
        """Resolve topic, course_id, course_title and lesson_index from the session."""
        topic = None
        course_id = trigger.course_id or (
            (trigger.action_data or {}).get("course_id")
        )
        course_title = None
        lesson_index = 0

        # 1) Check the trigger's action_data for an explicit topic
        if trigger.action_data:
            topic = trigger.action_data.get("topic") or trigger.action_data.get("subject")
            if topic and isinstance(topic, str):
                topic = topic.replace("**", "").strip()

        # 2) Look up the ConversationManager in-memory session
        if not topic:
            try:
                from lyo_app.ai_classroom.conversation_flow import get_conversation_manager
                cm = get_conversation_manager()
                conv_session = cm.get_session(trigger.session_id)
                if conv_session and str(conv_session.user_id) == str(trigger.user_id):
                    topic = conv_session.current_topic
                    if topic and isinstance(topic, str):
                        topic = topic.replace("**", "").strip()
                    course_id = course_id or conv_session.current_course_id
                    lesson_index = conv_session.current_lesson_index
            except Exception as e:
                logger.warning(f"⚠️ Could not look up ConversationSession: {e}")

        # 3) If we still don't have a course_id, try using session_id as course_id
        #    (iOS sends courseId as the WebSocket session_id)
        if not course_id:
            course_id = trigger.session_id

        if course_id and isinstance(course_id, str):
            course_id = course_id.replace("**", "").strip()

        # 4) If we have a course_id, query the Course DB for the title
        if course_id and not course_title:
            try:
                course_id_int = int(course_id)
                from sqlalchemy import select
                from lyo_app.learning.models import Course
                result = await self.db.execute(
                    select(Course.title, Course.topic).where(Course.id == course_id_int)
                )
                row = result.first()
                if row:
                    course_title = row.title
                    topic = topic or row.topic
            except ValueError:
                # It's a UUID, so it might be a GraphCourse, ChatCourse or GeneratedCourseModel
                try:
                    from lyo_app.ai_classroom.models import GraphCourse
                    from sqlalchemy import select
                    result = await self.db.execute(
                        select(GraphCourse.title, GraphCourse.subject).where(GraphCourse.id == course_id)
                    )
                    row = result.first()
                    if row:
                        course_title = row.title
                        topic = topic or row.subject
                    else:
                        # Try ChatCourse
                        from lyo_app.chat.models import ChatCourse
                        result = await self.db.execute(
                            select(ChatCourse.title, ChatCourse.topic).where(ChatCourse.id == course_id)
                        )
                        row = result.first()
                        if row:
                            course_title = row.title
                            topic = topic or row.topic
                        else:
                            # Try GeneratedCourseModel
                            from lyo_app.ai_agents.multi_agent_v2.pipeline.job_queue import GeneratedCourseModel
                            result = await self.db.execute(
                                select(GeneratedCourseModel.title, GeneratedCourseModel.topic).where(GeneratedCourseModel.id == course_id)
                            )
                            row = result.first()
                            if row:
                                course_title = row.title
                                topic = topic or row.topic
                except Exception as e:
                    logger.warning(f"⚠️ Could not query UUID course models: {e}")
            except Exception as e:
                logger.warning(f"⚠️ Could not query Course: {e}")

        # 5) Final fallback: web + GENERATE flows use a human-readable topic
        #    string AS the session id ("The French Revolution"). Without this,
        #    continue-triggered scenes lost the topic and taught "general
        #    learning" — the director then had nothing coherent to say.
        if not topic and trigger.session_id:
            sid = str(trigger.session_id).strip()
            looks_like_uuid = bool(re.fullmatch(r"[0-9a-fA-F\-]{32,36}", sid))
            if not looks_like_uuid and not sid.startswith(("gen_", "session_")) and 0 < len(sid) <= 80:
                topic = sid.replace("GENERATE:", "").strip()

        return topic, course_id, course_title, lesson_index

    async def _resolve_current_lesson(
        self,
        course_id: Optional[str],
        lesson_index: int,
        requested_lesson_id: Optional[str] = None,
    ) -> tuple:
        """Resolve canonical lesson identity and authored content for a course."""
        resolved_lesson_id = None
        resolved_lesson_index = lesson_index
        lesson_title = None
        lesson_content = None
        total_lessons = 0

        if not course_id:
            return (
                resolved_lesson_id,
                resolved_lesson_index,
                lesson_title,
                lesson_content,
                total_lessons,
            )

        try:
            course_id_int = int(course_id)
            from lyo_app.learning.models import Lesson

            requested_lesson_id_int = None
            if requested_lesson_id:
                try:
                    requested_lesson_id_int = int(requested_lesson_id)
                except (TypeError, ValueError):
                    pass

            # A canonical lesson ID from the launch URL wins over the cursor.
            lesson_filter = (
                Lesson.id == requested_lesson_id_int
                if requested_lesson_id_int is not None
                else Lesson.order_index == lesson_index
            )
            result = await self.db.execute(
                select(
                    Lesson.id,
                    Lesson.order_index,
                    Lesson.title,
                    Lesson.content,
                    Lesson.description,
                    Lesson.topic,
                )
                .where(
                    and_(
                        Lesson.course_id == course_id_int,
                        lesson_filter,
                    )
                )
                .limit(1)
            )
            row = result.first()
            if row:
                resolved_lesson_id = str(row.id)
                resolved_lesson_index = int(row.order_index)
                lesson_title = row.title
                lesson_content = row.content or row.description or ""
                logger.info(
                    f"📖 Resolved lesson {resolved_lesson_index} "
                    f"({resolved_lesson_id}): {lesson_title}"
                )

            # Get total lesson count
            count_result = await self.db.execute(
                select(sa_func.count(Lesson.id)).where(Lesson.course_id == course_id_int)
            )
            total_lessons = count_result.scalar() or 0
            logger.info(f"📚 Course {course_id} has {total_lessons} lessons")

        except ValueError:
            # It's a UUID, try getting lesson from GraphCourse first, then ChatCourse or GeneratedCourseModel
            try:
                from lyo_app.ai_classroom.models import GraphCourse, LearningNode
                from sqlalchemy import or_
                
                # Check if this course exists in GraphCourse by ID or Subject/Title (for topic sessions)
                course_result = await self.db.execute(
                    select(GraphCourse)
                    .where(
                        or_(
                            GraphCourse.id == course_id,
                            GraphCourse.subject == course_id,
                            GraphCourse.title.ilike(f"%{course_id}%")
                        )
                    )
                    .order_by(GraphCourse.created_at.desc())
                    .limit(1)
                )
                course_exists = course_result.scalars().first()
                
                if course_exists:
                    # Query all nodes for this course
                    nodes_result = await self.db.execute(
                        select(LearningNode)
                        .where(LearningNode.course_id == course_exists.id)
                        .order_by(LearningNode.sequence_order)
                    )
                    nodes = nodes_result.scalars().all()
                    
                    # Filter for narrative/lesson nodes
                    narrative_nodes = [n for n in nodes if n.node_type in ("narrative", "hook", "summary")]
                    
                    total_lessons = len(narrative_nodes)
                    if total_lessons > 0:
                        target_index = lesson_index
                        if requested_lesson_id:
                            requested_index = next(
                                (
                                    index
                                    for index, node in enumerate(narrative_nodes)
                                    if str(node.id) == str(requested_lesson_id)
                                ),
                                None,
                            )
                            if requested_index is not None:
                                target_index = requested_index
                        if 0 <= target_index < total_lessons:
                            target_node = narrative_nodes[target_index]
                            resolved_lesson_id = str(target_node.id)
                            resolved_lesson_index = target_index
                            keywords = target_node.content.get("keywords") or ["Overview"]
                            keyword = keywords[0] if keywords else "Overview"
                            lesson_title = target_node.content.get("title") or f"Lesson {target_index + 1}: {keyword.title()}"
                            lesson_content = target_node.content.get("narration", "")
                            if target_node.content.get("code"):
                                lang = target_node.content.get("language") or ""
                                code_str = target_node.content.get("code")
                                lesson_content += f"\n\nCode Example:\n```{lang}\n{code_str}\n```"
                            logger.info(f"📖 Resolved GraphCourse lesson {target_index}: {lesson_title}")
                    return (
                        resolved_lesson_id,
                        resolved_lesson_index,
                        lesson_title,
                        lesson_content,
                        total_lessons,
                    )
            except Exception as e:
                logger.warning(f"⚠️ Could not query GraphCourse for lessons: {e}")

            # Fallback to other UUID models (ChatCourse or GeneratedCourseModel)
            try:
                from lyo_app.chat.models import ChatCourse
                result = await self.db.execute(
                    select(ChatCourse.modules).where(ChatCourse.id == course_id)
                )
                row = result.first()
                modules = []
                if row and row.modules:
                    modules = row.modules
                else:
                    from lyo_app.ai_agents.multi_agent_v2.pipeline.job_queue import GeneratedCourseModel
                    result = await self.db.execute(
                        select(GeneratedCourseModel.course_data).where(GeneratedCourseModel.id == course_id)
                    )
                    row = result.first()
                    if row and row[0]:
                        import json as _json
                        cdata = row[0]
                        if isinstance(cdata, str):
                            try:
                                cdata = _json.loads(cdata)
                            except Exception:
                                cdata = {}
                        if isinstance(cdata, dict):
                            modules = cdata.get("curriculum", {}).get("modules", [])
                
                if modules:
                    # Flatten lessons from modules to find the one matching lesson_index
                    all_lessons = []
                    for module in modules:
                        module_lessons = module.get("lessons", [])
                        all_lessons.extend(module_lessons)
                    
                    total_lessons = len(all_lessons)
                    target_index = lesson_index
                    if requested_lesson_id:
                        requested_index = next(
                            (
                                index
                                for index, lesson in enumerate(all_lessons)
                                if str(lesson.get("id") or lesson.get("lesson_id") or "")
                                == str(requested_lesson_id)
                            ),
                            None,
                        )
                        if requested_index is not None:
                            target_index = requested_index
                    if 0 <= target_index < total_lessons:
                        lesson = all_lessons[target_index]
                        raw_lesson_id = lesson.get("id") or lesson.get("lesson_id")
                        resolved_lesson_id = (
                            str(raw_lesson_id) if raw_lesson_id is not None else None
                        )
                        resolved_lesson_index = target_index
                        lesson_title = lesson.get("title")
                        lesson_content = lesson.get("content") or lesson.get("description") or lesson.get("summary") or ""
                        logger.info(f"📖 Resolved chat/gen lesson {target_index}: {lesson_title}")
                    
            except Exception as e:
                logger.warning(f"⚠️ Could not query UUID course models for lesson: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Could not query Lesson: {e}")

        return (
            resolved_lesson_id,
            resolved_lesson_index,
            lesson_title,
            lesson_content,
            total_lessons,
        )

    async def _get_due_review_items(self, user_id: str) -> List[str]:
        """Return scheduled retrieval items without blocking guest sessions."""
        try:
            user_id_int = int(user_id)
            from lyo_app.personalization.service import PersonalizationEngine
            return await PersonalizationEngine()._get_due_repetitions(
                self.db, user_id_int
            )
        except (ValueError, TypeError):
            return []
        except Exception as exc:
            logger.debug("Could not load spaced-repetition queue: %s", exc)
            try:
                await self.db.rollback()
            except Exception:
                pass
            return []

    async def _get_knowledge_states(self, user_id: str) -> List[KnowledgeState]:
        """Retrieve mastery from the canonical personalization model.

        LearnerMastery is also written by quiz submission, so the live
        classroom reads the same evidence that the rest of personalization
        uses. Legacy classroom mastery remains a migration fallback.
        """
        async def names_for(keys):
            from lyo_app.events.mastery_projection import is_concept_graph_id
            ids = [key for key in keys if is_concept_graph_id(key)]
            if not ids:
                return {}
            from lyo_app.ai_classroom.models import Concept
            try:
                async with self.db.begin_nested():
                    rows = (await self.db.execute(select(
                        Concept.id, Concept.display_name, Concept.name,
                    ).where(Concept.id.in_(ids)))).all()
                return {identity: display or name for identity, display, name in rows}
            except Exception:
                logger.debug("Skill titles unavailable in the classroom context")
                return {}

        try:
            user_id_int = int(user_id)
            from lyo_app.personalization.models import LearnerMastery
            result = await self.db.execute(
                select(LearnerMastery).where(LearnerMastery.user_id == user_id_int)
            )
            rows = result.scalars().all()
            if rows:
                titles = await names_for([r.skill_id for r in rows])
                return [
                    KnowledgeState(
                        concept_id=r.skill_id,
                        concept_name=titles.get(r.skill_id),
                        mastery_level=r.mastery_level or 0.0,
                        confidence=max(0.0, min(1.0, 1.0 - (r.uncertainty or 0.5))),
                        total_attempts=r.attempts or 0,
                        last_attempt=r.last_seen,
                    )
                    for r in rows
                ]
        except (ValueError, TypeError):
            logger.debug("Guest classroom has no durable learner mastery")
        except Exception as e:
            logger.warning(f"⚠️ Could not query learner mastery: {e}")

        try:
            from lyo_app.ai_classroom.models import MasteryState as MasteryStateDB
            result = await self.db.execute(
                select(MasteryStateDB).where(MasteryStateDB.user_id == user_id)
            )
            rows = result.scalars().all()
            titles = await names_for([r.concept_id for r in rows])
            return [
                KnowledgeState(
                    concept_id=r.concept_id or r.objective_id or "unknown",
                    concept_name=titles.get(r.concept_id),
                    mastery_level=r.mastery_score,
                    confidence=r.confidence,
                    consecutive_correct=r.correct_count,
                    consecutive_incorrect=r.incorrect_count,
                    total_attempts=r.attempts,
                    last_attempt=r.last_seen,
                )
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"⚠️ Could not query legacy mastery states: {e}")
            return []

    async def _get_learner_context(
        self, user_id: str, current_skill: Optional[str]
    ) -> str:
        """Load durable learner preferences and relevant memory for teaching."""
        try:
            int(user_id)
            from lyo_app.personalization.service import PersonalizationEngine
            return await PersonalizationEngine().build_prompt_context(
                self.db, user_id, current_skill=current_skill
            )
        except (ValueError, TypeError):
            return ""
        except Exception as e:
            logger.debug(f"ℹ️ Could not build learner prompt context: {e}")
            return ""

    async def _calculate_frustration(self, trigger: Trigger) -> FrustrationMetrics:
        """Calculate user frustration based on recent interactions"""
        frustration = FrustrationMetrics()

        # Check the current trigger for hint requests
        if trigger.trigger_type == TriggerType.USER_ACTION:
            action_data = trigger.action_data or {}
            if action_data.get("action_intent") == "request_hint":
                frustration.consecutive_hints += 1

        # Query recent interaction attempts for failure streaks
        try:
            from lyo_app.ai_classroom.models import InteractionAttempt
            result = await self.db.execute(
                select(InteractionAttempt.is_correct)
                .where(InteractionAttempt.user_id == trigger.user_id)
                .order_by(desc(InteractionAttempt.created_at))
                .limit(10)
            )
            recent = [row[0] for row in result.all()]
            # Count consecutive failures from most recent
            for correct in recent:
                if not correct:
                    frustration.consecutive_failures += 1
                else:
                    break
        except Exception as e:
            logger.debug(f"ℹ️ Could not query interaction attempts for frustration: {e}")

        # Compute frustration score: weight failures more than hints
        frustration.frustration_score = min(
            1.0,
            frustration.consecutive_failures * 0.2 + frustration.consecutive_hints * 0.15
        )
        return frustration

    async def _get_peer_states(self, session_id: str) -> List[PeerState]:
        """Get state of AI peer students in this session.
        AI peers are synthetic — no DB table. We keep a static configuration."""
        return [
            PeerState(
                peer_name="Sam",
                personality_trait="curious",
                total_interventions=0
            )
        ]

    async def _get_session_duration(self, session_id: str) -> int:
        """Calculate session duration in minutes from ClassroomSession"""
        try:
            from lyo_app.classroom.models import ClassroomSession
            result = await self.db.execute(
                select(ClassroomSession.created_at)
                .where(
                    and_(
                        ClassroomSession.is_active == True,
                        ClassroomSession.id == int(session_id) if session_id.isdigit()
                        else ClassroomSession.title == session_id,
                    )
                )
                .limit(1)
            )
            row = result.first()
            if row and row[0]:
                delta = datetime.utcnow() - row[0]
                return max(0, int(delta.total_seconds() / 60))
        except Exception as e:
            logger.debug(f"ℹ️ Could not query session duration: {e}")
        return 0

    async def _count_completed_scenes(self, session_id: str) -> int:
        """Count completed scene interactions in this session"""
        try:
            from lyo_app.classroom.models import ClassroomInteraction
            sess_id = int(session_id) if session_id.isdigit() else None
            if sess_id is not None:
                result = await self.db.execute(
                    select(sa_func.count(ClassroomInteraction.id))
                    .where(ClassroomInteraction.session_id == sess_id)
                )
                count = result.scalar() or 0
                return count
        except Exception as e:
            logger.debug(f"ℹ️ Could not count completed scenes: {e}")
        return 0

    async def _calculate_engagement(self, user_id: str) -> float:
        """Calculate user engagement from UserEngagementState table"""
        try:
            from lyo_app.ai_agents.models import UserEngagementState, UserEngagementStateEnum
            # user_id may be str UUID; UserEngagementState uses int FK
            uid = int(user_id) if user_id.isdigit() else None
            if uid is not None:
                result = await self.db.execute(
                    select(UserEngagementState.state, UserEngagementState.sentiment_score)
                    .where(UserEngagementState.user_id == uid)
                )
                row = result.first()
                if row:
                    state, sentiment = row
                    # Map state to engagement multiplier
                    state_scores = {
                        UserEngagementStateEnum.ENGAGED: 0.9,
                        UserEngagementStateEnum.CURIOUS: 0.85,
                        UserEngagementStateEnum.CONFIDENT: 0.8,
                        UserEngagementStateEnum.IDLE: 0.4,
                        UserEngagementStateEnum.BORED: 0.3,
                        UserEngagementStateEnum.STRUGGLING: 0.5,
                        UserEngagementStateEnum.FRUSTRATED: 0.2,
                    }
                    base = state_scores.get(state, 0.5)
                    # Blend with sentiment (-1..1 mapped to 0..1)
                    sentiment_factor = (sentiment + 1.0) / 2.0 if sentiment is not None else 0.5
                    return round(base * 0.7 + sentiment_factor * 0.3, 2)
        except Exception as e:
            logger.debug(f"ℹ️ Could not query engagement state: {e}")
        return 0.5

    async def _calculate_learning_velocity(self, user_id: str) -> float:
        """Calculate learning velocity from mastery trend data"""
        try:
            from lyo_app.ai_classroom.models import MasteryState as MasteryStateDB
            result = await self.db.execute(
                select(MasteryStateDB.trend)
                .where(MasteryStateDB.user_id == user_id)
            )
            trends = [row[0] for row in result.all()]
            if trends:
                improving = sum(1 for t in trends if t == "improving")
                declining = sum(1 for t in trends if t == "declining")
                total = len(trends)
                # velocity: 1.0 = average, >1 = fast learner, <1 = slower
                return round(0.5 + (improving / total) - (declining / total * 0.5), 2)
        except Exception as e:
            logger.debug(f"ℹ️ Could not calculate learning velocity: {e}")
        return 1.0


# ═══════════════════════════════════════════════════════════════════════════════════
# Compatibility decision schema used by agent_integration
# ═══════════════════════════════════════════════════════════════════════════════════

class DirectorDecision(BaseModel):
    """Decision made by the Classroom Director"""

    selected_scene_type: SceneType
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)

    # Scene parameters
    estimated_duration_seconds: int = Field(default=30, ge=5, le=600)
    difficulty_adjustment: float = Field(default=0.0, ge=-0.5, le=0.5)

    # Component hints for older integrations
    suggested_components: List[ComponentType] = Field(default_factory=list)
    require_audio: bool = False
    require_interaction: bool = False

    # Timing
    decision_time_ms: float = 0.0


def session_concept(context: Optional["ContextSnapshot"]) -> Optional[str]:
    """Use the lesson/topic identity, never the prose learning objective."""
    if context is None:
        return None
    return getattr(context, "lesson_title", None) or getattr(context, "topic", None)


# The live engine restores guided state and renders AdaptiveSession scenes.

class SceneLifecycleEngine:
    """Orchestrate the shared adaptive teaching pathway and durable learner state."""

    # Class-level state tracking to persist across transient instances
    _active_scenes: Dict[str, Scene] = {}
    _session_contexts: Dict[str, Any] = {}
    _session_lesson_indices: Dict[str, int] = {}

    def __init__(self, db: AsyncSession, websocket_manager: Optional[Any] = None):
        # Phase components
        self.trigger_listener = TriggerListener()
        self.context_assembler = ContextAssembler(db)
        # Infrastructure
        self.db = db
        self.websocket_manager = websocket_manager

        # State tracking (shared class-level dicts to persist across transient instances)
        self.active_scenes = SceneLifecycleEngine._active_scenes
        self.session_contexts = SceneLifecycleEngine._session_contexts
        self.session_lesson_indices = SceneLifecycleEngine._session_lesson_indices

        # Register default handlers
        self._register_handlers()

    async def _persist_session_progress(
        self,
        trigger: Trigger,
        context: ContextSnapshot,
        progress: Dict[str, Any],
        *, record_interaction: bool = True,
    ) -> bool:
        """Persist guided classroom position in ClassroomSession.context."""
        try:
            user_id = int(trigger.user_id)
            from lyo_app.classroom.models import ClassroomInteraction, ClassroomSession
            result = await self.db.execute(
                select(ClassroomSession)
                .where(
                    and_(
                        ClassroomSession.user_id == user_id,
                        ClassroomSession.title == trigger.session_id,
                        ClassroomSession.session_type == "guided_ai",
                    )
                )
                .order_by(desc(ClassroomSession.updated_at))
                .limit(1)
            )
            session = result.scalars().first()
            if not session:
                session = ClassroomSession(
                    user_id=user_id,
                    title=trigger.session_id,
                    subject=context.topic,
                    session_type="guided_ai",
                    context={},
                )
                self.db.add(session)
                await self.db.flush()

            durable_context = dict(session.context or {})
            durable_context.update({
                "guided_state": progress.get("guided_state"),
                "guided_history": progress.get("guided_history", []),
                "current_lesson_index": progress.get(
                    "current_lesson_index", context.lesson_index
                ),
                "active_review_lesson_index": progress.get("active_review_lesson_index"),
                "course_id": progress.get("course_id") or context.course_id,
                "lesson_id": progress.get("lesson_id") or context.lesson_id,
                "mastered_lessons": list(progress.get("mastered_lessons", [])),
                "skipped_lessons": list(progress.get("skipped_lessons", [])),
                "evidence": dict(progress.get("evidence", {})),
                "attempt_history": list(progress.get("attempt_history", []))[-100:],
                "review_queue": list(progress.get("review_queue", []))[-50:],
                "hint_counts": dict(progress.get("hint_counts", {})),
                # The rung, not just the tally. Persisting only the count
                # meant that after a worker restart or a reconnect grading
                # could see that help was taken but not which kind — so a full
                # worked example scored like a nudge again, which is the exact
                # gap the rung was added to close.
                "hint_levels": dict(progress.get("hint_levels", {})),
                "misconception_history": list(progress.get("misconception_history", []))[-12:],
                "learning_objective": progress.get("learning_objective"),
                "record_scope": progress.get("record_scope", "topic"),
                "difficulty": progress.get("difficulty"),
                "classroom_mode": progress.get("classroom_mode", ClassroomMode.SOLO.value),
                "target_duration_minutes": progress.get("target_duration_minutes", 10),
                "language_code": progress.get("language_code", context.language_code),
                "course_complete": context.course_complete,
                "scene": progress.get("scene", 0),
                "covered": list(progress.get("covered", []))[-8:],
            })
            session.context = durable_context
            session.subject = context.topic or session.subject
            has_pending_review = bool(progress.get("review_queue")) or bool(
                (progress.get("guided_state") or {}).get("skipped")
            ) or any(snapshot.get("skipped") for snapshot in progress.get("guided_history", []))
            session.is_active = not context.course_complete or has_pending_review
            session.updated_at = datetime.utcnow()
            if context.course_complete and not has_pending_review:
                session.ended_at = datetime.utcnow()

            action_data = trigger.action_data or {}
            raw_intent = action_data.get("action_intent")
            try:
                action_intent = (
                    raw_intent
                    if isinstance(raw_intent, ActionIntent)
                    else ActionIntent(raw_intent)
                )
            except (TypeError, ValueError):
                action_intent = None
            recordable_intents = {
                ActionIntent.SUBMIT_ANSWER,
                ActionIntent.SUBMIT_TRANSFER,
                ActionIntent.SKIP_QUESTION,
                ActionIntent.REQUEST_HINT,
                ActionIntent.RETRY,
            }
            if record_interaction and action_intent in recordable_intents:
                answer_data = action_data.get("answer_data", {})
                response = str(
                    answer_data.get("response")
                    or action_data.get("message")
                    or ""
                ).strip()
                response_time_ms = (
                    answer_data.get("response_time_ms")
                    or action_data.get("response_time_ms")
                )
                try:
                    duration_seconds = (
                        max(float(response_time_ms) / 1000.0, 0.0)
                        if response_time_ms is not None
                        else None
                    )
                except (TypeError, ValueError):
                    duration_seconds = None
                # Client-supplied is_correct is never analytics evidence.
                # Canonical graded events are emitted from the durable outbox.
                is_correct = None
                self.db.add(ClassroomInteraction(
                    session_id=session.id,
                    event_type=action_intent.value,
                    card_id=trigger.component_id or f"lesson-{context.lesson_index}",
                    topic=context.learning_objective or context.lesson_title or context.topic,
                    duration_seconds=duration_seconds,
                    is_correct=is_correct,
                    word_count=len(response.split()) if response else None,
                ))
            await self.db.commit()
            return True
        except (ValueError, TypeError):
            return False
        except Exception as e:
            logger.warning(f"⚠️ Could not persist classroom progress: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return False

    def _register_handlers(self):
        """Register default trigger handlers"""
        self.trigger_listener.register_handler(
            TriggerType.USER_ACTION,
            self._handle_user_action_trigger
        )
        self.trigger_listener.register_handler(
            TriggerType.SYSTEM_TIMEOUT,
            self._handle_timeout_trigger
        )

    async def process_trigger(self, trigger: Trigger) -> Scene:
        """Run one learner-paced turn against the latest durable state."""
        from lyo_app.ai_classroom.adaptive_persistence import learner_session
        from lyo_app.ai_classroom.adaptive_session import AdaptiveSession

        key = session_progress_key(trigger.user_id, trigger.session_id)
        lock = _TURN_LOCKS.setdefault(key, asyncio.Lock())
        async with lock:
            original_db = self.db
            original_assembler_db = self.context_assembler.db
            try:
                async with learner_session(self.db, key) as db:
                    self.db = self.context_assembler.db = db
                    progress = _SESSION_PROGRESS.setdefault(key, {})
                    # Re-read on every turn: another worker/device may have
                    # accepted an answer since this worker last saw the session.
                    if not progress.get("_unsynced"):
                        progress["_hydrated"] = False
                    scene = await self._process_adaptive_trigger(trigger, key)
            except Exception as exc:
                logger.exception("Guided classroom turn unavailable: %s", type(exc).__name__)
                context = self.session_contexts.get(key) or ContextSnapshot(
                    user_id=trigger.user_id, session_id=trigger.session_id
                )
                scene = AdaptiveSession(None).unavailable(context, None)
            finally:
                self.db = original_db
                self.context_assembler.db = original_assembler_db
            self.active_scenes[scene.scene_id] = scene
            if self.websocket_manager and (
                (trigger.action_data or {}).get("action_intent") != ActionIntent.UPDATE_ACTIVITY
                or _SESSION_PROGRESS.get(key, {}).get("_unsynced")
            ):
                await self.websocket_manager.stream_scene_to_session(
                    trigger.session_id, scene, user_id=trigger.user_id
                )
            return scene

    async def _process_adaptive_trigger(self, trigger: Trigger, key: str) -> Scene:
        from lyo_app.ai_classroom.adaptive_teaching import AdaptiveTeacher, GuidedState
        from lyo_app.ai_classroom.adaptive_session import AdaptiveSession

        context = await self.context_assembler.assemble_context(trigger)
        progress = _SESSION_PROGRESS.setdefault(key, {})
        data = trigger.action_data or {}
        intent = data.get("action_intent")
        raw_state = progress.get("guided_state")
        record_interaction = intent != ActionIntent.UPDATE_ACTIVITY and (
            not raw_state or trigger.component_id not in raw_state.get("handled", [])
        )
        if raw_state:
            state = GuidedState.model_validate(raw_state)
            if state.course_id != context.course_id or state.lesson_id != context.lesson_id:
                # An explicit different lesson never inherits another lesson's
                # active question or grading rubric. Keep its state for review.
                history = progress.get("guided_history", [])
                matching = next((s for s in reversed(history)
                                 if s.get("course_id") == context.course_id
                                 and s.get("lesson_id") == context.lesson_id), None)
                progress["guided_history"] = [
                    *[s for s in history if (s.get("course_id"), s.get("lesson_id"))
                      not in ((state.course_id, state.lesson_id), (context.course_id, context.lesson_id))],
                    state.model_dump(mode="json"),
                ]
                if matching:
                    progress["guided_state"] = matching
                else:
                    progress.pop("guided_state", None)
                raw_state = progress.get("guided_state")
                state = GuidedState.model_validate(raw_state) if raw_state else None
            # The next authored lesson begins only on explicit Continue.
            if (state and state.path_done and intent == ActionIntent.CONTINUE
                    and AdaptiveSession.current_continue(state, trigger)
                    and context.lesson_index + 1 < context.total_lessons):
                resolved = await self.context_assembler._resolve_current_lesson(
                    context.course_id, context.lesson_index + 1
                )
                context.lesson_id, context.lesson_index, context.lesson_title, context.lesson_content, context.total_lessons = resolved
                context.learning_objective = context.lesson_title or context.topic
                progress["guided_history"] = [
                    *progress.get("guided_history", []), state.model_dump(mode="json"),
                ]
                progress.pop("guided_state", None)
                progress["current_lesson_index"] = context.lesson_index
                progress["lesson_id"] = context.lesson_id
        from lyo_app.ai_classroom.skill_identity import resolve_skill_plan
        from lyo_app.ai_classroom.unit_package_cache import DatabaseUnitPackageCache

        async def resolve_skills(classroom_context, plan):
            return await resolve_skill_plan(self.db, classroom_context, plan)

        runner = AdaptiveSession(
            getattr(self, "adaptive_teacher", None) or AdaptiveTeacher(
                package_cache=DatabaseUnitPackageCache(self.db)),
            skill_resolver=(resolve_skills if not hasattr(self, "skill_resolver")
                            else self.skill_resolver),
        )
        scene = await runner.run(context, progress, trigger)
        state_data = progress.get("guided_state")
        if state_data:
            state = GuidedState.model_validate(state_data)
            context.course_complete = (
                state.path_done and not state.skipped
                and not any(snapshot.get("skipped") for snapshot in progress.get("guided_history", []))
                and not (context.lesson_index + 1 < context.total_lessons)
            )
            context.overall_progress = len(state.completed) / len(state.plan.units)
        else:
            context.course_complete = False
        progress["course_complete"] = context.course_complete
        progress["current_lesson_index"] = context.lesson_index
        self.session_contexts[key] = context
        saved = await self._persist_session_progress(
            trigger, context, progress, record_interaction=record_interaction
        )
        progress["_unsynced"] = not saved
        if not saved:
            # Do not claim resumability or commit grading after a save failure.
            # Retain the active state locally so Retry can save it later.
            warning = runner.copy(context,
                "This step has not synced. Keep this classroom open and retry before leaving; progress may not resume on another device.",
                "Este paso no se ha sincronizado. Mantén esta aula abierta y reintenta antes de salir; podría no reanudarse en otro dispositivo.")
            # On the board beside the Retry control, not in the teacher's voice.
            # This is a product warning about syncing — consequential, and the
            # learner has to act on it — and the scene already carries the
            # teacher's own line about the lesson. A teacher who narrates the
            # backend's problems stops being a teacher.
            scene.components.insert(0, ExampleBlock(
                component_id="classroom-recovery/sync",
                title=runner.copy(context, "Save this step before leaving", "Guarda este paso antes de salir"),
                content=warning, language_code=context.language_code,
            ))
            if not any(getattr(c, "action_intent", None) == ActionIntent.RETRY for c in scene.components):
                scene.components.append(CTAButton(
                    label=runner.copy(context, "Retry saving", "Reintentar guardar"),
                    action_intent=ActionIntent.RETRY, language_code=context.language_code,
                ))
            return scene
        # A durable outbox closes the crash window between consuming a question
        # and recording evidence. Replaying it is safe by checkpoint event ID.
        snapshots = [s for s in [state_data, *progress.get("guided_history", [])] if s]
        outbox_states = [s for s in snapshots if s.get("outbox")]
        # A finished unit also owes the learner a review. Both queues drain
        # under one persist so a crash cannot lose one and keep the other.
        review_states = [s for s in snapshots if s.get("review_outbox")]
        if outbox_states or review_states:
            for snapshot in outbox_states:
                remaining = []
                for evidence in snapshot["outbox"]:
                    if not await self._record_adaptive_evidence(**evidence):
                        remaining.append(evidence)
                snapshot["outbox"] = remaining
            for snapshot in review_states:
                remaining = []
                for review in snapshot["review_outbox"]:
                    if not await self._schedule_adaptive_review(**review):
                        remaining.append(review)
                snapshot["review_outbox"] = remaining
            await self._persist_session_progress(trigger, context, progress, record_interaction=False)
        return scene

    async def _schedule_adaptive_review(self, *, user_id, concept_id, passed,
                                        decided_at=None, **_ignored) -> bool:
        """Advance this learner's spaced-review schedule for a finished unit.

        The classroom had no way into the scheduler at all: the only writers
        were Chat's answer check and the review endpoints, and those endpoints
        can only update a schedule that already exists. So nothing a learner
        did here ever became due, and the review queue they were offered stayed
        empty however many units they finished. This is that missing write, and
        it goes through `record_review` — the one SM-2 in the product — rather
        than keeping a second schedule the way the classroom used to.

        Replaying the queue is safe. `decided_at` is the moment the unit was
        decided, and a schedule already reviewed at or after that moment has
        had this write applied, so it is skipped rather than advanced twice —
        which would quietly push the learner's next review further out than
        their work earned.
        """
        from datetime import datetime as _datetime

        concept = self._canonical_concept_id(concept_id)
        if not concept:
            return True
        try:
            learner_id = int(user_id)
        except (TypeError, ValueError):
            return True  # Guests have no durable schedule.
        try:
            from lyo_app.personalization.models import SpacedRepetitionSchedule
            from lyo_app.personalization.service import personalization_engine
            from lyo_app.personalization.spaced_repetition import (
                QUALITY_FOR_CORRECT, QUALITY_FOR_INCORRECT)

            decided = None
            if isinstance(decided_at, str) and decided_at:
                try:
                    decided = _datetime.fromisoformat(decided_at)
                    if decided.tzinfo is not None:
                        decided = decided.replace(tzinfo=None)
                except ValueError:
                    decided = None
            if decided is not None:
                existing = (await self.db.execute(select(SpacedRepetitionSchedule).where(
                    SpacedRepetitionSchedule.user_id == learner_id,
                    SpacedRepetitionSchedule.item_id == concept,
                ).limit(1))).scalar_one_or_none()
                if existing is not None and isinstance(existing.last_review, _datetime) \
                        and existing.last_review >= decided:
                    return True

            await personalization_engine.record_review(
                self.db, learner_id, concept, concept,
                QUALITY_FOR_CORRECT if passed else QUALITY_FOR_INCORRECT,
            )
            return True
        except Exception as exc:
            logger.warning("Could not schedule classroom review: %s", type(exc).__name__)
            await self.db.rollback()
            return False

    async def _record_adaptive_evidence(self, **evidence) -> bool:
        """Deduplicate evidence; only use measured response time for legacy DKT."""
        event_id = evidence.pop("event_id")
        response_time_ms = evidence.pop("response_time_ms", None)
        try:
            learner_id = int(evidence["user_id"])
        except (TypeError, ValueError):
            return True  # Guests have no durable learner record.
        from lyo_app.events.models import EventType, LearningEvent
        try:
            prior = await self.db.execute(select(LearningEvent.id).where(
                LearningEvent.user_id == learner_id,
                LearningEvent.event_type == EventType.CLASSROOM_DEMONSTRATION,
                LearningEvent.measurable_outcome.is_not(None),
                LearningEvent.source_surface == "classroom",
                LearningEvent.metadata_json["classroom_checkpoint_id"].as_string() == event_id,
            ).limit(1))
            if prior.scalar_one_or_none() is not None:
                return True
            if not await self._log_classroom_evidence(**evidence, event_id=event_id):
                return False
            concept_id = self._canonical_concept_id(evidence.get("concept_id"))
            # Missing timing is unknown, not a fictional one-second answer.
            if concept_id and isinstance(response_time_ms, (int, float)) and 0 < response_time_ms < 3600000:
                from lyo_app.personalization.service import PersonalizationEngine
                await PersonalizationEngine().dkt.update_mastery(
                    self.db, learner_id, concept_id, evidence["correct"],
                    response_time_ms / 1000.0, evidence.get("hints_used", 0),
                )
            return True
        except Exception as exc:
            logger.warning("Could not persist classroom evidence: %s", type(exc).__name__)
            await self.db.rollback()
            return False

    async def _handle_user_action_trigger(self, trigger: Trigger):
        """Handle user action triggers"""
        # Cancel any pending timeouts since user is active
        self.trigger_listener.cancel_timeout(trigger.session_id)

        # Process the action
        await self.process_trigger(trigger)

        # Deliberately do not schedule an inactivity scene. The learner owns the
        # floor until they answer, ask for help, skip, or explicitly continue.

    async def _handle_timeout_trigger(self, trigger: Trigger):
        """Handle system timeout triggers"""
        scene = await self.process_trigger(trigger)
        # Don't schedule another timeout after this gentle nudge

    async def _stream_scene_to_client(self, scene: Scene, session_id: str):
        """Stream scene to client via WebSocket"""
        if not self.websocket_manager:
            return

        await self.websocket_manager.stream_scene_to_session(session_id, scene)

    #: How much of the lesson to re-present when teaching from the fallback.
    #: Long enough to be a real re-teach, short enough not to dump a whole
    #: lesson into one bubble.
    _FALLBACK_TEACHING_CHARS = 700

    @staticmethod
    def _excerpt_for_reteaching(content: Optional[str], limit: int) -> Optional[str]:
        """Take the opening of the lesson, cut at a sentence boundary.

        Returns None when there is nothing usable, so the caller can choose a
        different fallback rather than showing an empty or truncated bubble.

        This only ever re-presents text the course already provided. The
        fallback runs when generation failed, which is precisely the moment
        not to invent teaching material.
        """
        text = (content or "").strip()
        if len(text) < 40:
            return None
        if len(text) <= limit:
            return text

        window = text[:limit]
        # Prefer the last sentence end; fall back to the last paragraph or
        # word break so the excerpt never stops mid-word.
        cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
        if cut > limit // 3:
            return window[: cut + 1].strip()
        cut = max(window.rfind("\n\n"), window.rfind(" "))
        if cut > limit // 3:
            return window[:cut].strip() + "…"
        return window.strip() + "…"

    async def _create_fallback_scene(self, trigger: Trigger) -> Scene:
        """Teach something safe when the lifecycle fails.

        WHY THIS IS NOT A "SORRY" SCREEN

        This runs when the Director or the compiler raised — the learner is
        mid-lesson and the next scene could not be produced. What they used to
        get here was "Let's continue with one idea at a time when you're
        ready." and a Continue button: a polite dead end that teaches nothing
        and hands them no way forward except to press the same button again.

        That dead end is what iOS's on-device teaching engine existed to paper
        over — its own header said the screen "went dead" when the backend
        stopped streaming scenes. That engine has been removed, correctly,
        because a client-side teaching loop makes iOS a pedagogically
        different product from web and Android. Removing the workaround means
        the weakness underneath it has to be fixed where every client
        benefits: here.

        THE RULE

        Never leave the learner with nothing, and never invent teaching
        material to avoid that. Those pull in opposite directions only if you
        assume the fallback has to produce new content. It does not — the
        lesson the learner is already in is sitting in session context. So:

        * If we still hold the lesson, re-teach from it and offer a concrete
          next move. The learner keeps learning; they never see the failure.
        * If we hold only a title or objective, name what they are working on
          and offer to show a worked example, which is a real request the
          engine can serve on the next turn.
        * If we hold nothing at all, ask what they want to work on. That is a
          genuine move that leads somewhere, unlike Continue with nothing
          behind it.

        Every branch is built from values already in context, so nothing here
        can raise on a missing field. That matters: this is the error path,
        and a fallback that throws leaves the learner with the dead screen
        this exists to prevent.
        """
        key = session_progress_key(trigger.user_id, trigger.session_id)
        context = self.session_contexts.get(key)
        language_code = str(
            _SESSION_PROGRESS.get(key, {}).get(
                "language_code",
                getattr(context, "language_code", None) or "en-US",
            )
        )
        is_spanish = language_code.lower().startswith("es")

        lesson_title = (getattr(context, "lesson_title", None) or "").strip()
        objective = (getattr(context, "learning_objective", None) or "").strip()
        # Course-provided provenance only. The compiler carries these through
        # on normal scenes and the fallback must not drop them just because
        # generation failed.
        attributions = list(getattr(context, "source_attributions", None) or [])[:5]

        excerpt = self._excerpt_for_reteaching(
            getattr(context, "lesson_content", None), self._FALLBACK_TEACHING_CHARS
        )

        components: List[Component] = []

        if excerpt:
            subject = lesson_title or objective
            lead = (
                (f"Retomemos {subject}." if subject else "Retomemos la idea principal.")
                if is_spanish
                else (
                    f"Let's pick {subject} back up."
                    if subject
                    else "Let's pick the main idea back up."
                )
            )
            components.append(
                TeacherMessage(
                    text=f"{lead}\n\n{excerpt}",
                    emotion="encouraging",
                    audio_mood=AudioMood.CALM,
                    language_code=language_code,
                    source_attributions=attributions,
                )
            )
            components.append(
                CTAButton(
                    label="Muéstrame un ejemplo" if is_spanish else "Show me an example",
                    action_intent=ActionIntent.REQUEST_EXAMPLE,
                    button_style="secondary",
                    language_code=language_code,
                )
            )
            components.append(
                CTAButton(
                    label="Continuar" if is_spanish else "Continue",
                    action_intent=ActionIntent.CONTINUE,
                    language_code=language_code,
                )
            )

        elif lesson_title or objective:
            subject = lesson_title or objective
            components.append(
                TeacherMessage(
                    text=(
                        f"Seguimos con {subject}. ¿Quieres ver un ejemplo trabajado "
                        "o continuar?"
                        if is_spanish
                        else f"We're still on {subject}. Want a worked example, "
                        "or shall we carry on?"
                    ),
                    emotion="encouraging",
                    audio_mood=AudioMood.CALM,
                    language_code=language_code,
                    source_attributions=attributions,
                )
            )
            components.append(
                CTAButton(
                    label="Muéstrame un ejemplo" if is_spanish else "Show me an example",
                    action_intent=ActionIntent.REQUEST_EXAMPLE,
                    button_style="secondary",
                    language_code=language_code,
                )
            )
            components.append(
                CTAButton(
                    label="Continuar" if is_spanish else "Continue",
                    action_intent=ActionIntent.CONTINUE,
                    language_code=language_code,
                )
            )

        else:
            # Nothing to re-teach from. Asking is a real move; Continue with
            # nothing behind it is not.
            components.append(
                TeacherMessage(
                    text=(
                        "¿Qué te gustaría trabajar ahora?"
                        if is_spanish
                        else "What would you like to work on?"
                    ),
                    emotion="encouraging",
                    audio_mood=AudioMood.CALM,
                    language_code=language_code,
                )
            )
            components.append(
                InputField(
                    placeholder=(
                        "Escribe un tema" if is_spanish else "Type a topic"
                    ),
                    question=(
                        "Dime qué quieres aprender y empezamos por ahí."
                        if is_spanish
                        else "Tell me what you want to learn and we'll start there."
                    ),
                    action_intent=ActionIntent.ASK_QUESTION,
                    language_code=language_code,
                )
            )

        return Scene(
            scene_type=SceneType.INSTRUCTION,
            components=components,
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    # 🎮 PUBLIC API METHODS
    # ═══════════════════════════════════════════════════════════════════════════════

    async def handle_user_action(
        self,
        user_id: str,
        session_id: str,
        action_intent: ActionIntent,
        action_data: Optional[Dict[str, Any]] = None,
        component_id: Optional[str] = None
    ) -> Scene:
        """Public API: Handle user action (tap, submit, etc.)"""
        trigger = Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id=user_id,
            session_id=session_id,
            action_data={
                **(action_data or {}),
                "action_intent": action_intent,
            },
            component_id=component_id,
            urgency=5  # User actions are medium priority
        )

        return await self.process_trigger(trigger)

    @staticmethod
    def _canonical_concept_id(concept_id: Optional[str]) -> Optional[str]:
        """Keep historical string keys readable alongside new Concept IDs.

        New guided plans resolve their skill IDs against the database before
        presenting a question. Saved older sessions and compatibility scene
        handlers can still carry plain text; those retain their historical
        slug key without being guessed into another scoped skill's credit.

        UUIDs are left alone: those identify a row in `concepts`, and the
        projection routes them to the foreign-keyed column.

        The placeholder `current_concept` is not a concept. It is what the
        callers fall back to when they could not determine one, and recording
        evidence against it would pool unrelated work into a single fake row.
        """
        from lyo_app.ai.lesson_composer import slugify_skill
        from lyo_app.events.mastery_projection import is_concept_graph_id

        if not concept_id:
            return None
        if is_concept_graph_id(concept_id):
            return concept_id
        slug = slugify_skill(concept_id)
        # `slugify_skill` returns "general" for input with nothing to slugify,
        # which is no more a concept than the placeholder is.
        if slug in ("current_concept", "general"):
            return None
        return slug

    async def _log_classroom_evidence(
        self,
        *,
        user_id: str,
        concept_id: Optional[str],
        correct: bool,
        hints_used: int,
        hint_level: Optional[str] = None,
        evidence_type: Optional[str] = None,
        misconception: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> bool:
        """Record what the learner just demonstrated on the shared event stream.

        The event processor projects this evidence into MasteryState. New
        guided questions name a persisted Concept ID. Older chat checks name
        legacy slugs; they stay separate until a verified identity mapping is
        available, rather than crediting an unrelated skill by title alone.

        Three things this deliberately does not do:

        * It does not pass `skill_ids_json`. That field is what asks the
          processor to run a DKT update, and both callers have already run one
          directly for this same answer. Passing it would count a single
          answer against the learner's mastery twice.
        * It does not decide correctness. `correct` is the server's verdict,
          reached from the authored scene, and is only read here.
        * It never raises. The learner's verdict and next scene are already
          decided; evidence logging is what makes the *next* lesson better,
          not what makes this answer right.

        Asking for help never demotes the rung the learner reached — a
        transfer done with a nudge is still a transfer. It lowers the
        confidence attached to it, because the demonstration proves less about
        what they can do unaided.

        Guests have no learner record to write to, so their evidence is
        dropped rather than faked.
        """
        concept_id = self._canonical_concept_id(concept_id)
        if not concept_id:
            return True

        try:
            learner_id = int(user_id)
        except (TypeError, ValueError):
            logger.debug("Guest classroom evidence is not persisted")
            return True

        try:
            from lyo_app.events.evidence import evidence_from_graded_answer
            from lyo_app.events.models import EventType
            from lyo_app.events.processor import log_learning_event
            from lyo_app.events.schemas import LearningEventCreate

            evidence = evidence_from_graded_answer(
                correct=correct,
                misconception=misconception,
                hints_used=hints_used,
                hint_level=hint_level,
                evidence_type=evidence_type,
            )
            if evidence is None:
                return True

            await log_learning_event(
                self.db,
                LearningEventCreate(
                    user_id=learner_id,
                    event_type=EventType.CLASSROOM_DEMONSTRATION,
                    measurable_outcome=1.0 if correct else 0.0,
                    concept_id=concept_id,
                    evidence_type=evidence["kind"],
                    evidence_confidence=evidence["confidence"],
                    hints_used=hints_used,
                    misconception=misconception,
                    source_surface="classroom",
                    metadata_json={"classroom_checkpoint_id": event_id} if event_id else None,
                ),
            )
            return True
        except Exception as exc:
            logger.warning(
                "Could not log classroom evidence for %s: %s", concept_id, exc
            )
            try:
                await self.db.rollback()
            except Exception:
                pass
            return False

    async def handle_quiz_submission(
        self, user_id: str, session_id: str, quiz_component_id: str,
        selected_option_id: str, response_time_ms: int = 0,
    ) -> Scene:
        # Correctness is resolved against the persisted active task, not a
        # client flag or an unowned scene found in a global component search.
        return await self.process_trigger(Trigger(
            trigger_type=TriggerType.USER_ACTION, user_id=user_id,
            session_id=session_id, component_id=quiz_component_id,
            action_data={"action_intent": ActionIntent.SUBMIT_ANSWER,
                         "answer_data": {"selected_option_id": selected_option_id},
                         "response_time_ms": response_time_ms},
        ))

    async def handle_transfer_submission(
        self, user_id: str, session_id: str, input_component_id: str,
        response: str, response_time_ms: int = 0,
    ) -> Scene:
        # Semantic, question-specific evaluation lives in AdaptiveTeacher.
        # Keyword scoring remains a legacy helper only, never the live grader.
        return await self.process_trigger(Trigger(
            trigger_type=TriggerType.USER_ACTION, user_id=user_id,
            session_id=session_id, component_id=input_component_id,
            action_data={"action_intent": ActionIntent.SUBMIT_TRANSFER,
                         "answer_data": {"response": response[:2000]},
                         "response_time_ms": response_time_ms},
        ))

    async def trigger_celebration(
        self,
        user_id: str,
        session_id: str,
        achievement_type: str,
        points_earned: int = 0
    ) -> Scene:
        """Public API: Trigger celebration scene"""
        trigger = Trigger(
            trigger_type=TriggerType.ACHIEVEMENT_UNLOCK,
            user_id=user_id,
            session_id=session_id,
            action_data={
                "achievement_type": achievement_type,
                "points_earned": points_earned
            },
            urgency=8  # Celebrations are high priority for motivation
        )

        return await self.process_trigger(trigger)

    def get_session_context(self, session_id: str, user_id: str) -> Optional[ContextSnapshot]:
        """Get current context for a session"""
        return self.session_contexts.get(session_progress_key(user_id, session_id))

    def get_active_scene(self, scene_id: str) -> Optional[Scene]:
        """Get currently active scene"""
        return self.active_scenes.get(scene_id)


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════════

__all__ = [
    "SceneLifecycleEngine",
    "TriggerType", "Trigger", "TriggerListener",
    "ContextSnapshot", "ContextAssembler",
    "DirectorDecision", "session_concept",
]
