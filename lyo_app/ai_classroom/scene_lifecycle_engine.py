"""
Lyo AI Classroom - Scene Lifecycle Engine
========================================

The brain of the "Living Classroom" that controls turn-based micro-scenes.
Implements the four-phase closed-loop interaction model:

1. TRIGGER (Listen) - Event-driven activation from user or system
2. CONTEXT (Think) - Assemble user state snapshot
3. DIRECTOR (Decide) - Central agent selects optimal scene type
4. COMPILATION (Act) - Map to SDUI components and stream to client

Architecture: Event → Context → Decision → Scene → WebSocket Stream → iOS Renderer
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from uuid import uuid4

from lyo_app.ai_agents.multi_agent_v2.agents.tutor_agent import get_tutor_agent, UserContext as AgentUserContext

from pydantic import BaseModel, Field
from sqlalchemy import select, func as sa_func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.ai_classroom.sdui_models import (
    Scene, SceneType, Component, ComponentType,
    TeacherMessage, StudentPrompt, QuizCard, CTAButton, Celebration, ProgressBar,
    InputField, LessonBlock, ExampleBlock,
    AudioMood, ActionIntent, ClassroomMode, HintLevel, WebSocketPayload, SceneStreamPayload,
    UserActionPayload, SystemStatePayload, SceneMetadata
)

logger = logging.getLogger(__name__)

# Per-session teaching progression: scene counter + rolling summaries of what
# was already taught, so the director never replays the opening scene.
_SESSION_PROGRESS: Dict[str, Dict[str, Any]] = {}

_TRANSFER_STOPWORDS = {
    "about", "after", "again", "apply", "because", "before", "being", "compare",
    "course", "demonstrate", "explain", "from", "have", "into", "lesson", "that",
    "their", "there", "these", "this", "through", "understand", "using", "what",
    "when", "where", "which", "with", "would", "your",
}


def expected_transfer_keywords(objective: str, lesson_content: str = "") -> List[str]:
    """Build a small transparent rubric from authored course language."""
    source = f"{objective} {lesson_content[:400]}"
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", source.lower())
    keywords: List[str] = []
    for token in tokens:
        if token in _TRANSFER_STOPWORDS or token in keywords:
            continue
        keywords.append(token)
        if len(keywords) == 8:
            break
    return keywords


def score_transfer_response(
    response: str,
    expected_keywords: List[str],
    min_words: int = 6,
    min_score: float = 0.25,
) -> tuple[bool, float, List[str]]:
    """Score open evidence deterministically; return correctness, coverage, gaps."""
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{1,}", (response or "").lower())
    token_set = set(tokens)
    rubric = [k.lower().strip() for k in expected_keywords if k and k.strip()]
    hits = [k for k in rubric if k in token_set or k in (response or "").lower()]
    coverage = len(hits) / max(len(rubric), 1)
    substantive = len(tokens) >= min_words
    correct = substantive and (not rubric or coverage >= min_score)
    missing = [k for k in rubric if k not in hits]
    return correct, round(coverage, 3), missing[:4]


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
            trigger.session_id, {"scene": 0, "covered": [], "mastered_lessons": []}
        )
        if not progress.get("_hydrated"):
            persisted = await self._load_persisted_session_progress(trigger)
            if persisted:
                progress.update(persisted)
            progress["_hydrated"] = True
        if "current_lesson_index" in progress:
            context.lesson_index = int(progress["current_lesson_index"] or 0)
        context.course_complete = bool(progress.get("course_complete", False))

        # Resolve current lesson content from the DB
        context.lesson_title, context.lesson_content, context.total_lessons = \
            await self._resolve_current_lesson(context.course_id, context.lesson_index)
        # If lesson gave us a more specific topic, use it
        if context.lesson_title and not context.topic:
            context.topic = context.lesson_title
        if context.course_title or context.lesson_title:
            context.source_attributions = [
                "Course material"
                + (f": {context.course_title}" if context.course_title else "")
                + (f" — {context.lesson_title}" if context.lesson_title else "")
            ]

        # Preserve the instructional goal and learner-selected pace for the
        # entire classroom session. These values arrive on the welcome trigger
        # and must remain available on later WebSocket actions.
        action_data = trigger.action_data or {}
        explicit_objective = action_data.get("objective")
        if explicit_objective:
            progress["learning_objective"] = str(explicit_objective)
        context.learning_objective = (
            progress.get("learning_objective")
            or context.lesson_title
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
        if context.classroom_mode == ClassroomMode.REVIEW:
            context.review_due_items = await self._get_due_review_items(trigger.user_id)

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
            logger.debug(f"ℹ️ Could not hydrate classroom progress: {e}")
            return {}

    async def _resolve_topic(
        self, trigger: Trigger
    ) -> tuple:
        """Resolve topic, course_id, course_title and lesson_index from the session."""
        topic = None
        course_id = trigger.course_id
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
                if conv_session:
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
        self, course_id: Optional[str], lesson_index: int
    ) -> tuple:
        """Fetch the current lesson title, content, and total lessons for the course."""
        lesson_title = None
        lesson_content = None
        total_lessons = 0

        if not course_id:
            return lesson_title, lesson_content, total_lessons

        try:
            course_id_int = int(course_id)
            from lyo_app.learning.models import Lesson

            # Get the current lesson by order_index
            result = await self.db.execute(
                select(Lesson.title, Lesson.content, Lesson.description, Lesson.topic)
                .where(
                    and_(
                        Lesson.course_id == course_id_int,
                        Lesson.order_index == lesson_index
                    )
                )
                .limit(1)
            )
            row = result.first()
            if row:
                lesson_title = row.title
                lesson_content = row.content or row.description or ""
                logger.info(f"📖 Resolved lesson {lesson_index}: {lesson_title}")

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
                from sqlalchemy import select, or_
                
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
                        if 0 <= lesson_index < total_lessons:
                            target_node = narrative_nodes[lesson_index]
                            keywords = target_node.content.get("keywords") or ["Overview"]
                            keyword = keywords[0] if keywords else "Overview"
                            lesson_title = target_node.content.get("title") or f"Lesson {lesson_index + 1}: {keyword.title()}"
                            lesson_content = target_node.content.get("narration", "")
                            if target_node.content.get("code"):
                                lang = target_node.content.get("language") or ""
                                code_str = target_node.content.get("code")
                                lesson_content += f"\n\nCode Example:\n```{lang}\n{code_str}\n```"
                            logger.info(f"📖 Resolved GraphCourse lesson {lesson_index}: {lesson_title}")
                    return lesson_title, lesson_content, total_lessons
            except Exception as e:
                logger.warning(f"⚠️ Could not query GraphCourse for lessons: {e}")

            # Fallback to other UUID models (ChatCourse or GeneratedCourseModel)
            try:
                from lyo_app.chat.models import ChatCourse
                from sqlalchemy import select
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
                    if 0 <= lesson_index < total_lessons:
                        lesson = all_lessons[lesson_index]
                        lesson_title = lesson.get("title")
                        lesson_content = lesson.get("content") or lesson.get("description") or lesson.get("summary") or ""
                        logger.info(f"📖 Resolved chat/gen lesson {lesson_index}: {lesson_title}")
                    
            except Exception as e:
                logger.warning(f"⚠️ Could not query UUID course models for lesson: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Could not query Lesson: {e}")

        return lesson_title, lesson_content, total_lessons

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
        try:
            user_id_int = int(user_id)
            from lyo_app.personalization.models import LearnerMastery
            result = await self.db.execute(
                select(LearnerMastery).where(LearnerMastery.user_id == user_id_int)
            )
            rows = result.scalars().all()
            if rows:
                return [
                    KnowledgeState(
                        concept_id=r.skill_id,
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
            return [
                KnowledgeState(
                    concept_id=r.concept_id or r.objective_id or "unknown",
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
# 🎯 PHASE 3: CLASSROOM DIRECTOR (Decide)
# ═══════════════════════════════════════════════════════════════════════════════════

class DirectorDecision(BaseModel):
    """Decision made by the Classroom Director"""

    selected_scene_type: SceneType
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)

    # Scene parameters
    estimated_duration_seconds: int = Field(default=30, ge=5, le=600)
    difficulty_adjustment: float = Field(default=0.0, ge=-0.5, le=0.5)

    # Component hints for compiler
    suggested_components: List[ComponentType] = Field(default_factory=list)
    require_audio: bool = False
    require_interaction: bool = False

    # Timing
    decision_time_ms: float = 0.0


class ClassroomDirector:
    """Central authority that selects optimal scene types"""

    def __init__(self):
        self.decision_history: List[DirectorDecision] = []
        self.scene_patterns = self._init_scene_patterns()

    async def decide_scene(self, trigger: Trigger, context: ContextSnapshot) -> DirectorDecision:
        """Central decision making - THE CORE OF THE CLASSROOM"""
        start_time = time.time()

        logger.info(f"🎯 Director analyzing: {trigger.trigger_type} for user {trigger.user_id}")

        # Rule-based decision tree with educational AI logic
        decision = await self._evaluate_scene_need(trigger, context)
        decision.decision_time_ms = (time.time() - start_time) * 1000

        # Record decision for learning
        self.decision_history.append(decision)

        logger.info(f"✅ Director decided: {decision.selected_scene_type} "
                   f"(confidence={decision.confidence:.2f}) in {decision.decision_time_ms:.0f}ms")

        return decision

    async def _evaluate_scene_need(self, trigger: Trigger, context: ContextSnapshot) -> DirectorDecision:
        """Choose the next pedagogical move in the evidence-based mastery loop."""
        action_data = trigger.action_data or {}
        action_intent = action_data.get("action_intent")
        answer_data = action_data.get("answer_data", {})
        quiz_correct = (
            action_intent == ActionIntent.SUBMIT_ANSWER
            and answer_data.get("is_correct") is True
        )
        transfer_correct = (
            action_intent == ActionIntent.SUBMIT_TRANSFER
            and answer_data.get("is_correct") is True
        )
        newly_correct = quiz_correct or transfer_correct

        if (
            context.frustration.frustration_score > 0.6
            and context.frustration.consecutive_failures >= 3
            and not newly_correct
        ):
            return DirectorDecision(
                selected_scene_type=SceneType.CORRECTION,
                reasoning="Repeated misses require a smaller step and explicit reteaching",
                confidence=0.9,
                suggested_components=[ComponentType.TEACHER_MESSAGE],
                require_audio=True,
            )

        if trigger.trigger_type == TriggerType.ACHIEVEMENT_UNLOCK:
            return DirectorDecision(
                selected_scene_type=SceneType.CELEBRATION,
                reasoning="Achievement unlocked - reinforce success",
                confidence=0.95,
                suggested_components=[ComponentType.CELEBRATION, ComponentType.CTA_BUTTON],
                estimated_duration_seconds=10,
            )

        if trigger.trigger_type == TriggerType.USER_ACTION:
            if action_intent == ActionIntent.CONTINUE:
                if context.course_complete:
                    return DirectorDecision(
                        selected_scene_type=SceneType.CELEBRATION,
                        reasoning="All lesson checkpoints have recognition and transfer evidence",
                        confidence=0.95,
                        suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.LESSON_BLOCK],
                        estimated_duration_seconds=15,
                    )
                if action_data.get("advanced_after_mastery"):
                    return DirectorDecision(
                        selected_scene_type=SceneType.INSTRUCTION,
                        reasoning=f"Begin the next sequenced lesson: {context.lesson_title or context.topic}",
                        confidence=0.9,
                        suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                    )
                return DirectorDecision(
                    selected_scene_type=SceneType.CHALLENGE,
                    reasoning="Collect recognition evidence before transfer",
                    confidence=0.9,
                    suggested_components=[ComponentType.QUIZ_CARD],
                    require_interaction=True,
                    estimated_duration_seconds=45,
                )

            if action_intent == ActionIntent.REQUEST_HINT:
                hint = context.hint_level.value if context.hint_level else HintLevel.NUDGE.value
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning=f"Provide graduated help at the {hint} level",
                    confidence=0.92,
                    difficulty_adjustment=-0.1 if hint == HintLevel.NUDGE.value else -0.25,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.EXAMPLE_BLOCK],
                    require_audio=True,
                )

            if action_intent == ActionIntent.ASK_QUESTION:
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning="Answer the learner's question directly, then reconnect it to the objective",
                    confidence=0.95,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                    require_audio=True,
                )

            if action_intent == ActionIntent.USER_MESSAGE:
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning="Use the learner's response as evidence and continue the explanation",
                    confidence=0.85,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                )

            if action_intent == ActionIntent.REQUEST_EXAMPLE:
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning="Provide a concrete worked example",
                    confidence=0.9,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.EXAMPLE_BLOCK],
                )

            if action_intent == ActionIntent.SKIP_AHEAD:
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning="Increase depth and transfer without skipping the objective",
                    confidence=0.85,
                    difficulty_adjustment=0.25,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                )

            if action_intent in (ActionIntent.REQUEST_REVIEW, ActionIntent.SET_MODE):
                if context.classroom_mode == ClassroomMode.REVIEW:
                    return DirectorDecision(
                        selected_scene_type=SceneType.CHALLENGE,
                        reasoning="Run retrieval practice from the learner's due-review queue",
                        confidence=0.9,
                        suggested_components=[ComponentType.QUIZ_CARD],
                        require_interaction=True,
                    )
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning=f"Adopt the learner-selected {context.classroom_mode.value} format",
                    confidence=0.9,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                )

            if action_intent == ActionIntent.RETRY:
                return DirectorDecision(
                    selected_scene_type=SceneType.CHALLENGE,
                    reasoning="Retry the recognition checkpoint after targeted correction",
                    confidence=0.9,
                    suggested_components=[ComponentType.QUIZ_CARD],
                    require_interaction=True,
                )

            if action_intent == ActionIntent.SUBMIT_ANSWER:
                if quiz_correct:
                    return DirectorDecision(
                        selected_scene_type=SceneType.REFLECTION,
                        reasoning="Recognition passed; require explanation or application before mastery",
                        confidence=0.97,
                        suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.INPUT_FIELD],
                        require_interaction=True,
                        estimated_duration_seconds=60,
                    )
                return DirectorDecision(
                    selected_scene_type=SceneType.CORRECTION,
                    reasoning="Use the chosen distractor's misconception and remediation metadata",
                    confidence=0.95,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                    require_audio=True,
                )

            if action_intent == ActionIntent.SUBMIT_TRANSFER:
                if transfer_correct:
                    return DirectorDecision(
                        selected_scene_type=SceneType.CELEBRATION,
                        reasoning="Recognition plus transfer evidence demonstrates lesson mastery",
                        confidence=0.98,
                        suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CELEBRATION, ComponentType.CTA_BUTTON],
                        estimated_duration_seconds=12,
                    )
                return DirectorDecision(
                    selected_scene_type=SceneType.CORRECTION,
                    reasoning="Transfer response needs one precise revision before mastery",
                    confidence=0.96,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.INPUT_FIELD],
                    require_interaction=True,
                    require_audio=True,
                )

        if context.course_complete:
            return DirectorDecision(
                selected_scene_type=SceneType.CELEBRATION,
                reasoning="Persisted session shows every lesson has multiple forms of evidence",
                confidence=0.95,
                suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.LESSON_BLOCK],
                estimated_duration_seconds=15,
            )

        if trigger.trigger_type == TriggerType.SYSTEM_TIMEOUT:
            if context.classroom_mode == ClassroomMode.REVIEW and context.review_due_items:
                return DirectorDecision(
                    selected_scene_type=SceneType.CHALLENGE,
                    reasoning="Open with a due spaced-retrieval item",
                    confidence=0.9,
                    suggested_components=[ComponentType.QUIZ_CARD],
                    require_interaction=True,
                )
            return DirectorDecision(
                selected_scene_type=SceneType.INSTRUCTION,
                reasoning="Open or re-engage with explicit teaching",
                confidence=0.8,
                suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                require_audio=True,
            )

        return DirectorDecision(
            selected_scene_type=SceneType.INSTRUCTION,
            reasoning="Default guided instruction",
            confidence=0.6,
            suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
        )

    def _should_add_challenge(self, context: ContextSnapshot) -> bool:
        """Determine if user is ready for a challenge"""
        # Check recent mastery levels and engagement
        avg_mastery = sum(k.mastery_level for k in context.knowledge_states) / max(len(context.knowledge_states), 1)
        return avg_mastery > 0.7 and context.engagement_level > 0.6

    def _init_scene_patterns(self) -> Dict[str, Any]:
        """Initialize scene pattern templates"""
        return {
            "instruction_flow": ["instruction", "challenge", "instruction"],
            "correction_flow": ["correction", "instruction", "challenge"],
            "celebration_timing": {"min_gap_seconds": 30, "max_per_session": 3}
        }


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎨 PHASE 4: SDUI COMPILER (Act)
# ═══════════════════════════════════════════════════════════════════════════════════

class SceneCompiler:
    """Compiles Director decisions into concrete SDUI scenes"""

    def __init__(self, ai_service: Optional[Any] = None):
        self.ai_service = ai_service  # For dynamic content generation
        self.template_cache: Dict[str, Any] = {}

    async def compile_scene(
        self,
        decision: DirectorDecision,
        context: ContextSnapshot,
        trigger: Trigger
    ) -> Scene:
        """Compile Director decision into a complete Scene with Components"""

        logger.info(f"🎨 Compiling scene: {decision.selected_scene_type}")

        # Build scene metadata
        metadata = SceneMetadata(
            difficulty_level="beginner",  # Could be derived from context
            estimated_duration_seconds=decision.estimated_duration_seconds,
            user_mastery_context={k.concept_id: k.mastery_level for k in context.knowledge_states},
            frustration_level=context.frustration.frustration_score,
            scene_source="ai_generated"
        )

        # Generate components based on scene type
        components = await self._generate_components(decision, context, trigger)

        scene = Scene(
            scene_type=decision.selected_scene_type,
            components=components,
            metadata=metadata,
            trigger_conditions={"trigger_id": trigger.trigger_id}
        )

        logger.info(f"✅ Scene compiled: {len(components)} components, "
                   f"estimated {decision.estimated_duration_seconds}s duration")

        return scene

    async def _generate_components(
        self,
        decision: DirectorDecision,
        context: ContextSnapshot,
        trigger: Trigger
    ) -> List[Component]:
        """Generate appropriate components for the scene type"""

        components = []

        if decision.selected_scene_type == SceneType.INSTRUCTION:
            components.extend(await self._create_instruction_components(context))

        elif decision.selected_scene_type == SceneType.REFLECTION:
            components.extend(self._create_transfer_components(context))

        elif decision.selected_scene_type == SceneType.CHALLENGE:
            components.extend(await self._create_challenge_components(context))

        elif decision.selected_scene_type == SceneType.CORRECTION:
            components.extend(await self._create_correction_components(context, trigger))

        elif decision.selected_scene_type == SceneType.CELEBRATION:
            components.extend(await self._create_celebration_components(context))

        # Make advancement visible. A checkpoint counts only after the server
        # has validated it and placed it in mastered_lessons.
        progress = _SESSION_PROGRESS.get(context.session_id, {})
        total = max(context.total_lessons, 1)
        mastered_count = min(
            total,
            len(set(progress.get("mastered_lessons", []))),
        )
        if context.course_complete:
            mastered_count = total
        components.insert(0, ProgressBar(
            current=mastered_count,
            total=total,
            show_percentage=True,
            show_fraction=True,
            label="Lesson mastery",
            color_scheme="purple",
            priority=0,
        ))

        return components

    async def _create_instruction_components(self, context: ContextSnapshot) -> List[Component]:
        """Create one short teaching beat, then yield control to the learner."""
        if context.hint_level:
            return self._create_hint_components(context)

        if self.ai_service:
            beat = await self._generate_instruction_content(context)
        else:
            beat = self._local_teaching_beat(context)

        return [
            TeacherMessage(
                text=beat.speech,
                emotion="encouraging",
                audio_mood=AudioMood.CALM,
                concept_tags=[context.learning_objective or context.topic or "current_topic"],
                source_attributions=context.source_attributions,
                language_code=context.language_code,
                priority=0,
                delay_ms=0,
            ),
            ExampleBlock(
                title=beat.board_title,
                content=beat.board_content,
                example_type=beat.example_type
                if beat.example_type in {"code", "visual", "analogy", "real_world"}
                else "real_world",
                language_code=context.language_code,
                priority=1,
                delay_ms=0,
            ),
            CTAButton(
                label=self._localized_copy(
                    context.language_code,
                    english="Check understanding",
                    spanish="Comprobar comprensión",
                ),
                action_intent=ActionIntent.CONTINUE,
                button_style="primary",
                language_code=context.language_code,
                priority=2,
                delay_ms=0,
            ),
        ]

    def _create_hint_components(self, context: ContextSnapshot) -> List[Component]:
        """Return the requested rung of the hint ladder without hiding the level."""
        level = context.hint_level or HintLevel.NUDGE
        objective = context.learning_objective or context.lesson_title or context.topic or "this idea"
        remediation = context.remediation_hint or ""
        if context.language_code.lower().startswith("es"):
            guidance = {
                HintLevel.NUDGE: f"Una pista: identifica la regla que conecta la pregunta con {objective}.",
                HintLevel.PRINCIPLE: f"Principio: expresa la idea que gobierna {objective} antes de elegir o calcular.",
                HintLevel.WORKED_STEP: f"Primer paso: identifica la información conocida y conéctala con {objective}.",
                HintLevel.FULL_EXAMPLE: f"Ejemplo resuelto: elige un caso sencillo, aplica {objective} paso a paso y comprueba el resultado.",
                HintLevel.PREREQUISITE: f"Base necesaria: define los términos clave de {objective} y reconstruye su relación.",
            }[level]
        else:
            guidance = {
                HintLevel.NUDGE: f"Small nudge: identify the one rule that connects the question to {objective}.",
                HintLevel.PRINCIPLE: f"Principle: state the governing idea behind {objective} before calculating or choosing.",
                HintLevel.WORKED_STEP: f"First step: name the known information, then connect it to {objective}.",
                HintLevel.FULL_EXAMPLE: f"Worked example: choose a simple case, apply {objective} one step at a time, and check the result.",
                HintLevel.PREREQUISITE: f"Prerequisite review: define the key terms inside {objective}, then rebuild the relationship between them.",
            }[level]
        if remediation:
            guidance = (
                f"{guidance} Enfócate especialmente en: {remediation}"
                if context.language_code.lower().startswith("es")
                else f"{guidance} Focus especially on: {remediation}"
            )
        components: List[Component] = [
            TeacherMessage(
                text=guidance,
                emotion="thinking",
                audio_mood=AudioMood.GENTLE,
                concept_tags=[objective],
                source_attributions=context.source_attributions,
                language_code=context.language_code,
                priority=0,
            )
        ]
        if level in (HintLevel.WORKED_STEP, HintLevel.FULL_EXAMPLE, HintLevel.PREREQUISITE):
            spanish_titles = {
                HintLevel.WORKED_STEP: "Empieza aquí",
                HintLevel.FULL_EXAMPLE: "Ejemplo resuelto",
                HintLevel.PREREQUISITE: "Repaso de fundamentos",
            }
            english_titles = {
                HintLevel.WORKED_STEP: "Start here",
                HintLevel.FULL_EXAMPLE: "Worked example",
                HintLevel.PREREQUISITE: "Foundation refresher",
            }
            components.append(ExampleBlock(
                title=(
                    spanish_titles[level]
                    if context.language_code.lower().startswith("es")
                    else english_titles[level]
                ),
                content=context.lesson_content[:1200] if context.lesson_content else guidance,
                example_type="real_world",
                interactive=level == HintLevel.FULL_EXAMPLE,
                language_code=context.language_code,
                priority=1,
            ))
        components.append(CTAButton(
            label=self._localized_copy(
                context.language_code,
                english="Try the checkpoint",
                spanish="Intentar la comprobación",
            ),
            action_intent=ActionIntent.CONTINUE,
            button_style="primary",
            language_code=context.language_code,
            priority=100,
        ))
        return components

    def _create_transfer_components(self, context: ContextSnapshot) -> List[Component]:
        """Ask for explanation/application evidence after recognition succeeds."""
        objective = context.learning_objective or context.lesson_title or context.topic or "the lesson idea"
        keywords = expected_transfer_keywords(objective, context.lesson_content or "")
        is_spanish = context.language_code.lower().startswith("es")
        if is_spanish and context.classroom_mode == ClassroomMode.CHALLENGE:
            question = (
                f"Aplica {objective} a un caso nuevo o límite. Explica tu razonamiento "
                "y menciona una condición en la que la idea no se aplicaría."
            )
        elif is_spanish and context.classroom_mode == ClassroomMode.REVIEW:
            question = f"Sin mirar atrás, explica {objective} y da un ejemplo concreto."
        elif is_spanish:
            question = (
                f"Con tus propias palabras, aplica {objective} a un ejemplo o situación nueva. "
                "Explica por qué funciona tu ejemplo."
            )
        elif context.classroom_mode == ClassroomMode.CHALLENGE:
            question = (
                f"Apply {objective} to a new or boundary case. Explain your reasoning "
                "and name one condition where the idea would not apply."
            )
        elif context.classroom_mode == ClassroomMode.REVIEW:
            question = f"Without looking back, explain {objective} and give one concrete example."
        else:
            question = (
                f"In your own words, apply {objective} to a new example or situation. "
                "Explain why your example works."
            )
        return [
            TeacherMessage(
                text=(
                    "La elección muestra reconocimiento. Una aplicación breve mostrará que puedes usar la idea."
                    if is_spanish
                    else "The choice shows recognition. One short application will show that the idea is usable."
                ),
                emotion="thinking",
                audio_mood=AudioMood.CALM,
                concept_tags=[objective],
                source_attributions=context.source_attributions,
                language_code=context.language_code,
                priority=0,
            ),
            InputField(
                question=question,
                placeholder=(
                    "Explica y aplica la idea…"
                    if is_spanish
                    else "Explain and apply the idea…"
                ),
                action_intent=ActionIntent.SUBMIT_TRANSFER,
                concept_id=objective,
                evidence_type="retrieval" if context.classroom_mode == ClassroomMode.REVIEW else "transfer",
                expected_keywords=keywords,
                min_words=6,
                max_words=120,
                min_score=0.25,
                source_attributions=context.source_attributions,
                language_code=context.language_code,
                priority=1,
            ),
        ]

    async def _create_challenge_components(self, context: ContextSnapshot) -> List[Component]:
        """Create components for challenge/quiz scenes"""
        components = []

        # Quiz question
        quiz_question = await self._generate_quiz_question(context)
        components.append(quiz_question)

        return components

    async def _create_correction_components(self, context: ContextSnapshot, trigger: Trigger) -> List[Component]:
        """Create precise remediation from the submitted evidence."""
        components: List[Component] = []
        is_spanish = context.language_code.lower().startswith("es")

        if (
            context.classroom_mode == ClassroomMode.CLASSROOM
            and context.frustration.consecutive_failures >= 2
            and not context.peer_cooldown_active
        ):
            components.append(StudentPrompt(
                student_name="Sam",
                text=(
                    "Esa elección sigue un atajo común. Veamos exactamente dónde falla."
                    if is_spanish
                    else "That choice follows a common shortcut. Let's inspect exactly where it breaks."
                ),
                personality_trait="supportive",
                purpose="normalize_error",
                language_code=context.language_code,
                priority=0,
            ))

        focus = context.remediation_hint or context.misconception_tag
        feedback = context.answer_feedback
        if feedback or focus:
            correction_text = " ".join(
                part for part in [
                    feedback or (
                        "La respuesta está cerca, pero falta corregir un vínculo del razonamiento."
                        if is_spanish
                        else "The response is close, but one link in the reasoning needs revision."
                    ),
                    (
                        f"Enfócate en {focus}."
                        if is_spanish and focus
                        else f"Focus on {focus}." if focus else ""
                    ),
                ] if part
            )
        elif self.ai_service:
            correction_text = (
                await self._generate_instruction_content(context)
            ).speech
        else:
            correction_text = self._local_teaching_beat(context).speech

        components.append(TeacherMessage(
            text=correction_text,
            emotion="concerned",
            audio_mood=AudioMood.GENTLE,
            concept_tags=[context.learning_objective or context.topic or "current_topic"],
            source_attributions=context.source_attributions,
            language_code=context.language_code,
            priority=1,
        ))

        action_intent = (trigger.action_data or {}).get("action_intent")
        if action_intent == ActionIntent.SUBMIT_TRANSFER:
            transfer_input = self._create_transfer_components(context)[-1]
            objective = context.learning_objective or context.topic
            if is_spanish:
                transfer_input.question = (
                    f"Revisa tu aplicación de {objective or 'la idea'}. "
                    + (
                        f"Asegúrate de abordar {focus}."
                        if focus
                        else "Añade el vínculo que falta y explica por qué funciona el ejemplo."
                    )
                )
            else:
                transfer_input.question = (
                    f"Revise your application of {objective or 'the idea'}. "
                    + (
                        f"Make sure you address {focus}."
                        if focus
                        else "Add the missing reasoning link and explain why the example works."
                    )
                )
            transfer_input.priority = 2
            components.append(transfer_input)
        else:
            components.append(CTAButton(
                label="Reintentar comprobación" if is_spanish else "Retry checkpoint",
                action_intent=ActionIntent.RETRY,
                button_style="secondary",
                language_code=context.language_code,
                priority=2,
            ))

        return components

    async def _create_celebration_components(self, context: ContextSnapshot) -> List[Component]:
        """Close with evidence, a useful summary, and the next retrieval step."""
        progress = _SESSION_PROGRESS.get(context.session_id, {})
        covered = list(progress.get("covered", []))[-3:]
        objective = context.learning_objective or context.lesson_title or context.topic or "this idea"
        is_spanish = context.language_code.lower().startswith("es")
        components: List[Component] = []

        if context.course_complete:
            if is_spanish:
                message = (
                    f"Completaste {context.course_title or context.topic or 'este curso'}. "
                    "Cada lección ya tiene evidencia de reconocimiento y aplicación."
                )
                celebration_message = "Dominio del curso demostrado"
            else:
                message = (
                    f"You completed {context.course_title or context.topic or 'this course'}. "
                    "Each lesson now has both recognition and application evidence."
                )
                celebration_message = "Course mastery demonstrated"
        else:
            if is_spanish:
                message = (
                    f"Reconociste y aplicaste {objective}. "
                    "Eso demuestra más comprensión que una elección correcta por sí sola."
                )
                celebration_message = "Lección dominada"
            else:
                message = (
                    f"You recognized and applied {objective}. "
                    "That is stronger evidence than a correct choice alone."
                )
                celebration_message = "Lesson mastered"

        components.append(TeacherMessage(
            text=message,
            emotion="excited",
            audio_mood=AudioMood.ENCOURAGING,
            concept_tags=[objective],
            source_attributions=context.source_attributions,
            language_code=context.language_code,
            priority=0,
        ))

        summary_items = covered or [
            (
                f"Objetivo: {objective}"
                if is_spanish
                else f"Objective: {objective}"
            ),
            (
                "Evidencia: reconocimiento más explicación o aplicación"
                if is_spanish
                else "Evidence: recognition plus explanation/application"
            ),
            (
                "Siguiente paso: recuperar la idea de nuevo después de una pausa"
                if is_spanish
                else "Next: retrieve the idea again after spacing"
            ),
        ]
        components.append(LessonBlock(
            block_type="summary",
            block={
                "title": "Lo que ahora puedes hacer" if is_spanish else "What you can now do",
                "content": (
                    f"Usar {objective} sin depender de opciones de respuesta."
                    if is_spanish
                    else f"Use {objective} without relying on answer choices."
                ),
                "items": summary_items,
                "source_attributions": context.source_attributions,
                "retrieval_scheduled": True,
            },
            language_code=context.language_code,
            priority=1,
        ))
        components.append(Celebration(
            message=celebration_message,
            celebration_type="standard",
            particle_effect="confetti",
            language_code=context.language_code,
            achievement_type="mastery",
            points_earned=10,
            priority=2,
        ))

        if not context.course_complete:
            components.append(CTAButton(
                label="Next lesson",
                action_intent=ActionIntent.CONTINUE,
                button_style="primary",
                priority=3,
            ))

        return components

    async def _generate_teaching_beat(
        self, context: ContextSnapshot
    ) -> TeachingBeat:
        """Generate one 10-20 second explanation and one supporting board item."""
        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager

            topic = context.topic or "general learning"
            objective = context.learning_objective or context.lesson_title or topic
            avg_mastery = (
                sum(k.mastery_level for k in context.knowledge_states)
                / max(len(context.knowledge_states), 1)
            )
            user_level = (
                "advanced" if max(avg_mastery, context.preferred_difficulty) >= 0.75
                else "intermediate" if max(avg_mastery, context.preferred_difficulty) >= 0.5
                else "beginner"
            )
            progress = _SESSION_PROGRESS.setdefault(
                context.session_id,
                {"scene": 0, "covered": [], "mastered_lessons": []},
            )
            progress["scene"] = int(progress.get("scene", 0)) + 1
            covered = list(progress.get("covered", []))[-8:]

            prompt = f"""
