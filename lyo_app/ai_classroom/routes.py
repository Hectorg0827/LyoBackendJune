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
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .intent_detector import get_intent_detector, ChatIntent
from .conversation_flow import (
    get_conversation_manager,
    ConversationManager,
    FlowResponse,
    ConversationState
)
from lyo_app.streaming import get_sse_manager, stream_response, EventType, StreamEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/classroom", tags=["AI Classroom"])


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
    intent: Optional[Dict[str, Any]] = None
    audio_url: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
async def create_session(request: SessionRequest):
    """
    Create a new classroom session
    
    Returns a session_id to use for subsequent requests.
    Each session maintains conversation context.
    """
    manager = get_conversation_manager()
    session = manager.create_session(
        user_id=request.user_id,
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
async def classroom_chat(request: ChatRequest):
    """
    Main classroom chat endpoint
    
    Intelligently handles:
    - Quick explanations (instant response)
    - Deep dives (with images)
    - Course requests (triggers generation)
    - Quizzes (interactive testing)
    
    Set stream=true for real-time streaming response.
    """
    manager = get_conversation_manager()
    
    # Get or create session
    if request.session_id:
        session = manager.get_session(request.session_id)
        if not session:
            session = manager.create_session()
    else:
        session = manager.create_session()
    
    # Process message
    response = await manager.process_message(
        session.session_id,
        request.message,
        include_audio=request.include_audio
    )
    
    # Get intent from latest message
    intent_dict = None
    if session.messages:
        last_user_msg = None
        for msg in reversed(session.messages):
            if msg.role.value == "user" and msg.intent:
                intent_dict = msg.intent.to_dict()
                break
    
    return ChatResponse(
        session_id=session.session_id,
        content=response.content,
        response_type=response.response_type,
        state=response.state.value,
        intent=intent_dict,
        audio_url=response.audio_url,
        images=response.images,
        actions=response.actions,
        metadata=response.metadata
    )


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
