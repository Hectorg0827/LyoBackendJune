"""
Unified AI Classroom Routes
The main API endpoints for Lyo's award-winning learning experience

Brings together:
- Intelligent chat with intent detection
- Multi-agent course generation
- TTS audio synthesis
- Image generation
- Real-time streaming
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Depends, Request, BackgroundTasks, Security
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .intent_detector import get_intent_detector, ChatIntent
from .conversation_flow import (
    get_conversation_manager,
    ConversationManager,
    FlowResponse,
    ConversationState
)
from lyo_app.streaming import get_sse_manager, stream_response, EventType, StreamEvent

from lyo_app.auth.dependencies import get_current_user
from lyo_app.models.enhanced import User
from lyo_app.core.database import get_async_session as get_db, AsyncSessionLocal
from lyo_app.ai_classroom.models import GraphCourse, LearningNode, LearningEdge, NodeType
from lyo_app.core.context_engine import ContextEngine
from lyo_app.personalization.soft_skills import SoftSkillsService, SoftSkillAnalyzer

logger = logging.getLogger(__name__)

# Authentication dependencies
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from lyo_app.auth.routes import api_key_header

# Optional security checks (auto_error=False allows us to handle missing creds manually)
optional_bearer = HTTPBearer(auto_error=False)
optional_api_key = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_current_user_or_guest(
    request: Request,
    db: AsyncSession = Depends(get_db),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(optional_bearer),
    api_key: Optional[str] = Security(optional_api_key)
) -> User:
    """
    Get current user (JWT) OR create a temporary guest user context (API Key).
    Allows 'Beginner' flow to generate courses before signup.
    """
    # 1. Try Bearer Token (Authenticated User)
    if bearer:
        try:
            # Re-use the standard dependency logic manually?
            # It's cleaner to use the dependency if we could, but we can't conditionally depend.
            # So we import the verifier.
            from lyo_app.auth.jwt_auth import verify_token_async
            from lyo_app.auth.service import AuthService
            
            token_data = await verify_token_async(bearer.credentials, expected_type="access")
            if token_data.user_id:
                user_id = int(token_data.user_id)
                auth_service = AuthService()
                user = await auth_service.get_user_by_id(db, user_id)
                if user:
                    return user
        except Exception as e:
            logger.warning(f"Bearer token validation failed in guest-optimistic auth: {e}")
            # Fallthrough to guest check
    
    # 2. Try API Key (Guest)
    if api_key:
        # We assume presence of valid API key header (validated by gateway or implicit trust for now)
        # In future, validate against DB/Env.
        logger.info("Allowing Guest access via API Key for Course Generation")
        
        # Create a transient Guest User object (not saved to DB)
        # We use a special ID format for guests
        return User(
            id="guest_session", 
            username="Guest Learner", 
            email="guest@lyo.app",
            is_active=True
        )

    # 3. Fail
    raise HTTPException(
        status_code=401, 
        detail="Not authenticated (Bearer Token or API Key required)"
    )


router = APIRouter(prefix="/api/v1/classroom", tags=["AI Classroom"])

# Initialize Context Engine
context_engine = ContextEngine()

async def analyze_soft_skills_task(user_id: int, message: str):
    """Background task to analyze and record soft skills."""
    try:
        analyzer = SoftSkillAnalyzer()
        service = SoftSkillsService()
        
        results = analyzer.analyze(message)
        if not results:
            return
            
        async with AsyncSessionLocal() as db:
            for result in results:
                await service.record_evidence(
                    db, 
                    user_id, 
                    result["skill"], 
                    result["delta"], 
                    result["desc"]
                )
                logger.info(f"Recorded soft skill evidence: {result['skill']} for user {user_id}")
    except Exception as e:
        logger.error(f"Error in soft skills analysis task: {e}")


# Request/Response Models

class ChatRequest(BaseModel):
    """Request for classroom chat"""
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    include_audio: bool = Field(default=False, description="Include TTS audio")
    stream: bool = Field(default=False, description="Stream response")


class ChatResponse(BaseModel):
    """Response from classroom chat"""
    session_id: str
    content: str
    response_type: str
    state: str
    generated_course_id: Optional[str] = None
    intent: Optional[Dict[str, Any]] = None
    audio_url: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    openClassroomPayload: Optional[Dict[str, Any]] = None


class GraphCourseItemRead(BaseModel):
    """Lightweight graph course summary matching the iOS GraphCourseItem contract."""
    id: str
    title: str
    description: str
    subject: str
    grade_band: str
    entry_node_id: Optional[str] = None
    estimated_minutes: int
    total_nodes: int
    created_at: Optional[datetime] = None


class SessionRequest(BaseModel):
    """Request to create a session"""
    user_id: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class SessionResponse(BaseModel):
    """Session information"""
    session_id: str
    state: str
    message_count: int
    current_topic: Optional[str] = None
    welcome_message: str


class IntentAnalysisRequest(BaseModel):
    """Request to analyze intent without responding"""
    message: str = Field(..., min_length=1, max_length=2000)


class IntentAnalysisResponse(BaseModel):
    """Intent analysis result"""
    intent_type: str
    confidence: float
    confidence_level: str
    topic: Optional[str]
    complexity_hint: str
    requires_generation: bool
    suggested_response_type: str
    reasoning: str
    strategy: Dict[str, Any]


# Routes


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    async for session in get_async_session():
        yield session


def _course_to_item(course: GraphCourse, total_nodes: int) -> GraphCourseItemRead:
    return GraphCourseItemRead(
        id=course.id,
        title=course.title,
        description=course.description or "",
        subject=course.subject,
        grade_band=course.grade_band or "general",
        entry_node_id=course.entry_node_id,
        estimated_minutes=course.estimated_minutes,
        total_nodes=total_nodes,
        created_at=course.created_at,
    )


async def _count_nodes(db: AsyncSession, course_id: str) -> int:
    result = await db.execute(
        select(func.count(LearningNode.id)).where(LearningNode.course_id == course_id)
    )
    return int(result.scalar() or 0)


async def _create_minimal_graph_course(
    db: AsyncSession,
    *,
    topic: str,
    creator_id: str,
    level: str = "beginner",
) -> GraphCourse:
    """Create a minimal playable graph course (linear graph) for iOS playback."""
    course = GraphCourse(
        title=f"{topic} ({level})",
        description=f"An interactive course on {topic}.",
        subject=topic,
        grade_band="general",
        estimated_minutes=20,
        difficulty=level,
        created_by=creator_id,
        is_published=True,
        is_template=False,
    )
    db.add(course)
    await db.flush()  # ensure course.id exists

    hook_node = LearningNode(
        course_id=course.id,
        node_type=NodeType.HOOK.value,
        content={
            "narration": f"Welcome! Today we’re going to learn {topic}. Ready to begin?",
            "visual_prompt": f"A clean, modern educational title card about {topic}",
            "keywords": [topic],
            "audio_mood": "calm",
            "duration_hint": 8.0,
        },
        sequence_order=0,
        estimated_seconds=10,
    )
    lesson_node = LearningNode(
        course_id=course.id,
        node_type=NodeType.NARRATIVE.value,
        content={
            "narration": f"Let’s start with the basics of {topic}. Here’s the core idea, in simple terms...",
            "visual_prompt": f"A concept diagram explaining the basics of {topic}",
            "keywords": [topic, "basics"],
            "audio_mood": "calm",
            "duration_hint": 20.0,
        },
        sequence_order=1,
        estimated_seconds=30,
    )
    interaction_node = LearningNode(
        course_id=course.id,
        node_type=NodeType.INTERACTION.value,
        content={
            "prompt": f"Quick check: which statement best matches the main idea of {topic}?",
            "interaction_type": "multiple_choice",
            "options": [
                {
                    "id": "a",
                    "label": "It’s a random fact with no structure.",
                    "is_correct": False,
                    "feedback": "Not quite—there’s a core principle behind it.",
                    "misconception_tag": "no_structure",
                },
                {
                    "id": "b",
                    "label": "It’s a structured concept that explains how something works.",
                    "is_correct": True,
                    "feedback": "Exactly—nice work.",
                    "misconception_tag": None,
                },
                {
                    "id": "c",
                    "label": "It only applies in one narrow edge case.",
                    "is_correct": False,
                    "feedback": "Usually it’s broader than that.",
                    "misconception_tag": "too_narrow",
                },
            ],
            "explanation": f"{topic} is best understood as a structured concept you can apply.",
            "visual_prompt": f"A simple quiz card about {topic}",
        },
        sequence_order=2,
        estimated_seconds=20,
    )
    summary_node = LearningNode(
        course_id=course.id,
        node_type=NodeType.SUMMARY.value,
        content={
            "narration": f"Great job. You learned the basics of {topic}. Next we can go deeper or practice.",
            "visual_prompt": f"A clean summary card with key points about {topic}",
            "keywords": [topic, "summary"],
            "audio_mood": "calm",
            "duration_hint": 10.0,
        },
        sequence_order=3,
        estimated_seconds=15,
    )

    db.add_all([hook_node, lesson_node, interaction_node, summary_node])
    await db.flush()

    course.entry_node_id = hook_node.id

    edges = [
        LearningEdge(
            course_id=course.id,
            from_node_id=hook_node.id,
            to_node_id=lesson_node.id,
            condition="always",
            weight=1.0,
        ),
        LearningEdge(
            course_id=course.id,
            from_node_id=lesson_node.id,
            to_node_id=interaction_node.id,
            condition="always",
            weight=1.0,
        ),
        LearningEdge(
            course_id=course.id,
            from_node_id=interaction_node.id,
            to_node_id=summary_node.id,
            condition="always",
            weight=1.0,
        ),
    ]
    db.add_all(edges)

    await db.commit()
    await db.refresh(course)
    return course

@router.get("/health")
async def classroom_health():
    """Check AI Classroom health"""
    intent_detector = get_intent_detector()
    conversation_manager = get_conversation_manager()
    
    return {
        "status": "healthy",
        "service": "ai_classroom",
        "components": {
            "intent_detector": "active",
            "conversation_manager": "active",
            "active_sessions": len(conversation_manager._sessions)
        }
    }


@router.post("/session", response_model=SessionResponse)
async def create_session(
    request: SessionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Create a new classroom session
    
    Returns a session_id to use for subsequent requests.
    Each session maintains conversation context.
    """
    manager = get_conversation_manager()
    session = manager.create_session(
        user_id=str(current_user.id),
        preferences=request.preferences
    )
    
    # Get the welcome message
    welcome_message = ""
    if session.messages:
        welcome_message = session.messages[0].content
    
    return SessionResponse(
        session_id=session.session_id,
        state=session.state.value,
        message_count=len(session.messages),
        current_topic=session.current_topic,
        welcome_message=welcome_message
    )


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """
    Get session information
    
    Returns current state, message count, and topic.
    """
    manager = get_conversation_manager()
    session = manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "message_count": len(session.messages),
        "current_topic": session.current_topic,
        "current_course_id": session.current_course_id,
        "preferences": session.preferences,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat()
    }


