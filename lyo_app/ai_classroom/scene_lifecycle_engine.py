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

        # Resolve current lesson content from the DB
        context.lesson_title, context.lesson_content, context.total_lessons = \
            await self._resolve_current_lesson(context.course_id, context.lesson_index)
        # If lesson gave us a more specific topic, use it
        if context.lesson_title and not context.topic:
            context.topic = context.lesson_title

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

        # 2) Look up the ConversationManager in-memory session
        if not topic:
            try:
                from lyo_app.ai_classroom.conversation_flow import get_conversation_manager
                cm = get_conversation_manager()
                conv_session = cm.get_session(trigger.session_id)
                if conv_session:
                    topic = conv_session.current_topic
                    course_id = course_id or conv_session.current_course_id
                    lesson_index = conv_session.current_lesson_index
            except Exception as e:
                logger.warning(f"⚠️ Could not look up ConversationSession: {e}")

        # 3) If we still don't have a course_id, try using session_id as course_id
        #    (iOS sends courseId as the WebSocket session_id)
        if not course_id:
            course_id = trigger.session_id

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
                # It's a UUID, so it might be a ChatCourse or GeneratedCourseModel
                try:
                    from lyo_app.chat.models import ChatCourse
                    from sqlalchemy import select
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
            # It's a UUID, try getting lesson from ChatCourse or GeneratedCourseModel
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
                        select(GeneratedCourseModel.modules).where(GeneratedCourseModel.id == course_id)
                    )
                    row = result.first()
                    if row and row.modules:
                        modules = row.modules
                
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
        """Retrieve current mastery states from the mastery_states table"""
        try:
            from lyo_app.ai_classroom.models import MasteryState as MasteryStateDB
            result = await self.db.execute(
                select(MasteryStateDB).where(MasteryStateDB.user_id == user_id)
            )
            rows = result.scalars().all()
            if rows:
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
            logger.warning(f"⚠️ Could not query mastery states: {e}")
        return []

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
        """Core decision logic - this is where the magic happens"""

        # PRIORITY 1: Handle high-frustration situations immediately
        if context.frustration.frustration_score > 0.6:
            if context.frustration.consecutive_failures >= 3:
                return DirectorDecision(
                    selected_scene_type=SceneType.CORRECTION,
                    reasoning="High frustration with multiple failures - need peer normalization",
                    confidence=0.9,
                    suggested_components=[ComponentType.STUDENT_PROMPT, ComponentType.TEACHER_MESSAGE],
                    require_audio=True
                )

        # PRIORITY 2: Celebrate achievements to maintain motivation
        if trigger.trigger_type == TriggerType.ACHIEVEMENT_UNLOCK:
            return DirectorDecision(
                selected_scene_type=SceneType.CELEBRATION,
                reasoning="Achievement unlocked - reinforce success",
                confidence=0.95,
                suggested_components=[ComponentType.CELEBRATION, ComponentType.CTA_BUTTON],
                estimated_duration_seconds=10
            )

        # PRIORITY 3: Handle user actions based on context
        if trigger.trigger_type == TriggerType.USER_ACTION:
            action_intent = trigger.action_data.get("action_intent") if trigger.action_data else None

            if action_intent == ActionIntent.CONTINUE:
                # ── Lesson Progression ────────────────────────────────
                # Every 3rd lesson → quiz to reinforce learning
                if context.lesson_index > 0 and context.lesson_index % 3 == 0:
                    return DirectorDecision(
                        selected_scene_type=SceneType.CHALLENGE,
                        reasoning=f"Quiz time after lesson {context.lesson_index}",
                        confidence=0.85,
                        suggested_components=[ComponentType.QUIZ_CARD],
                        require_interaction=True,
                        estimated_duration_seconds=45
                    )
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning=f"Continue to lesson {context.lesson_index}"
                              + (f": {context.lesson_title}" if hasattr(context, 'lesson_title') and context.lesson_title else ""),
                    confidence=0.8,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON]
                )

            elif action_intent == ActionIntent.REQUEST_HINT:
                # User is stuck - provide gentle guidance
                return DirectorDecision(
                    selected_scene_type=SceneType.INSTRUCTION,
                    reasoning="User requested hint - provide scaffolding",
                    confidence=0.8,
                    suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                    require_audio=True
                )

            elif action_intent == ActionIntent.SUBMIT_ANSWER:
                # Answer submitted - evaluate and respond
                answer_data = trigger.action_data.get("answer_data", {})
                if answer_data.get("is_correct"):
                    # Correct answer - move forward or challenge
                    if self._should_add_challenge(context):
                        return DirectorDecision(
                            selected_scene_type=SceneType.CHALLENGE,
                            reasoning="Correct answer + high mastery - provide challenge",
                            confidence=0.75,
                            suggested_components=[ComponentType.QUIZ_CARD],
                            require_interaction=True
                        )
                    else:
                        return DirectorDecision(
                            selected_scene_type=SceneType.INSTRUCTION,
                            reasoning="Correct answer - continue instruction",
                            confidence=0.8,
                            suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON]
                        )
                else:
                    # Incorrect answer - determine intervention level
                    return DirectorDecision(
                        selected_scene_type=SceneType.CORRECTION,
                        reasoning="Incorrect answer - provide targeted correction",
                        confidence=0.85,
                        suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                        require_audio=True
                    )

        # PRIORITY 4: Handle timeouts with gentle re-engagement
        if trigger.trigger_type == TriggerType.SYSTEM_TIMEOUT:
            return DirectorDecision(
                selected_scene_type=SceneType.INSTRUCTION,
                reasoning="User inactive - gentle re-engagement",
                confidence=0.6,
                suggested_components=[ComponentType.TEACHER_MESSAGE, ComponentType.CTA_BUTTON],
                require_audio=True
            )

        # FALLBACK: Default instruction scene
        return DirectorDecision(
            selected_scene_type=SceneType.INSTRUCTION,
            reasoning="Default instruction scene",
            confidence=0.5,
            suggested_components=[ComponentType.TEACHER_MESSAGE]
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
            instruction_text = f"Let's continue learning about {topic}. Are you ready?"

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
            label="Continue",
            action_intent=ActionIntent.CONTINUE,
            button_style="primary",
            priority=len(paragraphs),
            delay_ms=min(len(paragraphs) * 1500, 5000)
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

        # Teacher correction
        topic_hint = f" about {context.topic}" if context.topic else ""
        components.append(TeacherMessage(
            text=f"Let me help clarify this concept{topic_hint} for you.",
            emotion="concerned",
            audio_mood=AudioMood.GENTLE,
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

        components.append(Celebration(
            message="Excellent work! You're making great progress! 🎉",
            celebration_type="standard",
            particle_effect="confetti",
            achievement_type="streak",
            points_earned=10,
            priority=0
        ))

        components.append(CTAButton(
            label="Keep Going!",
            action_intent=ActionIntent.CONTINUE,
            button_style="primary",
            priority=1
        ))

        return components

    async def _generate_instruction_content(self, context: ContextSnapshot) -> str:
        """Generate dynamic instruction content using AI TutorAgent"""
        try:
            tutor_agent = self.ai_service  # TutorAgent instance

            topic = context.topic or "general learning"
            course_label = f" in the course '{context.course_title}'" if context.course_title else ""

            logger.info(
                f"📝 Generating instruction: lesson_title={context.lesson_title!r}, "
                f"lesson_index={context.lesson_index}, total={context.total_lessons}, "
                f"topic={context.topic!r}, course={context.course_title!r}"
            )

            # Build a contextual prompt for the tutor
            # If we have lesson-specific data, use it for a focused lesson
            if context.lesson_title:
                prompt = (
                    f"You are Lyo, an expert AI tutor{course_label}. "
                    f"You are now teaching Lesson {context.lesson_index + 1} of {context.total_lessons}: "
                    f"'{context.lesson_title}'.\n\n"
                )
                if context.lesson_content:
                    # Include lesson source material (truncated for prompt size)
                    prompt += (
                        f"Use this source material as a guide for your explanation:\n"
                        f"{context.lesson_content[:2000]}\n\n"
                    )
                prompt += (
                    f"Explain this lesson clearly and engagingly in 2-3 paragraphs. "
                    f"Use examples, analogies, or real-world applications. "
                    f"End with a thought-provoking question to check understanding. "
                    f"IMPORTANT: Do NOT introduce yourself or say hello. Start directly with the lesson content."
                )
            else:
                # Fallback to generic prompt when no lesson data
                progress_note = (
                    f" The learner has completed {context.scenes_completed} scenes so far."
                    if context.scenes_completed > 0 else ""
                )
                prompt = (
                    f"You are Lyo, an expert AI tutor teaching about {topic}{course_label}.{progress_note} "
                    f"Provide a clear, engaging explanation of the next concept they should learn. "
                    f"Keep it concise (2-3 paragraphs max) and end with a thought-provoking question. "
                    f"Do NOT introduce yourself. Start directly with the teaching content."
                )

            # Map classroom context to TutorAgent's UserContext
            agent_context = AgentUserContext(
                user_id=context.user_id,
                course_id=context.course_id,
                current_topic=context.topic,
                completed_lessons=[
                    s.concept_id for s in context.knowledge_states if s.mastery_level > 0.8
                ],
                skill_level="beginner" if context.preferred_difficulty < 0.4 else (
                    "advanced" if context.preferred_difficulty > 0.7 else "intermediate"
                ),
            )

            response = await tutor_agent.chat(
                user_message=prompt,
                context=agent_context,
            )

            # Truncate to stay within TeacherMessage max_length (5000)
            text = response.message
            if len(text) > 4800:
                text = text[:4800] + "..."
            return text

        except Exception as e:
            logger.error(f"❌ TutorAgent instruction generation failed: {e}")
            topic = context.topic or "this concept"
            return f"Let's explore {topic} together. I'll guide you through the key ideas step by step."

    async def _generate_quiz_question(self, context: ContextSnapshot) -> QuizCard:
        """Generate dynamic quiz question using AI"""
        from lyo_app.ai_classroom.sdui_models import QuizOption
        import json as _json

        topic = context.topic or "the current concept"

        if self.ai_service:
            try:
                agent_context = AgentUserContext(
                    user_id=context.user_id,
                    course_id=context.course_id,
                    current_topic=context.topic,
                )

                prompt = (
                    f"Generate a single multiple-choice quiz question about {topic}. "
                    f"Return ONLY valid JSON (no markdown) with this exact structure: "
                    f'{{"question": "...", "options": ['
                    f'{{"id": "a", "label": "...", "is_correct": false}}, '
                    f'{{"id": "b", "label": "...", "is_correct": true}}, '
                    f'{{"id": "c", "label": "...", "is_correct": false}}, '
                    f'{{"id": "d", "label": "...", "is_correct": false}}'
                    f']}}'
                )

                response = await self.ai_service.chat(
                    user_message=prompt,
                    context=agent_context,
                )

                # Parse the JSON response from the AI
                raw = response.message.strip()
                # Strip markdown fences if present
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                data = _json.loads(raw)

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
                    concept_id=context.topic or "current_concept",
                )

            except Exception as e:
                logger.error(f"❌ AI quiz generation failed, using fallback: {e}")

        # Fallback static question (only when AI is unavailable)
        return QuizCard(
            question=f"Which of the following best describes {topic}?",
            options=[
                QuizOption(id="a", label="Option A", is_correct=False),
                QuizOption(id="b", label="Option B", is_correct=True),
                QuizOption(id="c", label="Option C", is_correct=False),
            ],
            allow_multiple_attempts=True,
            concept_id=context.topic or "current_concept",
        )


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎪 MASTER SCENE LIFECYCLE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════════

class SceneLifecycleEngine:
    """Master orchestrator of the four-phase scene lifecycle"""

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

        # State tracking
        self.active_scenes: Dict[str, Scene] = {}
        self.session_contexts: Dict[str, ContextSnapshot] = {}
        self.session_lesson_indices: Dict[str, int] = {}  # session_id → current lesson_index

        # Register default handlers
        self._register_handlers()

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

            # ── Lesson Progression: advance lesson_index on CONTINUE (skip quizzes) ──
            if trigger.trigger_type == TriggerType.USER_ACTION:
                action_intent = (trigger.action_data or {}).get("action_intent")
                if action_intent == ActionIntent.CONTINUE and scene.scene_type != SceneType.CHALLENGE:
                    old_idx = self.session_lesson_indices.get(trigger.session_id, 0)
                    new_idx = old_idx + 1
                    # Wrap around if we've passed the last lesson
                    if context.total_lessons > 0 and new_idx >= context.total_lessons:
                        new_idx = 0  # restart or could stop
                        logger.info(f"📚 Course completed! Wrapping to lesson 0")
                    self.session_lesson_indices[trigger.session_id] = new_idx
                    logger.info(f"📖 Advanced lesson index: {old_idx} → {new_idx}")
                    # Also update ConversationSession if it exists
                    try:
                        from lyo_app.ai_classroom.conversation_flow import get_conversation_manager
                        cm = get_conversation_manager()
                        conv_session = cm.get_session(trigger.session_id)
                        if conv_session:
                            conv_session.current_lesson_index = new_idx
                    except Exception:
                        pass

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
        validated_correct = is_correct  # fallback to client value
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