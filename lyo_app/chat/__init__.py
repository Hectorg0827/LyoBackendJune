"""
Chat Module

Intelligent chat system with:
- Mode-based routing (Quick Explainer, Course Planner, Practice, Note Taker)
- Agent architecture for specialized responses
- CTA de-duplication and length enforcement
- Response caching
- Telemetry tracking

Usage:
    from lyo_app.chat import chat_router
    app.include_router(chat_router, prefix="/api/v1")
"""

from lyo_app.chat.routes import router as chat_router
from lyo_app.chat.models import (
    ChatMode, ChipAction, CTAType,
    ChatCourse, ChatNote, ChatConversation, ChatMessage, ChatTelemetry
)
from lyo_app.chat.schemas import (
    ChatRequest, ChatResponse,
    QuickExplainerRequest, QuickExplainerResponse,
    CoursePlannerRequest, CoursePlannerResponse,
    PracticeRequest, PracticeResponse,
    NoteRequest, NoteResponse,
    TelemetryStatsResponse
)
from lyo_app.chat.router import chat_router as message_router
from lyo_app.chat.agents import agent_registry
from lyo_app.chat.assembler import response_assembler
from lyo_app.chat.stores import (
    course_store, notes_store, conversation_store,
    response_cache, telemetry_store, initialize_stores
)

__all__ = [
    # Router
    "chat_router",
    
    # Models
    "ChatMode",
    "ChipAction",
    "CTAType",
    "ChatCourse",
    "ChatNote",
    "ChatConversation",
    "ChatMessage",
    "ChatTelemetry",
    
    # Schemas
    "ChatRequest",
    "ChatResponse",
    "QuickExplainerRequest",
    "QuickExplainerResponse",
    "CoursePlannerRequest",
    "CoursePlannerResponse",
    "PracticeRequest",
    "PracticeResponse",
    "NoteRequest",
    "NoteResponse",
    "TelemetryStatsResponse",
    
    # Internal components
    "message_router",
    "agent_registry",
    "response_assembler",
    
    # Stores
    "course_store",
    "notes_store",
    "conversation_store",
    "response_cache",
    "telemetry_store",
    "initialize_stores",
]