@router.delete("/session/{session_id}")
async def end_session(session_id: str):
    """
    End a classroom session
    
    Cleans up session resources.
    """
    manager = get_conversation_manager()
    success = manager.end_session(session_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"status": "ended", "session_id": session_id}


@router.post("/chat", response_model=ChatResponse)
async def classroom_chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
):
    """
    Main classroom chat endpoint
    
    Intelligently handles:
    - Quick explanations (instant response)
    - Deep dives (with images)
    - Course requests (triggers multi-agent generation)
    - Quizzes (interactive testing)
    
    Set stream=true for real-time streaming response.
    """
    # Trigger Soft Skills Analysis in Background (skip for guest users)
    if current_user.id != "guest_session" and isinstance(current_user.id, int):
        background_tasks.add_task(analyze_soft_skills_task, current_user.id, request.message)

    manager = get_conversation_manager()
    
    # Get or create session
    if request.session_id:
        session = manager.get_session(request.session_id)
        if not session:
            session = manager.create_session()
    else:
        session = manager.create_session()
    
    detector = get_intent_detector()
    detected_intent: Optional[ChatIntent] = None
    try:
        detected_intent = detector.detect(request.message)
    except Exception:
        logger.exception("Intent detection failed; falling back to keyword heuristic")

    message_lower = request.message.lower()
    is_course_request = (
        detector.should_trigger_course_generation(detected_intent)
        if detected_intent is not None
        else (("course" in message_lower) and ("create" in message_lower))
    )

    generated_course_id: Optional[str] = None
    
    # NEW: Handle Course Generation with Real Pipeline
    if is_course_request:
        try:
            logger.info(f"Triggering REAL course generation for: {request.message}")
            
            # 1. Determine Topic
            topic = (
                (detected_intent.topic if detected_intent is not None else None)
                or session.current_topic
                or ""
            )

            if not topic:
                match = re.search(r"['\"]([^'\"]{1,200})['\"]", request.message)
                topic = match.group(1) if match else request.message

            topic = topic.strip().strip("'\"")
            if len(topic) > 90:
                topic = topic[:87] + "..."
            
            # 2. Initialize Pipeline via Helper
            from lyo_app.ai_agents.multi_agent_v2.routes import get_pipeline
            from lyo_app.ai_classroom.graph_generator import GraphCourseGenerator, GraphGenerationConfig
            
            pipeline = get_pipeline()
            
            # 3. Define Context (Guest vs User)
            user_context_dict = {
                "source": "classroom_chat",
                "request_time": datetime.utcnow().isoformat()
            }
            creator_id = str(current_user.id)
            
            if creator_id != "guest_session":
                 user_context_dict["user_id"] = creator_id
            
            # 4. Run Generation (This usually takes 30-60s)
            # In a prod environment, we might push this to background & stream updates.
            # For now, we await it to block and return the full result.
            generated_course = await pipeline.generate_course(
                user_request=f"Create a course about {topic}",
                user_context=user_context_dict,
                job_id=f"chatgen_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{str(session.session_id)[:8]}"
            )
            
            # 5. Persist as Graph Course
            graph_generator = GraphCourseGenerator(
                config=GraphGenerationConfig(
                    add_hook_nodes=True,
                    add_interaction_checkpoints=True,
                    target_node_duration_minutes=1.5
                )
            )
            
            graph_course, result = await graph_generator.generate_graph_course(
                db=db,
                curriculum=generated_course.curriculum,
                lessons=generated_course.lessons,
                assessments=generated_course.assessments,
                creator_id=creator_id
            )
            
            generated_course_id = graph_course.id
            session.current_course_id = generated_course_id
            session.current_topic = topic

            # 6. Construct Response Payload
            payload = {
                "course": {
                    "id": graph_course.id,
                    "title": graph_course.title,
                    "topic": topic,
                    "level": graph_course.difficulty_level or "beginner"
                }
            }

            response = FlowResponse(
                content=f"✅ I've created a new interactive course for you: **{graph_course.title}**.\n\nIt includes {result.nodes_created} scenes and interactive quizzes. Ready to start?",
                response_type="OPEN_CLASSROOM",
                state=ConversationState.IN_LESSON,
                metadata={
                    "course_id": generated_course_id,
                    "generated_course_id": generated_course_id,
                    "topic": topic,
                    "openClassroomPayload": payload,
                    "nodes_created": result.nodes_created
                },
                actions=[
                    {
                        "type": "course_created",
                        "course_id": generated_course_id,
                        "topic": topic,
                    }
                ],
            )
        except Exception as e:
            logger.exception(f"Failed to create REAL graph course: {e}")
            # Fallback to chat response instead of 500
            response = FlowResponse(
                content=f"I tried to create a comprehensive course on '{topic}', but hit a snag during the deep research phase. Let's start simpler - check out this summary instead.",
                response_type="text",
                state=session.state,
                metadata={"error": str(e)}
            )
            
            # Minimal fallback if real generation fails
            try:
                fallback_course = await _create_minimal_graph_course(
                    db,
                    topic=topic,
                    creator_id=str(current_user.id),
                    level="beginner"
                )
                generated_course_id = fallback_course.id
                response.metadata["course_id"] = generated_course_id
                response.metadata["generated_course_id"] = generated_course_id
                response.response_type = "OPEN_CLASSROOM"
            except Exception:
                pass

    else:
        # Get User Context (skip for guest users)
        user_context = "student"  # Default context
        if current_user.id != "guest_session" and isinstance(current_user.id, int):
            try:
                user_context = await context_engine.get_user_context(
                    db, 
                    current_user.id, 
                    current_input=request.message
                )
            except Exception as e:
                logger.warning(f"Context engine failed for user {current_user.id}: {e}")
                user_context = "student"

        # Default AI classroom behavior
        response = await manager.process_message(
            session.session_id,
            request.message,
            include_audio=request.include_audio,
            user_context=user_context
        )

        # Best-effort compatibility: surface any course_id from response/session.
        generated_course_id = (
            getattr(session, "current_course_id", None)
            or response.metadata.get("course_id")
            or response.metadata.get("current_course_id")
        )
    
    # Get intent from latest message
    intent_dict = detected_intent.to_dict() if detected_intent is not None else None
    if intent_dict is None and session.messages:
        for msg in reversed(session.messages):
            if msg.role.value == "user" and msg.intent:
                intent_dict = msg.intent.to_dict()
                break
    
    return ChatResponse(
        session_id=session.session_id,
        content=response.content,
        response_type=response.response_type,
        state=response.state.value,
        generated_course_id=generated_course_id,
        intent=intent_dict,
        audio_url=response.audio_url,
        images=response.images,
        actions=response.actions,
        metadata=response.metadata,
        openClassroomPayload=response.metadata.get("openClassroomPayload")
    )


