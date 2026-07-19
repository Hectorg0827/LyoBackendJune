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
    TeacherMessage, StudentPrompt, QuizCard, CTAButton, Celebration,
    AudioMood, ActionIntent, WebSocketPayload, SceneStreamPayload,
    UserActionPayload, SystemStatePayload, SceneMetadata
)

logger = logging.getLogger(__name__)

# Per-session teaching progression: scene counter + rolling summaries of what
# was already taught, so the director never replays the opening scene.
_SESSION_PROGRESS: Dict[str, Dict[str, Any]] = {}


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

    # Current learner input + durable personalization context
    learner_signal: Optional[str] = None
    learner_message: Optional[str] = None
    learner_response: Optional[str] = None
    learner_context: str = ""

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
        """Choose the next pedagogical move in the guided mastery loop."""
        action_data = trigger.action_data or {}
        action_intent = action_data.get("action_intent")
        answer_correct = (
            action_intent == ActionIntent.SUBMIT_ANSWER
            and action_data.get("answer_data", {}).get("is_correct") is True
        )

        # Do not turn a newly correct answer into another correction merely
        # because the learner struggled on earlier attempts.
        if (
            context.frustration.frustration_score > 0.6
            and context.frustration.consecutive_failures >= 3
            and not answer_correct
        ):
            return DirectorDecision(
                selected_scene_type=SceneType.CORRECTION,
                reasoning="Repeated misses require a smaller step and explicit reteaching",
                confidence=0.9,
                suggested_components=[ComponentType.STUDENT_PROMPT, ComponentType.TEACHER_MESSAGE],
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
                        reasoning="All lesson checkpoints are mastered",
                        confidence=0.95,
                        suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CELEBRATION],
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
                    reasoning="Check understanding before advancing",
                    confidence=0.9,
                    suggested_components=[ComponentType.QUIZ_CARD],
                    require_interaction=True,
                    estimated_duration_seconds=45,
                )

            if action_intent == ActionIntent.REQUEST_HINT:
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning="Learner is confused - reteach with a smaller step and worked example",
                    confidence=0.9,
                    difficulty_adjustment=-0.2,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
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
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                )

            if action_intent == ActionIntent.SKIP_AHEAD:
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning="Learner reports low challenge - increase depth without skipping the objective",
                    confidence=0.85,
                    difficulty_adjustment=0.25,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                )

            if action_intent == ActionIntent.RETRY:
                return DirectorDecision(
                    selected_scene_type=SceneType.CHALLENGE,
                    reasoning="Retry the checkpoint after correction",
                    confidence=0.9,
                    suggested_components=[ComponentType.QUIZ_CARD],
                    require_interaction=True,
                )

            if action_intent == ActionIntent.SUBMIT_ANSWER:
                if answer_correct:
                    return DirectorDecision(
                        selected_scene_type=SceneType.CELEBRATION,
                        reasoning="Checkpoint passed - acknowledge mastery before advancing",
                        confidence=0.95,
                        suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CELEBRATION, ComponentType.CTA_BUTTON],
                        estimated_duration_seconds=12,
                    )
                return DirectorDecision(
                    selected_scene_type=SceneType.CORRECTION,
                    reasoning="Checkpoint missed - explain the misconception and retry",
                    confidence=0.95,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                    require_audio=True,
                )

        if context.course_complete:
            return DirectorDecision(
                selected_scene_type=SceneType.CELEBRATION,
                reasoning="Persisted session shows every checkpoint complete",
                confidence=0.95,
                suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CELEBRATION],
                estimated_duration_seconds=15,
            )

        if trigger.trigger_type == TriggerType.SYSTEM_TIMEOUT:
            return DirectorDecision(
                selected_scene_type=SceneType.INSTRUCTION,
                reasoning="Open or re-engage the lesson with explicit teaching",
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

        elif decision.selected_scene_type == SceneType.CHALLENGE:
            components.extend(await self._create_challenge_components(context))

        elif decision.selected_scene_type == SceneType.CORRECTION:
            components.extend(await self._create_correction_components(context, trigger))

        elif decision.selected_scene_type == SceneType.CELEBRATION:
            components.extend(await self._create_celebration_components(context))

        # Always add progress indicator if not celebration
        if decision.selected_scene_type != SceneType.CELEBRATION:
            # Could add progress bar component here
            pass

        return components

    async def _create_instruction_components(self, context: ContextSnapshot) -> List[Component]:
        """Create components for instruction scenes"""
        components = []

        # Main teacher message
        if self.ai_service:
            # Dynamic AI-generated content
            instruction_text = await self._generate_instruction_content(context)
        else:
            # Template fallback — still include the topic when available
            topic = context.topic or "the next concept"
            instruction_text = f'[ {{"type": "speech", "speaker": "Teacher", "text": "Let\'s continue learning about {topic}. Are you ready?"}} ]'

        # Degenerate output (empty / bare brackets) teaches nothing and fails
        # TeacherMessage validation — swap in the topic-aware local fallback.
        if len(instruction_text.strip()) < 10 or instruction_text.strip() in ("[]", "[ ]", "{}"):
            instruction_text = self._local_instruction_fallback(context)

        # If the text is JSON (starts with '[' and ends with ']'), do not split it by paragraphs
        text_to_check = instruction_text.strip()
        if text_to_check.startswith('[') and text_to_check.endswith(']'):
            components.append(TeacherMessage(
                text=text_to_check,
                emotion="encouraging",
                audio_mood=AudioMood.CALM,
                concept_tags=[context.topic or "current_topic"],
                priority=0,
                delay_ms=0
            ))
        else:
            paragraphs = [p.strip() for p in instruction_text.split('\n\n') if p.strip()]
            
            for idx, paragraph in enumerate(paragraphs):
                delay = min(idx * 1500, 4900)  # Cap delay to 4900ms
                components.append(TeacherMessage(
                    text=paragraph,
                    emotion="encouraging",
                    audio_mood=AudioMood.CALM,
                    concept_tags=[context.topic or "current_topic"],
                    priority=idx,
                    delay_ms=delay
                ))

        # Continue button
        components.append(CTAButton(
            label="Check understanding",
            action_intent=ActionIntent.CONTINUE,
            button_style="primary",
            priority=100,  # Ensure it comes last
            delay_ms=5000
        ))

        return components

    async def _create_challenge_components(self, context: ContextSnapshot) -> List[Component]:
        """Create components for challenge/quiz scenes"""
        components = []

        # Quiz question
        quiz_question = await self._generate_quiz_question(context)
        components.append(quiz_question)

        return components

    async def _create_correction_components(self, context: ContextSnapshot, trigger: Trigger) -> List[Component]:
        """Create components for correction scenes"""
        components = []

        # Check if we should include peer normalization
        if context.frustration.consecutive_failures >= 2 and not context.peer_cooldown_active:
            # Add AI peer to normalize the error
            components.append(StudentPrompt(
                student_name="Sam",
                text="I thought that too! These concepts can be tricky at first.",
                personality_trait="supportive",
                purpose="normalize_error",
                priority=0
            ))

        # Reteach the missed idea rather than merely saying it was wrong.
        if self.ai_service:
            correction_text = await self._generate_instruction_content(context)
        else:
            correction_text = self._local_instruction_fallback(context)
        components.append(TeacherMessage(
            text=correction_text,
            emotion="concerned",
            audio_mood=AudioMood.GENTLE,
            concept_tags=[context.learning_objective or context.topic or "current_topic"],
            priority=1
        ))

        # Try again button
        components.append(CTAButton(
            label="Try Again",
            action_intent=ActionIntent.RETRY,
            button_style="secondary",
            priority=2
        ))

        return components

    async def _create_celebration_components(self, context: ContextSnapshot) -> List[Component]:
        """Create components for celebration scenes"""
        components = []

        if context.course_complete:
            components.append(TeacherMessage(
                text=(
                    f"You completed {context.course_title or context.topic or 'this course'} "
                    "and demonstrated the key ideas at every checkpoint. "
                    "Review your notebook, then choose one idea to apply outside the classroom."
                ),
                emotion="celebrating",
                audio_mood=AudioMood.UPBEAT,
                priority=0,
            ))
            celebration_message = "Course complete — you earned this! 🎉"
        else:
            components.append(TeacherMessage(
                text=(
                    f"Yes — that shows you understand "
                    f"{context.learning_objective or context.lesson_title or context.topic or 'this idea'}."
                ),
                emotion="encouraging",
                audio_mood=AudioMood.UPBEAT,
                priority=0,
            ))
            celebration_message = "Checkpoint mastered! 🎉"

        components.append(Celebration(
            message=celebration_message,
            celebration_type="standard",
            particle_effect="confetti",
            achievement_type="mastery",
            points_earned=10,
            priority=1
        ))

        if not context.course_complete:
            components.append(CTAButton(
                label="Next lesson",
                action_intent=ActionIntent.CONTINUE,
                button_style="primary",
                priority=2
            ))

        return components

    async def _generate_instruction_content(self, context: ContextSnapshot) -> str:
        """Generate dynamic instruction content using the Classroom Director System Prompt"""
        try:
            from lyo_app.ai_classroom.director_prompt import CLASSROOM_DIRECTOR_PROMPT
            from lyo_app.core.ai_resilience import ai_resilience_manager
            import json
            
            topic = context.topic or "general learning"
            course_title = context.course_title or topic
            session_number = context.lesson_index + 1
            user_name = "Learner"
            avg_mastery = (
                sum(k.mastery_level for k in context.knowledge_states)
                / max(len(context.knowledge_states), 1)
            )
            user_level = (
                "advanced" if max(avg_mastery, context.preferred_difficulty) >= 0.75
                else "intermediate" if max(avg_mastery, context.preferred_difficulty) >= 0.5
                else "beginner"
            )

            logger.info(
                f"📝 Generating instruction via AI Resilience Manager: lesson_title={context.lesson_title!r}, "
                f"lesson_index={context.lesson_index}, total={context.total_lessons}, "
                f"topic={topic!r}, course={course_title!r}"
            )

            # Progression: without this, every scene regenerated the same
            # opening class (and the response cache then replayed it verbatim).
            prog = _SESSION_PROGRESS.setdefault(
                context.session_id, {"scene": 0, "covered": []})
            prog["scene"] += 1
            scene_number = prog["scene"]
            covered = prog["covered"][-8:]

            input_block = f"""
INPUT FORMAT:
subject: "{course_title}"
session_number: {session_number}
scene_number: {scene_number}
user_name: "{user_name}"
learner_context: {json.dumps(context.learner_context or "No stored learner preferences yet.")}
last_session_recap: {json.dumps(covered[-1] if covered else "")}
already_covered: {json.dumps(covered)}
user_level: "{user_level}"
learning_objective: {json.dumps(context.learning_objective or context.lesson_title or topic)}
learner_signal: {json.dumps(context.learner_signal or "")}
learner_question: {json.dumps(context.learner_message or "")}
learner_response: {json.dumps(context.learner_response or "")}
lesson_title: "{context.lesson_title or topic}"
lesson_content: {json.dumps(context.lesson_content or "")}

TEACHING RESPONSE RULES:
- Keep the learning_objective visible in your reasoning and make every turn serve it.
- If learner_question is present, answer it directly before resuming the sequence.
- If learner_response is present, acknowledge its reasoning briefly and use it as evidence; do not pretend it was a question.
- If learner_signal is request_hint or confused, slow down, diagnose the likely gap, and use one worked example.
- If learner_signal is skip_ahead or too_easy, increase depth and transfer difficulty; do not merely move on.
- If learner_signal is incorrect_answer, explicitly explain the likely misconception, then show one worked example.
- Use learner_context only when relevant. Never invent preferences or history.
- Teach first. AI classmates are optional and may speak only when they clarify a misconception or model reasoning.

PROGRESSION RULES (CRITICAL):
- scene_number 1 is the ONLY scene that may use the opening protocol.
- If scene_number > 1: NO welcome, NO re-introduction, NO repeating the hook.
  Continue the SAME class exactly where it left off and teach the NEXT idea,
  strictly deeper or adjacent to what came before.
- NEVER re-teach anything listed in already_covered.
- Only emit session_end when the topic is genuinely concluded (never before
  scene 4) — most scenes should end mid-lesson, awaiting the learner.
- NEVER return an empty array. There is ALWAYS a deeper or adjacent idea to
  teach next; every scene must contain at least 6 turns.
"""
            # Injecting explicit instruction to use the generated lesson content
            prompt = (
                CLASSROOM_DIRECTOR_PROMPT + "\n\n"
                "## CURRENT LESSON TO TEACH:\n"
                "You must teach the following content:\n"
                f"Lesson Title: {context.lesson_title or topic}\n"
                f"Lesson Content:\n{context.lesson_content or ''}\n\n"
                "## INPUT STATE:\n"
                + input_block
            )

            # Call the resilient AI manager with Gemini and OpenAI fallbacks.
            response = await ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a rigorous, warm classroom teacher. Teach the exact lesson_content toward the stated learning_objective. Respond directly to learner_question, learner_response, and learner_signal. Use explanation, a worked example, and a concise check for understanding. AI classmates are optional and must never displace the teacher or the learner. Use learner_context only when relevant. Return ONLY a valid, non-empty JSON list of director turns. No prose or markdown."},
                    {"role": "user", "content": prompt}
                ],
                # gpt-4o-mini first: the Gemini key is currently revoked
                # ("reported as leaked"), so leading with it just burns a
                # circuit-breaker failure per scene.
                provider_order=["gpt-4o-mini", "gemini-2.5-flash"],
                # The director script is 20-25 JSON turns (~2500+ tokens); the
                # 1000-token default truncated mid-array, normalizing to "[]"
                # and killing every scene with a TeacherMessage validation error.
                max_tokens=3500,
                # Never serve a lesson from cache: identical inputs used to
                # replay the exact same lecture on every scene.
                use_cache=False,
            )

            # CRITICAL: when every provider has failed, ai_resilience_manager
            # does NOT raise — it returns a canned apology string with
            # is_fallback=True. Without this guard, that apology string was
            # being shipped verbatim to iOS as TeacherMessage.text, which is
            # exactly the "Experiencing technical issues" bug users hit.
            if response.get("is_fallback"):
                logger.warning(
                    "⚠️ AI resilience returned fallback for instruction — "
                    "falling back to local template (topic=%r)", topic
                )
                raise RuntimeError("ai_resilience returned is_fallback")

            text = response.get("content", "").strip()
            # Remove Markdown fences if any
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].strip()

            # Resilient JSON Array extraction: find first [ and last ]
            first_bracket = text.find('[')
            last_bracket = text.rfind(']')
            if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                text = text[first_bracket:last_bracket+1].strip()

            # Belt-and-suspenders: if the upstream service somehow returned an
            # apology string without setting is_fallback (e.g., a Gemini safety
            # block), reject it before it reaches the user.
            APOLOGY_PHRASES = (
                "Experiencing technical issues",
                "AI services unavailable",
                "temporarily unable to process",
            )
            if any(phrase in text for phrase in APOLOGY_PHRASES):
                logger.warning("⚠️ AI returned apology string — using local template (topic=%r)", topic)
                raise RuntimeError("ai_resilience returned apology content")

            # Ensure we return a clean JSON array string (starting with [ and ending with ])
            try:
                parsed = None
                try:
                    parsed = json.loads(text)
                except Exception as json_err:
                    logger.warning(f"⚠️ json.loads failed, trying ast.literal_eval: {json_err}")
                    try:
                        import ast
                        parsed = ast.literal_eval(text)
                    except Exception as ast_err:
                        logger.error(f"❌ Both json.loads and ast.literal_eval failed: {ast_err}")
                        raise RuntimeError(f"Failed to parse instruction JSON: {json_err}")

                if isinstance(parsed, dict):
                    # Extract the first list value found (e.g., 'turns', 'scene', 'components')
                    list_extracted = False
                    for key, val in parsed.items():
                        if isinstance(val, list):
                            text = json.dumps(val)
                            list_extracted = True
                            break
                    if not list_extracted:
                        # Fallback: if no list is found inside the dict, wrap the dict in a list
                        text = json.dumps([parsed])
                elif isinstance(parsed, list):
                    if not parsed:
                        # Flaky model behavior — one retry with a direct nudge
                        # usually recovers before we resort to the template.
                        logger.warning("⚠️ Director returned []; retrying once")
                        retry = await ai_resilience_manager.chat_completion(
                            messages=[
                                {"role": "system", "content": "You are the classroom director. Return ONLY a non-empty JSON array of director turns (at least 6 turns). Never return an empty array."},
                                {"role": "user", "content": prompt},
                            ],
                            provider_order=["gpt-4o-mini", "gemini-2.5-flash"],
                            max_tokens=3500,
                            use_cache=False,
                        )
                        retry_text = (retry.get("content") or "").strip()
                        fb = retry_text.find('[')
                        lb = retry_text.rfind(']')
                        if fb != -1 and lb > fb:
                            retry_text = retry_text[fb:lb + 1]
                        parsed = json.loads(retry_text)
                        if not isinstance(parsed, list) or not parsed:
                            raise RuntimeError("Director returned an empty turn list twice")
                    text = json.dumps(parsed)
                else:
                    raise RuntimeError("Parsed JSON is neither a list nor a dictionary")
            except Exception as e:
                logger.error(f"❌ JSON normalization failed: {e}")
                # Clear resilience manager cache so we don't get stuck with a broken cached AI response
                try:
                    ai_resilience_manager.request_cache.clear()
                    logger.info("🧹 Cleared AI Resilience Manager cache due to JSON parsing failure")
                except Exception as cache_err:
                    logger.warning(f"Failed to clear cache: {cache_err}")
                raise

            # Remember what this scene taught so the next one moves forward.
            try:
                speech_texts = [
                    t.get("text", "") for t in (parsed if isinstance(parsed, list) else [])
                    if isinstance(t, dict) and t.get("type") == "speech" and t.get("speaker") == "Teacher"
                ]
                summary = " / ".join(s[:110] for s in speech_texts[:2] if s)
                if summary:
                    prog["covered"].append(summary)
            except Exception:
                pass

            return text

        except Exception as e:
            logger.error(f"❌ TutorAgent resilient instruction generation failed: {e}")
            return self._local_instruction_fallback(context)

    def _local_instruction_fallback(self, context: ContextSnapshot) -> str:
        """Topic-aware multi-turn lesson opener used when every AI provider
        is down. Better than 'try again later' — gives the user something
        actually teachable while we recover.
        """
        import json
        import re
        topic = context.topic or context.course_title or "this concept"
        course_title = context.course_title or topic
        session = context.lesson_index + 1
        total = context.total_lessons or 1
        lesson_content = context.lesson_content or ""

        if lesson_content:
            paragraphs = [p.strip() for p in lesson_content.split('\n\n') if p.strip()]
            main_point = paragraphs[0] if paragraphs else f"Let's dive into {topic}."
            if main_point.startswith("#"):
                main_point = re.sub(r'^#+\s*', '', main_point)
            
            turns = [
                {
                    "type": "speech",
                    "speaker": "Teacher",
                    "text": f"Welcome back. Today we're learning about {topic} — lesson {session} of {total}."
                },
                {
                    "type": "speech",
                    "speaker": "Teacher",
                    "text": f"Here is the core concept: {main_point}"
                }
            ]
            if len(paragraphs) > 1:
                sub_point = paragraphs[1]
                if sub_point.startswith("#"):
                    sub_point = re.sub(r'^#+\s*', '', sub_point)
                turns.append({
                    "type": "speech",
                    "speaker": "Teacher",
                    "text": f"To understand this better, remember: {sub_point}"
                })
            turns.append({
                "type": "speech",
                "speaker": "Teacher",
                "text": "Let's work through this concept together. When you are ready, tap continue!"
            })
        else:
            turns = [
                {
                    "type": "speech",
                    "speaker": "Teacher",
                    "text": f"Welcome to {course_title} — lesson {session} of {total}. We're going to keep this focused and practical."
                },
                {
                    "type": "speech",
                    "speaker": "Teacher",
                    "text": f"Here's the goal for today: get a clear, working understanding of {topic} — what it is, why it matters, and where you'll see it."
                },
                {
                    "type": "speech",
                    "speaker": "Teacher",
                    "text": f"Think of {topic} as a tool. We'll start with the simplest version, then layer on the real-world details so it sticks."
                },
                {
                    "type": "speech",
                    "speaker": "Teacher",
                    "text": "When you're ready, tap continue and I'll walk you through the first idea step by step."
                }
            ]
        return json.dumps(turns)

    async def _generate_quiz_question(self, context: ContextSnapshot) -> QuizCard:
        """Generate dynamic quiz question using AI"""
        from lyo_app.ai_classroom.sdui_models import QuizOption
        from lyo_app.core.ai_resilience import ai_resilience_manager
        import json as _json

        topic = context.topic or "the current concept"
        lesson_content = context.lesson_content or ""

        try:
            covered = _SESSION_PROGRESS.get(context.session_id, {}).get("covered", [])
            taught_context = "\n".join(covered[-4:]) if covered else ""
            prompt = (
                f"Generate a single multiple-choice quiz question about the following lesson: '{context.lesson_title or topic}'.\n"
                f"Lesson Content:\n{lesson_content}\n\n"
                f"What the teacher just taught in class (test THIS material):\n{taught_context}\n\n"
                f"The question must test understanding of the specific concepts described above — never a generic question.\n"
                f"Return ONLY valid JSON (no markdown) with this exact structure:\n"
                f'{{"question": "...", "options": ['
                f'{{"id": "a", "label": "...", "is_correct": false}}, '
                f'{{"id": "b", "label": "...", "is_correct": true}}, '
                f'{{"id": "c", "label": "...", "is_correct": false}}, '
                f'{{"id": "d", "label": "...", "is_correct": false}}'
                f']}}'
            )

            # Call the resilient AI manager with Gemini and OpenAI fallbacks.
            # Strict JSON mode dropped here too — see _generate_instruction_content
            # for the full rationale (Gemini fails hard on strict mode + long prompts).
            response = await ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a world-class course designer. Output ONLY valid JSON quiz questions. No prose, no markdown — pure JSON."},
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
                )
                for opt in data["options"]
            ]

            return QuizCard(
                question=data["question"],
                options=options,
                allow_multiple_attempts=True,
                concept_id=context.learning_objective or context.topic or "current_concept",
            )

        except Exception as e:
            logger.error(f"❌ Resilient AI quiz generation failed, using fallback: {e}")

        # Fallback static question (only when AI is unavailable)
        options = [
            QuizOption(id="a", label=f"Understanding {topic}", is_correct=True),
            QuizOption(id="b", label="Applying the concept", is_correct=False),
            QuizOption(id="c", label="Reviewing the basics", is_correct=False),
            QuizOption(id="d", label="None of the above", is_correct=False)
        ]
        return QuizCard(
            question=f"Which of the following represents the core objective when studying {topic}?",
            options=options,
            allow_multiple_attempts=True,
            concept_id=context.learning_objective or context.topic or "current_concept"
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
                "learning_objective": progress.get("learning_objective"),
                "difficulty": progress.get("difficulty"),
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

            # Guided mastery gate: a correct checkpoint masters the current
            # lesson; only the following Continue may advance to the next one.
            action_data = trigger.action_data or {}
            action_intent = action_data.get("action_intent")
            progress = _SESSION_PROGRESS.setdefault(
                trigger.session_id, {"scene": 0, "covered": [], "mastered_lessons": []}
            )
            mastered_lessons = set(progress.get("mastered_lessons", []))

            if action_intent == ActionIntent.SUBMIT_ANSWER:
                answer_is_correct = (
                    action_data.get("answer_data", {}).get("is_correct") is True
                )
                context.learner_signal = (
                    "correct_answer" if answer_is_correct else "incorrect_answer"
                )
                if answer_is_correct:
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
                    try:
                        from lyo_app.ai_classroom.conversation_flow import get_conversation_manager
                        conv_session = get_conversation_manager().get_session(trigger.session_id)
                        if conv_session:
                            conv_session.current_lesson_index = next_index
                    except Exception:
                        pass
                    logger.info(f"📖 Mastery gate advanced lesson to {next_index}")
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
        scene = await self.process_trigger(trigger)

        # Schedule next timeout
        self.trigger_listener.schedule_timeout(trigger.session_id, delay_seconds=45)

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
        return Scene(
            scene_type=SceneType.INSTRUCTION,
            components=[
                TeacherMessage(
                    text="Let's continue with your learning journey.",
                    emotion="encouraging",
                    audio_mood=AudioMood.CALM
                )
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
        is_correct: bool,
        response_time_ms: int
    ) -> Scene:
        """Public API: Handle quiz answer submission with server-side validation"""

        # ── Server-side correctness check ────────────────────────────

        # Look up the active QuizCard scene to validate the answer.
        # The client-supplied `is_correct` is treated as a hint only;
        # the authoritative answer lives in the scene's QuizCard options.
        validated_correct = False  # fail closed if the authoritative scene is unavailable
        validated_skill_id = (
            self.session_contexts.get(session_id).learning_objective
            if self.session_contexts.get(session_id)
            else None
        )
        active_scene = self.active_scenes.get(
            next(
                (sid for sid, s in self.active_scenes.items()
                 if any(c.component_id == quiz_component_id for c in s.components)),
                None
            )
        ) if self.active_scenes else None

        if active_scene:
            for comp in active_scene.components:
                if comp.component_id == quiz_component_id and hasattr(comp, 'options'):
                    validated_skill_id = getattr(comp, "concept_id", None) or validated_skill_id
                    for opt in comp.options:
                        if opt.id == selected_option_id:
                            validated_correct = opt.is_correct
                            if validated_correct != is_correct:
                                logger.warning(
                                    f"⚠️ Quiz validation mismatch: client said "
                                    f"is_correct={is_correct}, server says {validated_correct}"
                                )
                            break
                    break

        # Persist the authoritative result in the same mastery model used by
        # personalization and by ContextAssembler. Guest sessions remain ephemeral.
        try:
            user_id_int = int(user_id)
            from lyo_app.personalization.service import PersonalizationEngine
            await PersonalizationEngine().dkt.update_mastery(
                self.db,
                user_id_int,
                validated_skill_id or "current_concept",
                validated_correct,
                max(response_time_ms / 1000.0, 1.0),
                0,
            )
        except (ValueError, TypeError):
            logger.debug("Guest quiz result is not persisted")
        except Exception as e:
            logger.warning(f"⚠️ Could not persist classroom mastery: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass

        # Determine frustration based on correctness and time
        urgency = 7 if not validated_correct else 3

        trigger = Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id=user_id,
            session_id=session_id,
            action_data={
                "action_intent": ActionIntent.SUBMIT_ANSWER,
                "answer_data": {
                    "selected_option_id": selected_option_id,
                    "is_correct": validated_correct,
                    "response_time_ms": response_time_ms
                }
            },
            component_id=quiz_component_id,
            urgency=urgency
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
    "ClassroomDirector", "DirectorDecision",
    "SceneCompiler"
]