Create exactly ONE learner-gated teaching beat.

Spoken language: {context.language_code}
Topic: {topic}
Lesson: {context.lesson_title or topic}
Learning objective: {objective}
Learner level: {user_level}
Classroom mode: {context.classroom_mode.value}
Beat number: {progress["scene"]}
Already covered: {json.dumps(covered, ensure_ascii=False)}
Learner question: {json.dumps(context.learner_message or "", ensure_ascii=False)}
Learner response: {json.dumps(context.learner_response or "", ensure_ascii=False)}
Learner signal: {json.dumps(context.learner_signal or "", ensure_ascii=False)}
Misconception: {json.dumps(context.misconception_tag or "", ensure_ascii=False)}
Remediation cue: {json.dumps(context.remediation_hint or "", ensure_ascii=False)}
Lesson material:
{(context.lesson_content or "")[:6000]}

Return ONLY one JSON object:
{{
  "speech": "28-55 natural spoken words in {context.language_code}, at most two sentences",
  "board_title": "short title in {context.language_code}",
  "board_content": "one concrete example, comparison, formula, or 2-4 concise bullets",
  "example_type": "real_world|analogy|visual|code"
}}

Rules:
- Teach one idea accurately; do not write a scene, dialogue, welcome, or cast.
- The Teacher is the only speaker. Never supply an AI student's answer.
- If a learner question exists, answer it directly.
- If the learner was confused or incorrect, explain the exact gap differently.
- Refer naturally to the board in the speech.
- Do not ask a question in the speech; the server presents the checkpoint next.
- Do not repeat anything in Already covered.
- Use only supplied course material and never invent a citation.
"""
            response = await ai_resilience_manager.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a rigorous, warm teacher. Produce one short "
                            "learner-gated teaching beat as valid JSON, with no "
                            "markdown or surrounding prose."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                provider_order=["gpt-4o-mini", "gemini-2.5-flash"],
                max_tokens=650,
                use_cache=False,
            )
            if response.get("is_fallback"):
                raise RuntimeError("AI service returned fallback content")

            raw = (response.get("content") or "").strip()
            first_brace = raw.find("{")
            last_brace = raw.rfind("}")
            if first_brace < 0 or last_brace <= first_brace:
                raise ValueError("Teaching beat did not contain a JSON object")
            data = json.loads(raw[first_brace:last_brace + 1])
            beat = self._normalize_teaching_beat(data)
            progress.setdefault("covered", []).append(beat.speech[:220])
            return beat
        except Exception as exc:
            logger.error("Teaching-beat generation failed: %s", type(exc).__name__)
            return self._local_teaching_beat(context)

    def _normalize_teaching_beat(self, data: Dict[str, Any]) -> TeachingBeat:
        speech = self._plain_text(str(data.get("speech") or ""))
        board_title = self._plain_text(str(data.get("board_title") or ""))
        board_content = str(data.get("board_content") or "").strip()
        if len(speech.split()) < 3 or not board_title or not board_content:
            raise ValueError("Teaching beat is missing required content")

        example_type = str(data.get("example_type") or "real_world")
        if example_type not in {"real_world", "analogy", "visual", "code"}:
            example_type = "real_world"
        return TeachingBeat(
            speech=self._clip_words(speech, 55),
            board_title=self._clip_words(board_title, 10),
            board_content=board_content[:1200],
            example_type=example_type,
        )

    def _local_teaching_beat(self, context: ContextSnapshot) -> TeachingBeat:
        """Keep teaching locally when model generation is unavailable."""
        topic = (
            context.lesson_title
            or context.topic
            or context.course_title
            or "this concept"
        )
        raw_content = (
            context.lesson_content
            or context.learning_objective
            or topic
        )
        plain_content = self._plain_text(raw_content)
        main_point = self._clip_words(plain_content or topic, 28)
        if context.language_code.lower().startswith("es"):
            speech = (
                f"Centremos la atención en una sola idea sobre {topic}: {main_point} "
                "Mira el ejemplo del tablero y observa cómo conecta la idea "
                "con un caso concreto."
            )
            title = "Idea central"
        else:
            speech = (
                f"Focus on one useful idea about {topic}: {main_point} "
                "Look at the board example and notice how it connects the idea "
                "to a concrete case."
            )
            title = "Core idea"
        return TeachingBeat(
            speech=self._clip_words(speech, 55),
            board_title=title,
            board_content=self._clip_words(plain_content or topic, 80),
            example_type="real_world",
        )

    @staticmethod
    def _plain_text(value: str) -> str:
        text = re.sub(r"```(?:[a-zA-Z0-9_+-]+)?", " ", value or "")
        text = text.replace("```", " ")
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"[*_`]+", "", text)
        return " ".join(text.split())

    @staticmethod
    def _clip_words(value: str, limit: int) -> str:
        clipped = " ".join(value.split()[:limit]).strip()
        if clipped and clipped[-1] not in ".!?":
            clipped += "."
        return clipped

    @staticmethod
    def _localized_copy(language_code: str, english: str, spanish: str) -> str:
        return spanish if language_code.lower().startswith("es") else english

    async def _generate_instruction_content(
        self, context: ContextSnapshot
    ) -> TeachingBeat:
        return await self._generate_teaching_beat(context)

    async def _generate_quiz_question(self, context: ContextSnapshot) -> QuizCard:
        """Generate dynamic quiz question using AI"""
        from lyo_app.ai_classroom.sdui_models import QuizOption
        from lyo_app.core.ai_resilience import ai_resilience_manager
        import json as _json

        topic = (
            context.review_due_items[0]
            if context.classroom_mode == ClassroomMode.REVIEW and context.review_due_items
            else context.topic or "the current concept"
        )
        lesson_content = context.lesson_content or ""

        try:
            covered = _SESSION_PROGRESS.get(context.session_id, {}).get("covered", [])
            taught_context = "\n".join(covered[-4:]) if covered else ""
            prompt = (
                f"Generate a single multiple-choice quiz question about the following lesson: '{context.lesson_title or topic}'.\n"
                f"Write the question, options, and feedback in {context.language_code}.\n"
                f"Lesson Content:\n{lesson_content}\n\n"
                f"What the teacher just taught in class (test THIS material):\n{taught_context}\n\n"
                f"The question must test understanding of the specific concepts described above — never a generic question.\n"
                f"Each distractor must represent a plausible, distinct misconception. "
                f"Give option-specific feedback and a remediation cue.\n"
                f"Return ONLY valid JSON (no markdown) with this exact structure:\n"
                f'{{"question": "...", "options": ['
                f'{{"id": "a", "label": "...", "is_correct": false, "feedback_correct": null, "feedback_incorrect": "...", "misconception_tag": "...", "remediation_hint": "..."}}, '
                f'{{"id": "b", "label": "...", "is_correct": true, "feedback_correct": "...", "feedback_incorrect": null, "misconception_tag": null, "remediation_hint": null}}, '
                f'{{"id": "c", "label": "...", "is_correct": false, "feedback_correct": null, "feedback_incorrect": "...", "misconception_tag": "...", "remediation_hint": "..."}}, '
                f'{{"id": "d", "label": "...", "is_correct": false, "feedback_correct": null, "feedback_incorrect": "...", "misconception_tag": "...", "remediation_hint": "..."}}'
                f']}}'
            )

            # Call the resilient AI manager with Gemini and OpenAI fallbacks.
            response = await ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": f"You are a world-class course designer. Write in {context.language_code}. Output ONLY valid JSON quiz questions. No prose, no markdown — pure JSON."},
                    {"role": "user", "content": prompt}
                ],
                provider_order=["gpt-4o-mini", "gemini-2.5-flash"],
                # Cached quizzes repeat the identical question forever.
                use_cache=False,
            )

            # When every provider has failed, ai_resilience returns the canned
            # apology with is_fallback=True. Trip to local fallback below.
            if response.get("is_fallback"):
                raise RuntimeError("ai_resilience returned is_fallback")

            # Parse the JSON response from the AI
            raw = response.get("content", "").strip()
            # Strip markdown fences if present
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].strip()

            # Resilient JSON Object extraction: find first { and last }
            first_brace = raw.find('{')
            last_brace = raw.rfind('}')
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                raw = raw[first_brace:last_brace+1].strip()

            try:
                data = _json.loads(raw)
            except Exception as json_err:
                logger.warning(f"⚠️ json.loads failed for quiz, trying ast.literal_eval: {json_err}")
                try:
                    import ast
                    data = ast.literal_eval(raw)
                except Exception as ast_err:
                    logger.error(f"❌ Both json.loads and ast.literal_eval failed for quiz: {ast_err}")
                    raise RuntimeError(f"Failed to parse quiz JSON: {json_err}")

            options = [
                QuizOption(
                    id=opt["id"],
                    label=opt["label"],
                    is_correct=opt.get("is_correct", False),
                    feedback_correct=opt.get("feedback_correct"),
                    feedback_incorrect=opt.get("feedback_incorrect"),
                    misconception_tag=opt.get("misconception_tag"),
                    remediation_hint=opt.get("remediation_hint"),
                )
                for opt in data["options"]
            ]

            return QuizCard(
                question=data["question"],
                options=options,
                allow_multiple_attempts=True,
                concept_id=context.learning_objective or context.topic or "current_concept",
                language_code=context.language_code,
            )

        except Exception as e:
            logger.error(f"❌ Resilient AI quiz generation failed, using fallback: {e}")

        # Fallback static question (only when AI is unavailable)
        is_spanish = context.language_code.lower().startswith("es")
        core = (
            lesson_content.strip().split(".")[0]
            or (
                f"La relación principal de la lección sobre {topic}"
                if is_spanish
                else f"The lesson's stated relationship in {topic}"
            )
        )[:260]
        if is_spanish:
            option_copy = {
                "correct": "Eso coincide con la relación enseñada en la lección.",
                "b_label": f"{topic} funciona solo cuando todos los valores son idénticos.",
                "b_feedback": "Eso añade una condición absoluta que la lección no estableció.",
                "b_hint": "Separa la relación principal de los casos especiales.",
                "c_label": f"{topic} es principalmente una regla que se memoriza sin razonar.",
                "c_feedback": "La lección presenta la idea como una relación que puedes explicar y aplicar.",
                "c_hint": "Vuelve a conectar el procedimiento con la razón por la que funciona.",
                "d_label": f"{topic} no puede aplicarse fuera del ejemplo mostrado.",
                "d_feedback": "Un ejemplo ilustra la idea; no limita dónde puede usarse.",
                "d_hint": "Identifica qué rasgos del ejemplo son esenciales.",
                "question": f"¿Cuál opción representa el objetivo principal al estudiar {topic}?",
            }
        else:
            option_copy = {
                "correct": "That matches the relationship taught in the lesson.",
                "b_label": f"{topic} works only when every value is identical.",
                "b_feedback": "That adds an absolute condition the lesson did not establish.",
                "b_hint": "Separate the core relationship from special cases.",
                "c_label": f"{topic} is mainly a rule to memorize without reasoning.",
                "c_feedback": "The lesson treats the idea as a relationship you can explain and apply.",
                "c_hint": "Reconnect the procedure to why it works.",
                "d_label": f"{topic} cannot be applied outside the example shown.",
                "d_feedback": "A worked example illustrates the idea; it does not limit its use.",
                "d_hint": "Identify which features of the example are essential.",
                "question": f"Which option represents the core objective when studying {topic}?",
            }
        options = [
            QuizOption(
                id="a",
                label=core,
                is_correct=True,
                feedback_correct=option_copy["correct"],
            ),
            QuizOption(
                id="b",
                label=option_copy["b_label"],
                is_correct=False,
                feedback_incorrect=option_copy["b_feedback"],
                misconception_tag="overgeneralized_condition",
                remediation_hint=option_copy["b_hint"],
            ),
            QuizOption(
                id="c",
                label=option_copy["c_label"],
                is_correct=False,
                feedback_incorrect=option_copy["c_feedback"],
                misconception_tag="procedure_without_meaning",
                remediation_hint=option_copy["c_hint"],
            ),
            QuizOption(
                id="d",
                label=option_copy["d_label"],
                is_correct=False,
                feedback_incorrect=option_copy["d_feedback"],
                misconception_tag="example_as_boundary",
                remediation_hint=option_copy["d_hint"],
            ),
        ]
        return QuizCard(
            question=option_copy["question"],
            options=options,
            allow_multiple_attempts=True,
            concept_id=context.learning_objective or context.topic or "current_concept",
            language_code=context.language_code,
        )


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎪 MASTER SCENE LIFECYCLE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════════

class SceneLifecycleEngine:
    """Master orchestrator of the four-phase scene lifecycle"""

    # Class-level state tracking to persist across transient instances
    _active_scenes: Dict[str, Scene] = {}
    _session_contexts: Dict[str, Any] = {}
    _session_lesson_indices: Dict[str, int] = {}

    def __init__(self, db: AsyncSession, websocket_manager: Optional[Any] = None):
        # Phase components
        self.trigger_listener = TriggerListener()
        self.context_assembler = ContextAssembler(db)
        self.director = ClassroomDirector()

        # Initialize compiler with TutorAgent so it can generate real AI content
        try:
            tutor_agent = get_tutor_agent()
            self.compiler = SceneCompiler(ai_service=tutor_agent)
            logger.info("✅ SceneCompiler initialized with TutorAgent")
        except Exception as e:
            logger.warning(f"⚠️ TutorAgent unavailable, compiler will use templates: {e}")
            self.compiler = SceneCompiler()

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
    ) -> None:
        """Persist guided classroom position in ClassroomSession.context."""
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
            if not session:
                session = ClassroomSession(
                    user_id=user_id,
                    title=trigger.session_id,
                    subject=context.topic,
                    session_type="guided_ai",
                    context={},
                )
                self.db.add(session)

            durable_context = dict(session.context or {})
            durable_context.update({
                "current_lesson_index": context.lesson_index,
                "mastered_lessons": list(progress.get("mastered_lessons", [])),
                "evidence": dict(progress.get("evidence", {})),
                "hint_counts": dict(progress.get("hint_counts", {})),
                "misconception_history": list(progress.get("misconception_history", []))[-12:],
                "learning_objective": progress.get("learning_objective"),
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
            session.is_active = not context.course_complete
            session.updated_at = datetime.utcnow()
            if context.course_complete:
                session.ended_at = datetime.utcnow()
            await self.db.commit()
        except (ValueError, TypeError):
            return
        except Exception as e:
            logger.warning(f"⚠️ Could not persist classroom progress: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass

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
        """Execute complete four-phase lifecycle"""
        logger.info(f"🎭 LIFECYCLE START: {trigger.trigger_type} for session {trigger.session_id}")
        start_time = time.time()

        try:
            # PHASE 1: Already have trigger (Listen)
            logger.debug(f"Phase 1 (Trigger): {trigger.trigger_type}")

            # PHASE 2: Context Assembly (Think)
            context = await self.context_assembler.assemble_context(trigger)
            # Inject cached lesson_index from previous CONTINUE advances
            if trigger.session_id in self.session_lesson_indices:
                context.lesson_index = self.session_lesson_indices[trigger.session_id]
                # Re-resolve lesson data with updated index
                context.lesson_title, context.lesson_content, context.total_lessons = \
                    await self.context_assembler._resolve_current_lesson(
                        context.course_id, context.lesson_index
                    )
                if context.lesson_title and not context.topic:
                    context.topic = context.lesson_title
            self.session_contexts[trigger.session_id] = context
            logger.debug(f"Phase 2 (Context): {len(context.knowledge_states)} concepts analyzed")

            # Guided mastery gate: recognition unlocks a transfer task; only
            # recognition plus transfer marks a lesson as mastered.
            action_data = trigger.action_data or {}
            action_intent = action_data.get("action_intent")
            answer_data = action_data.get("answer_data", {})
            progress = _SESSION_PROGRESS.setdefault(
                trigger.session_id, {"scene": 0, "covered": [], "mastered_lessons": []}
            )
            mastered_lessons = set(progress.get("mastered_lessons", []))
            evidence = progress.setdefault("evidence", {})
            lesson_key = str(context.lesson_index)
            lesson_evidence = evidence.setdefault(
                lesson_key, {"recognition": False, "transfer": False}
            )

            if action_intent == ActionIntent.SUBMIT_ANSWER:
                answer_is_correct = answer_data.get("is_correct") is True
                context.learner_signal = (
                    "correct_answer" if answer_is_correct else "incorrect_answer"
                )
                lesson_evidence["recognition"] = answer_is_correct
                if not answer_is_correct and answer_data.get("misconception_tag"):
                    history = progress.setdefault("misconception_history", [])
                    history.append({
                        "lesson_index": context.lesson_index,
                        "tag": answer_data.get("misconception_tag"),
                        "at": datetime.utcnow().isoformat(),
                    })

            if action_intent == ActionIntent.SUBMIT_TRANSFER:
                transfer_is_correct = answer_data.get("is_correct") is True
                context.learner_signal = (
                    "correct_transfer" if transfer_is_correct else "incorrect_transfer"
                )
                lesson_evidence["transfer"] = transfer_is_correct
                if transfer_is_correct and lesson_evidence.get("recognition"):
                    mastered_lessons.add(context.lesson_index)
                    progress["mastered_lessons"] = sorted(mastered_lessons)

            if action_intent == ActionIntent.CONTINUE and context.lesson_index in mastered_lessons:
                next_index = context.lesson_index + 1
                if context.total_lessons > 0 and next_index < context.total_lessons:
                    context.lesson_index = next_index
                    self.session_lesson_indices[trigger.session_id] = next_index
                    action_data["advanced_after_mastery"] = True
                    context.lesson_title, context.lesson_content, context.total_lessons = \
                        await self.context_assembler._resolve_current_lesson(
                            context.course_id, next_index
                        )
                    context.learning_objective = context.lesson_title or context.topic
                    context.source_attributions = [
                        "Course material"
                        + (f": {context.course_title}" if context.course_title else "")
                        + (f" — {context.lesson_title}" if context.lesson_title else "")
                    ]
                    try:
                        from lyo_app.ai_classroom.conversation_flow import get_conversation_manager
                        conv_session = get_conversation_manager().get_session(trigger.session_id)
                        if conv_session:
                            conv_session.current_lesson_index = next_index
                    except Exception:
                        pass
                    logger.info(f"📖 Evidence gate advanced lesson to {next_index}")
                else:
                    context.course_complete = True
                    action_data["course_complete"] = True
                    logger.info("🏁 All available classroom lessons mastered")

            context.overall_progress = min(
                1.0,
                len(mastered_lessons) / max(context.total_lessons, 1),
            )
            progress["current_lesson_index"] = context.lesson_index
            progress["course_complete"] = context.course_complete
            self.session_contexts[trigger.session_id] = context
            await self._persist_session_progress(trigger, context, progress)

            # PHASE 3: Director Decision (Decide)
            decision = await self.director.decide_scene(trigger, context)
            logger.debug(f"Phase 3 (Director): {decision.selected_scene_type} selected")

            # PHASE 4: SDUI Compilation (Act)
            scene = await self.compiler.compile_scene(decision, context, trigger)
            self.active_scenes[scene.scene_id] = scene
            logger.debug(f"Phase 4 (Compiler): {len(scene.components)} components compiled")

            # Stream to client
            if self.websocket_manager:
                await self._stream_scene_to_client(scene, trigger.session_id)

            total_time = (time.time() - start_time) * 1000
            logger.info(f"✅ LIFECYCLE COMPLETE: {scene.scene_id} in {total_time:.0f}ms")

            return scene

        except Exception as e:
            logger.error(f"❌ LIFECYCLE FAILED: {e}")
            # Return fallback scene
            return await self._create_fallback_scene(trigger)

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

    async def _create_fallback_scene(self, trigger: Trigger) -> Scene:
        """Create safe fallback scene when errors occur"""
        language_code = str(
            _SESSION_PROGRESS.get(trigger.session_id, {}).get(
                "language_code", "en-US"
            )
        )
        is_spanish = language_code.lower().startswith("es")
        return Scene(
            scene_type=SceneType.INSTRUCTION,
            components=[
                TeacherMessage(
                    text=(
                        "Retomemos una idea a la vez cuando estés listo."
                        if is_spanish
                        else "Let's continue with one idea at a time when you're ready."
                    ),
                    emotion="encouraging",
                    audio_mood=AudioMood.CALM,
                    language_code=language_code,
                ),
                CTAButton(
                    label="Continuar" if is_spanish else "Continue",
                    action_intent=ActionIntent.CONTINUE,
                    language_code=language_code,
                ),
            ]
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
                "action_intent": action_intent,
                **(action_data or {})
            },
            component_id=component_id,
            urgency=5  # User actions are medium priority
        )

        return await self.process_trigger(trigger)

    async def handle_quiz_submission(
        self,
        user_id: str,
        session_id: str,
        quiz_component_id: str,
        selected_option_id: str,
        response_time_ms: int,
    ) -> Scene:
        """Validate a quiz server-side and preserve distractor diagnosis."""
        validated_correct = False
        validated_skill_id = (
            self.session_contexts.get(session_id).learning_objective
            if self.session_contexts.get(session_id)
            else None
        )
        selected_feedback = None
        misconception_tag = None
        remediation_hint = None
        active_scene = self.active_scenes.get(
            next(
                (
                    sid for sid, scene in self.active_scenes.items()
                    if any(c.component_id == quiz_component_id for c in scene.components)
                ),
                None,
            )
        ) if self.active_scenes else None

        if active_scene:
            for comp in active_scene.components:
                if comp.component_id == quiz_component_id and hasattr(comp, "options"):
                    validated_skill_id = getattr(comp, "concept_id", None) or validated_skill_id
                    for option in comp.options:
                        if option.id == selected_option_id:
                            validated_correct = option.is_correct
                            selected_feedback = (
                                option.feedback_correct
                                if validated_correct
                                else option.feedback_incorrect
                            )
                            misconception_tag = option.misconception_tag
                            remediation_hint = option.remediation_hint
                            break
                    break

        progress = _SESSION_PROGRESS.get(session_id, {})
        session_context = self.session_contexts.get(session_id)
        lesson_index = session_context.lesson_index if session_context else 0
        hints_used = int(
            progress.get("hint_counts", {}).get(str(lesson_index), 0)
        )

        try:
            user_id_int = int(user_id)
            from lyo_app.personalization.schemas import KnowledgeTraceRequest
            from lyo_app.personalization.service import PersonalizationEngine
            await PersonalizationEngine().trace_knowledge(
                self.db,
                KnowledgeTraceRequest(
                    learner_id=str(user_id_int),
                    skill_id=validated_skill_id or "current_concept",
                    item_id=validated_skill_id or "current_concept",
                    correct=validated_correct,
                    time_taken_seconds=max(response_time_ms / 1000.0, 1.0),
                    hints_used=hints_used,
                ),
            )
        except (ValueError, TypeError):
            logger.debug("Guest quiz result is not persisted")
        except Exception as exc:
            logger.warning("Could not persist classroom recognition evidence: %s", exc)
            try:
                await self.db.rollback()
            except Exception:
                pass

        trigger = Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id=user_id,
            session_id=session_id,
            action_data={
                "action_intent": ActionIntent.SUBMIT_ANSWER,
                "answer_data": {
                    "selected_option_id": selected_option_id,
                    "is_correct": validated_correct,
                    "response_time_ms": response_time_ms,
                    "feedback": selected_feedback,
                    "misconception_tag": misconception_tag,
                    "remediation_hint": remediation_hint,
                },
            },
            component_id=quiz_component_id,
            urgency=7 if not validated_correct else 3,
        )
        return await self.process_trigger(trigger)

    async def handle_transfer_submission(
        self,
        user_id: str,
        session_id: str,
        input_component_id: str,
        response: str,
        response_time_ms: int = 0,
    ) -> Scene:
        """Score explanation/application evidence from the active server rubric."""
        validated_correct = False
        coverage = 0.0
        missing: List[str] = []
        skill_id = (
            self.session_contexts.get(session_id).learning_objective
            if self.session_contexts.get(session_id)
            else "current_concept"
        )
        expected_keywords: List[str] = []
        min_words = 6
        min_score = 0.25

        active_scene = self.active_scenes.get(
            next(
                (
                    sid for sid, scene in self.active_scenes.items()
                    if any(c.component_id == input_component_id for c in scene.components)
                ),
                None,
            )
        ) if self.active_scenes else None
        if active_scene:
            for comp in active_scene.components:
                if isinstance(comp, InputField) and comp.component_id == input_component_id:
                    skill_id = comp.concept_id or skill_id
                    expected_keywords = list(comp.expected_keywords)
                    min_words = comp.min_words
                    min_score = comp.min_score
                    validated_correct, coverage, missing = score_transfer_response(
                        response,
                        expected_keywords,
                        min_words=min_words,
                        min_score=min_score,
                    )
                    break

        feedback = (
            "Your explanation uses the lesson idea in a new situation."
            if validated_correct
            else (
                "Add the missing reasoning link"
                + (f" around {', '.join(missing)}" if missing else "")
                + f". Aim for at least {min_words} words and explain why the example works."
            )
        )

        progress = _SESSION_PROGRESS.get(session_id, {})
        session_context = self.session_contexts.get(session_id)
        lesson_index = session_context.lesson_index if session_context else 0
        hints_used = int(progress.get("hint_counts", {}).get(str(lesson_index), 0))
        try:
            user_id_int = int(user_id)
            from lyo_app.personalization.service import PersonalizationEngine
            await PersonalizationEngine().dkt.update_mastery(
                self.db,
                user_id_int,
                skill_id or "current_concept",
                validated_correct,
                max(response_time_ms / 1000.0, 1.0),
                hints_used,
            )
        except (ValueError, TypeError):
            logger.debug("Guest transfer evidence is not persisted")
        except Exception as exc:
            logger.warning("Could not persist classroom transfer evidence: %s", exc)
            try:
                await self.db.rollback()
            except Exception:
                pass

        trigger = Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id=user_id,
            session_id=session_id,
            action_data={
                "action_intent": ActionIntent.SUBMIT_TRANSFER,
                "message": response,
                "answer_data": {
                    "is_correct": validated_correct,
                    "coverage": coverage,
                    "missing_keywords": missing,
                    "feedback": feedback,
                    "remediation_hint": ", ".join(missing) if missing else None,
                },
            },
            component_id=input_component_id,
            urgency=6 if not validated_correct else 3,
        )
        return await self.process_trigger(trigger)

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

    def get_session_context(self, session_id: str) -> Optional[ContextSnapshot]:
        """Get current context for a session"""
        return self.session_contexts.get(session_id)

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
    "expected_transfer_keywords", "score_transfer_response",
    "ClassroomDirector", "DirectorDecision",
    "SceneCompiler"
]