@router.get("/courses", response_model=List[GraphCourseItemRead])
async def list_graph_courses(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List graph courses created by the authenticated user."""
    result = await db.execute(
        select(GraphCourse)
        .where(GraphCourse.created_by == str(current_user.id))
        .order_by(GraphCourse.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    courses = result.scalars().all()

    items: List[GraphCourseItemRead] = []
    for course in courses:
        total_nodes = await _count_nodes(db, course.id)
        items.append(_course_to_item(course, total_nodes))
    return items


@router.get("/courses/{course_id}", response_model=GraphCourseItemRead)
async def get_graph_course(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific graph course by id (must belong to current user)."""
    result = await db.execute(
        select(GraphCourse).where(
            GraphCourse.id == course_id,
            GraphCourse.created_by == str(current_user.id),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    total_nodes = await _count_nodes(db, course.id)
    return _course_to_item(course, total_nodes)


@router.post("/chat/stream")
async def classroom_chat_stream(request: ChatRequest):
    """
    Streaming classroom chat
    
    Returns Server-Sent Events for real-time experience.
    Each event contains part of the response.
    
    Event types:
    - intent_detected: User intent analysis
    - typing: Typing indicator
    - content: Response content (word by word)
    - complete: Full response
    """
    manager = get_conversation_manager()
    sse_manager = get_sse_manager()
    
    # Get or create session
    session_id = request.session_id
    if session_id:
        session = manager.get_session(session_id)
        if not session:
            session = manager.create_session()
            session_id = session.session_id
    else:
        session = manager.create_session()
        session_id = session.session_id
    
    async def generate_events():
        async for event in manager.stream_response(session_id, request.message):
            yield StreamEvent(
                event=EventType.MESSAGE_DELTA if event["event"] == "content" else EventType.MESSAGE_START,
                data=event["data"]
            ).to_sse()
            
        yield StreamEvent(event=EventType.DONE, data={"session_id": session_id}).to_sse()
    
    return stream_response(generate_events())


@router.post("/analyze-intent", response_model=IntentAnalysisResponse)
async def analyze_intent(request: IntentAnalysisRequest):
    """
    Analyze intent without generating a response
    
    Useful for previewing how a message will be handled,
    or for debugging intent detection.
    """
    detector = get_intent_detector()
    intent = detector.detect(request.message)
    strategy = detector.get_response_strategy(intent)
    
    return IntentAnalysisResponse(
        intent_type=intent.intent_type.value,
        confidence=intent.confidence,
        confidence_level=intent.confidence_level.value,
        topic=intent.topic,
        complexity_hint=intent.complexity_hint,
        requires_generation=intent.requires_generation,
        suggested_response_type=intent.suggested_response_type,
        reasoning=intent.reasoning,
        strategy=strategy
    )


@router.get("/session/{session_id}/history")
async def get_conversation_history(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200)
):
    """
    Get conversation history for a session
    
    Returns messages with their intents and metadata.
    """
    manager = get_conversation_manager()
    session = manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = [m.to_dict() for m in session.messages[-limit:]]
    
    return {
        "session_id": session_id,
        "message_count": len(session.messages),
        "messages": messages
    }


@router.post("/session/{session_id}/continue")
async def continue_learning(session_id: str):
    """
    Continue with next content in the session
    
    Moves to next lesson, quiz question, or content section.
    """
    manager = get_conversation_manager()
    session = manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Process a "continue" message
    response = await manager.process_message(session_id, "continue")
    
    return ChatResponse(
        session_id=session_id,
        content=response.content,
        response_type=response.response_type,
        state=response.state.value,
        actions=response.actions,
        metadata=response.metadata
    )


@router.get("/suggestions")
async def get_learning_suggestions(
    topic: Optional[str] = Query(default=None, description="Current topic for context")
):
    """
    Get suggested learning paths and questions
    
    Returns conversation starters and learning suggestions.
    """
    suggestions = {
        "quick_questions": [
            "What is machine learning?",
            "Explain Python decorators",
            "How does the internet work?",
        ],
        "course_requests": [
            "Create a course on Python for beginners",
            "Teach me JavaScript from scratch",
            "I want to learn data science comprehensively",
        ],
        "practice": [
            "Quiz me on Python basics",
            "Give me coding challenges",
            "Test my knowledge of algorithms",
        ]
    }
    
    if topic:
        suggestions["topic_specific"] = [
            f"Explain {topic} in detail",
            f"Create a course on {topic}",
            f"Quiz me on {topic}",
            f"What are the key concepts in {topic}?",
        ]
    
    return suggestions


@router.get("/capabilities")
async def get_classroom_capabilities():
    """
    Get AI Classroom capabilities
    
    Returns information about what the classroom can do.
    """
    return {
        "features": {
            "chat": {
                "description": "Intelligent conversational learning",
                "intents_supported": [
                    "quick_explanation",
                    "definition", 
                    "deep_dive",
                    "learn_topic",
                    "full_course",
                    "tutorial",
                    "quiz_request",
                    "practice"
                ]
            },
            "course_generation": {
                "description": "Multi-agent full course creation",
                "includes": ["curriculum", "lessons", "quizzes", "images", "audio"]
            },
            "tts": {
                "description": "Text-to-speech with premium voices",
                "voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
            },
            "images": {
                "description": "Educational diagram generation",
                "types": ["concept_diagram", "process_flow", "mind_map", "timeline", "infographic"]
            },
            "streaming": {
                "description": "Real-time response streaming",
                "protocol": "Server-Sent Events (SSE)"
            }
        },
        "tips": [
            "Say 'create a course on X' for comprehensive learning",
            "Ask 'what is X?' for quick explanations",
            "Request 'quiz me on X' to test your knowledge",
            "Use 'explain X in detail' for deep dives with visuals"
        ]
    }
