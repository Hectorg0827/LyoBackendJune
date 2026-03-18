"""
Chat Module Routes

FastAPI routes for the chat module including:
- Main /chat endpoint with mode_hint and action support
- Streaming /chat/stream endpoint for real-time responses
- Quick Explainer endpoint
- Course Planner endpoint
- Practice endpoint
- Note endpoints
- Telemetry endpoints
- A2A (Agent-to-Agent) endpoints
"""

import asyncio
import json
import re
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.jwt_auth import get_optional_current_user
from lyo_app.models.enhanced import User
from lyo_app.chat.models import ChatMode, ChatMessage, ChatConversation
from lyo_app.chat.schemas import (
    ChatRequest, ChatResponse, ConversationHistoryItem,
    QuickExplainerRequest, QuickExplainerResponse,
    CoursePlannerRequest, CoursePlannerResponse,
    PracticeRequest, PracticeResponse,
    NoteRequest, NoteResponse,
    CTAClickRequest, CTAItem, ChipActionItem,
    TelemetryStatsResponse,
    ChatCourseRead, ChatCourseCreate,
    ChatNoteRead, ChatNoteCreate, ChatNoteUpdate,
    GreetingResponse,
    OpenClassroomCourse, OpenClassroomPayload,
    # Selection / highlight / notes-popup schemas
    SelectionExplainRequest, SelectionExplainResponse,
    SelectionNoteRequest, SelectionNoteResponse,
    HighlightCreate, HighlightRead, HighlightListResponse,
    AnnotationUpdate,
)
from lyo_app.core.lyo_protocol import (
    LyoBlock, BlockType, SemanticRole, PresentationHint, ConceptPayload
)
from lyo_app.chat.router import chat_router, mode_transition_manager
from lyo_app.chat.agents import agent_registry
from lyo_app.chat.assembler import response_assembler
from lyo_app.chat.stores import (
    course_store, notes_store, conversation_store,
    highlight_store, response_cache, telemetry_store
)
from lyo_app.streaming import get_sse_manager, stream_response, EventType, StreamEvent
from lyo_app.personalization.service import personalization_engine
from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.core.context_engine import context_engine
from lyo_app.core.personality import LYO_SYSTEM_PROMPT

# A2A Imports
from lyo_app.ai_agents.a2a.schemas import (
    A2ACourseRequest, A2ACourseResponse,
    StreamingEvent as A2AStreamingEvent
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


# =============================================================================
# PROACTIVE GREETING ENDPOINT
# =============================================================================

@router.get("/greeting", response_model=GreetingResponse)
async def get_proactive_greeting(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Generate a proactive, personalized greeting for the user.
    Uses the 'Smart Memory' context if available.
    """
    # 1. Build context
    learner_context = ""
    user_context_tag = "student" # Default
    
    if current_user:
        try:
            # Get Context Tag (Student vs Professional)
            user_context_tag = await context_engine.get_user_context(db, current_user.id)
            
            # Get Detailed Learning Context
            # TEMPORARILY DISABLED due to greenlet issues
            learner_context = ""  # await personalization_engine.build_prompt_context(db, str(current_user.id))
        except Exception as e:
            await db.rollback()
            logger.warning(f"Failed to build context for greeting: {e}")

    # 2. Construct prompt
    system_prompt = LYO_SYSTEM_PROMPT + """
    
---
**GREETING SPECIFIC INSTRUCTIONS:**
Your goal is to welcome the user back. 
Keep it short (max 2 sentences). 
Be warm and proactive. 
Adapt your tone for a {user_context_tag} audience. 
If context is provided, use it to make the greeting specific (e.g., mentioning a recent topic or struggle), 
but do not be creepy or over-specific. Just a gentle nod to their journey.
"""
    
    user_message = "Hi Lyo!"
    if learner_context:
        user_message += f"\n\n[Context]:\n{learner_context}"

    # 3. Call AI (Fast model)
    try:
        response = await ai_resilience_manager.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=100,
            provider_order=["gemini-3.1-pro-preview-customtools", "gpt-4o-mini", "gemini-3.1-pro-preview-customtools"] # Prefer fast model
        )
        greeting_text = response.get("content", "Welcome back! Ready to learn something new?")
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting_text = "Welcome back! Ready to learn something new?"

    # Build context-aware suggestions
    if learner_context:
        suggestions = ["Continue where I left off", "Review my struggles", "Create a course"]
    else:
        suggestions = ["Teach me something new", "Create a course", "Quiz me on a topic"]

    return GreetingResponse(
        greeting=greeting_text,
        context_used=bool(learner_context),
        suggestions=suggestions
    )


# =============================================================================
# MAIN CHAT ENDPOINT
# =============================================================================

@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Main chat endpoint with mode_hint and action support.
    
    This endpoint routes messages to the appropriate agent based on:
    1. Explicit action (chip clicks)
    2. Mode hint from client
    3. Message content analysis
    4. Conversation context
    
    Returns a response with optional CTAs and chip actions.
    """
    start_time = time.time()
    
    try:
        # 1. Get or create conversation
        session_id = request.session_id or str(uuid4())
        conversation_id = request.conversation_id
        
        if conversation_id:
            conversation = await conversation_store.get_conversation(db, conversation_id)
        else:
            conversation = await conversation_store.get_active_conversation(
                db, session_id, user_id=str(current_user.id) if current_user else None
            )
        
        if not conversation:
            conversation = await conversation_store.create_conversation(
                db, session_id,
                user_id=str(current_user.id) if current_user else None,
                initial_mode=request.mode_hint or ChatMode.GENERAL.value
            )

        # Capture essential data EARLY before any commit/rollback expires the object
        active_conversation_id = conversation.id
        active_conversation_topic = conversation.topic

        # Best-effort backfill user binding for continuity
        if current_user and not conversation.user_id:
            try:
                conversation.user_id = str(current_user.id)
                await db.commit()
            except Exception:
                await db.rollback()

        # Best-effort topic assignment (does not change client contract)
        if request.context and not active_conversation_topic:
            try:
                conversation.topic = request.context[:200]
                active_conversation_topic = conversation.topic
                await db.commit()
            except Exception:
                await db.rollback()
        
        # 2. Build Context & History EARLY (for Router)
        history = []
        if request.conversation_history:
            for msg in request.conversation_history:
                history.append({"role": msg.role, "content": msg.content})

        context = {
            "context": request.context,
            "conversation_id": active_conversation_id,
            "resource_id": request.resource_id,
            "course_id": request.course_id,
            "note_id": request.note_id,
        }

        # Optional learner context (authenticated users only)
        # TEMPORARILY DISABLED due to greenlet/SQLAlchemy async issues
        # TODO: Re-enable once personalization service is fixed
        if current_user and False:  # Disabled for now
            try:
                learner_context = await personalization_engine.build_prompt_context(
                    db,
                    learner_id=str(current_user.id),
                    current_skill=None
                )
                if learner_context:
                    context["learner_context"] = learner_context
                    context["learner_id"] = str(current_user.id)
            except Exception as e:
                # Defensive rollback and continue without personalization
                try:
                    await db.rollback()
                except Exception:
                    pass
                logger.warning(f"Personalization context unavailable: {e}")
                
        # 3. Route the message (Now with full context)
        mode, confidence, reasoning = await chat_router.route(
            message=request.message,
            mode_hint=request.mode_hint,
            action=request.action,
            context=context,
            conversation_history=history
        )
        
        logger.info(f"Routed to {mode.value} with confidence {confidence}: {reasoning}")
        
        # 5. Check cache for similar requests
        cache_hit = False
        cached_response = None
        
        if response_cache:
            cached_response = await response_cache.get(
                request.message, mode.value
            )
            if cached_response:
                cache_hit = True
                logger.info("Cache hit for message")
        
        # 6. Process with agent
        if cached_response:
            agent_result = cached_response
        else:
            agent_result = await agent_registry.process(
                mode=mode,
                message=request.message,
                context=context,
                conversation_history=history
            )
            
            # Cache the response
            if response_cache and agent_result.get("response"):
                await response_cache.set(
                    request.message, mode.value, agent_result
                )
        
        # FORCE ROLLBACK to clear any stealth failed transaction states
        # (e.g., from personalization pgvector queries or cache logic)
        try:
            await db.rollback()
        except Exception:
            pass

        # 7. Get recent CTAs for deduplication (defensive: retry after rollback)
        recent_messages = []
        try:
            recent_messages = await conversation_store.get_messages(
                db, active_conversation_id, limit=5
            )
        except Exception as msg_err:
            logger.warning(f"get_messages failed ({msg_err}), retrying after rollback")
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                recent_messages = await conversation_store.get_messages(
                    db, active_conversation_id, limit=5
                )
            except Exception:
                logger.warning("get_messages retry also failed, skipping CTA dedup")
                try:
                    await db.rollback()
                except Exception:
                    pass
        recent_ctas = [msg.ctas or [] for msg in recent_messages]
        
        # 8. Assemble final response
        assembled = response_assembler.assemble(
            response=agent_result.get("response", ""),
            mode=mode,
            ctas=agent_result.get("ctas"),
            chips=agent_result.get("chips"),
            context=context,
            recent_ctas=recent_ctas,
            max_length=request.max_tokens * 4 if request.max_tokens else None,
            include_ctas=request.include_ctas,
            include_chips=request.include_chips
        )
        
        # 9. Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 10. Save messages and telemetry in parallel (batch writes for ~10-20ms savings)
        message_id = str(uuid4())
        
        async def save_user_message():
            return await conversation_store.add_message(
                db, active_conversation_id,
                role="user",
                content=request.message,
                mode_used=mode.value
            )
        
        async def save_assistant_message():
            return await conversation_store.add_message(
                db, active_conversation_id,
                role="assistant",
                content=assembled["response"],
                mode_used=mode.value,
                action_triggered=request.action,
                tokens_used=agent_result.get("tokens_used"),
                model_used=agent_result.get("model_used"),
                latency_ms=latency_ms,
                ctas=[cta.model_dump() for cta in assembled["ctas"]],
                chip_actions=[chip.model_dump() for chip in assembled["chip_actions"]],
                cache_hit=cache_hit
            )
        
        # Captured ID is used for saves to avoid greenlet errors on expired objects

        # Execute saves sequentially to avoid SQLAlchemy session conflicts
        # (asyncio.gather with shared db session causes IllegalStateChangeError)
        try:
            await save_user_message()
            assistant_message = await save_assistant_message()
        except Exception as save_err:
            logger.warning(f"Message save failed ({save_err}), retrying after rollback")
            try:
                await db.rollback()
            except Exception:
                pass
            await save_user_message()
            assistant_message = await save_assistant_message()
        
        # 11. Record telemetry (await to avoid "transaction closed" errors)
        # Note: fire-and-forget with asyncio.create_task + db session causes errors
        # because FastAPI closes the session before the task completes
        try:
            await telemetry_store.record(
                db,
                event_type="chat_response",
                session_id=session_id,
                conversation_id=active_conversation_id,
                message_id=assistant_message.id,
                mode_chosen=mode.value,
                tokens_used=agent_result.get("tokens_used"),
                cache_hit=cache_hit,
                latency_ms=latency_ms,
                metadata={
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "action": request.action
                }
            )
        except Exception as tele_err:
            logger.warning(f"Telemetry recording failed (non-critical): {tele_err}")
        
        # 12. Build updated history
        updated_history = []
        if request.conversation_history:
            for msg in request.conversation_history:
                updated_history.append(ConversationHistoryItem(
                    role=msg.role, content=msg.content
                ))
        updated_history.append(ConversationHistoryItem(
            role="user", content=request.message
        ))
        updated_history.append(ConversationHistoryItem(
            role="assistant", content=assembled["response"]
        ))
        
        # 13. Check for generated content IDs
        generated_course_id = agent_result.get("course_id")
        generated_note_id = agent_result.get("note_id")
        
        # If course was generated, save it
        if mode == ChatMode.COURSE_PLANNER and agent_result.get("course_data"):
            course_data = agent_result["course_data"]
            saved_course = await course_store.create(
                db,
                user_id=None,  # Public chat, no user
                title=course_data.get("title", "Generated Course"),
                topic=request.message,
                description=course_data.get("description"),
                modules=course_data.get("modules"),
                difficulty=course_data.get("difficulty", "intermediate"),
                estimated_hours=course_data.get("estimated_hours"),
                learning_objectives=course_data.get("learning_objectives"),
                source_conversation_id=active_conversation_id
            )
            generated_course_id = saved_course.id
        
        # 14. Build iOS-compatible embedded payloads
        quick_explainer_data = None
        course_proposal_data = None
        content_types = []
        
        if mode == ChatMode.QUICK_EXPLAINER:
            # Extract key points from response (simple heuristic)
            key_points = []
            if "•" in assembled["response"]:
                key_points = [
                    line.strip().lstrip("•").strip() 
                    for line in assembled["response"].split("\n") 
                    if line.strip().startswith("•")
                ][:5]
            quick_explainer_data = {
                "explanation": assembled["response"],
                "key_points": key_points or agent_result.get("key_points", []),
                "related_topics": agent_result.get("related_topics", [])
            }
            content_types.append({
                "type": "quick_explainer",
                "id": str(uuid4()),
                "data": quick_explainer_data
            })
        
        # OPEN_CLASSROOM variables
        open_classroom_type = None
        open_classroom_payload = None
        
        if mode == ChatMode.COURSE_PLANNER and agent_result.get("course_data"):
            course_data = agent_result["course_data"]
            course_proposal_data = {
                "course_id": generated_course_id or str(uuid4()),
                "title": course_data.get("title", "Generated Course"),
                "description": course_data.get("description", ""),
                "estimated_hours": course_data.get("estimated_hours", 1.0),
                "module_count": len(course_data.get("modules", [])),
                "learning_objectives": course_data.get("learning_objectives", [])
            }
            content_types.append({
                "type": "course_proposal",
                "id": course_proposal_data["course_id"],
                "data": course_proposal_data
            })
            
            # Build OPEN_CLASSROOM payload for iOS
            open_classroom_type = "OPEN_CLASSROOM"
            open_classroom_payload = OpenClassroomPayload(
                course=OpenClassroomCourse(
                    id=generated_course_id or str(uuid4()),
                    title=course_data.get("title", "Generated Course"),
                    topic=request.message,  # Use original message as topic
                    level=course_data.get("difficulty", "intermediate"),
                    duration=f"~{int(course_data.get('estimated_hours', 1) * 60)} min",
                    objectives=course_data.get("learning_objectives", [])
                )
            )

        # Test Prep Logic
        study_plan_data = None
        if mode == ChatMode.TEST_PREP and agent_result.get("study_plan"):
             study_plan_data = agent_result["study_plan"]
             content_types.append({
                 "type": "study_plan",
                 "id": study_plan_data.get("plan_id", str(uuid4())),
                 "data": study_plan_data
             })

        response_obj = ChatResponse(
            response=assembled["response"],
            message_id=assistant_message.id,
            conversation_id=active_conversation_id,
            mode_used=mode.value,
            mode_confidence=confidence,
            quick_explainer=quick_explainer_data,
            course_proposal=course_proposal_data,
            study_plan=study_plan_data,
            content_types=content_types,
            ui_component=None,
            type=open_classroom_type,
            payload=open_classroom_payload,
            conversation_history=updated_history,
            ctas=assembled["ctas"],
            chip_actions=assembled["chip_actions"],
            tokens_used=agent_result.get("tokens_used"),
            cache_hit=cache_hit,
            latency_ms=latency_ms,
            generated_course_id=generated_course_id,
            generated_note_id=generated_note_id,
            lyo_blocks=agent_result.get("lyo_blocks") or ([
                LyoBlock(
                    id=str(uuid4()),
                    type=BlockType.CONCEPT,
                    role=SemanticRole.NORMAL,
                    content=ConceptPayload(markdown=assembled["response"]),
                    presentation_hint=PresentationHint.INLINE
                )
            ] if assembled["response"] else [])
        )

        return response_obj
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing failed: {str(e)}"
        )


# =============================================================================
# STREAMING CHAT ENDPOINT
# =============================================================================

@router.post("/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Streaming chat endpoint for real-time responses.
    
    Returns Server-Sent Events (SSE) for a ChatGPT-like typing experience.
    ~70% reduction in perceived latency by showing tokens as they arrive.
    
    Event types:
    - message_start: Response generation started
    - message_delta: Partial content chunk
    - message_complete: Full response with metadata
    - done: Stream complete
    """
    sse_manager = get_sse_manager()
    
    async def generate_stream() -> AsyncGenerator[str, None]:
        start_time = time.time()
        session_id = request.session_id or str(uuid4())
        
        try:
            # 1. Get or create conversation
            conversation_id = request.conversation_id
            if conversation_id:
                conversation = await conversation_store.get_conversation(db, conversation_id)
            else:
                conversation = await conversation_store.get_active_conversation(
                    db, session_id, user_id=str(current_user.id) if current_user else None
                )
            
            if not conversation:
                conversation = await conversation_store.create_conversation(
                    db, session_id,
                    user_id=str(current_user.id) if current_user else None,
                    initial_mode=request.mode_hint or ChatMode.GENERAL.value
                )

            # Capture essential data EARLY
            active_conversation_id = conversation.id

            # Best-effort backfill user binding for continuity
            if current_user and not conversation.user_id:
                try:
                    conversation.user_id = str(current_user.id)
                    await db.commit()
                except Exception:
                    await db.rollback()

            # Best-effort topic assignment
            if request.context and not conversation.topic:
                try:
                    conversation.topic = request.context[:200]
                    await db.commit()
                except Exception:
                    await db.rollback()
            
            # Refresh ID just in case commit/rollback happened
            active_conversation_id = conversation.id
            
            # 2. Build Context & History EARLY (for Router)
            history = []
            if request.conversation_history:
                for msg in request.conversation_history:
                    history.append({"role": msg.role, "content": msg.content})

            context = {
                "context": request.context,
                "conversation_id": active_conversation_id,
                "resource_id": request.resource_id,
                "course_id": request.course_id,
                "note_id": request.note_id,
            }

            # Optional learner context (authenticated users only)
            # TEMPORARILY DISABLED due to greenlet/SQLAlchemy async issues
            if current_user and False:  # Disabled for now
                try:
                    learner_context = await personalization_engine.build_prompt_context(
                        db,
                        learner_id=str(current_user.id),
                        current_skill=None
                    )
                    if learner_context:
                        context["learner_context"] = learner_context
                        context["learner_id"] = str(current_user.id)
                except Exception as e:
                    # Defensive rollback and continue without personalization
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    logger.warning(f"Personalization context unavailable: {e}")
            
            # 3. Route the message
            mode, confidence, reasoning = await chat_router.route(
                message=request.message,
                mode_hint=request.mode_hint,
                action=request.action,
                context=context,
                conversation_history=history
            )
            
            # 4. Send start event
            yield StreamEvent(
                event=EventType.MESSAGE_START,
                data={
                    "session_id": session_id,
                    "conversation_id": active_conversation_id,
                    "mode": mode.value,
                    "confidence": confidence,
                    "timestamp": time.time()
                }
            ).to_sse()
            
            # 5. Check cache first
            cache_hit = False
            cached_response = None
            
            if response_cache:
                cached_response = await response_cache.get(request.message, mode.value)
                if cached_response:
                    cache_hit = True
            
            # 6. Get or generate response
            if cached_response:
                agent_result = cached_response
                full_response = agent_result.get("response", "")
                
                # Stream cached response word by word for consistent UX
                words = full_response.split(" ")
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    yield StreamEvent(
                        event=EventType.MESSAGE_DELTA,
                        data={"content": chunk, "chunk_index": i + 1}
                    ).to_sse()
                    await asyncio.sleep(0.02)  # Natural typing feel
            else:
                # Process with agent
                agent_result = await agent_registry.process(
                    mode=mode,
                    message=request.message,
                    context=context,
                    conversation_history=history
                )
                
                full_response = agent_result.get("response", "")
                
                # Stream response word by word
                words = full_response.split(" ")
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    yield StreamEvent(
                        event=EventType.MESSAGE_DELTA,
                        data={"content": chunk, "chunk_index": i + 1}
                    ).to_sse()
                    await asyncio.sleep(0.02)
                
                # Cache the response
                if response_cache and full_response:
                    await response_cache.set(request.message, mode.value, agent_result)
            
            # 7. Assemble final response
            assembled = response_assembler.assemble(
                response=full_response,
                mode=mode,
                ctas=agent_result.get("ctas"),
                chips=agent_result.get("chips"),
                context=context,
                max_length=request.max_tokens * 4 if request.max_tokens else None,
                include_ctas=request.include_ctas,
                include_chips=request.include_chips
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # 8. Save messages in background (don't block stream completion)
            asyncio.create_task(_save_stream_messages(
                db, active_conversation_id, session_id, mode.value, request, assembled,
                agent_result, cache_hit, latency_ms, confidence, reasoning
            ))
            
            # 9. Send completion event
            yield StreamEvent(
                event=EventType.MESSAGE_COMPLETE,
                data={
                    "full_content": assembled["response"],
                    "mode_used": mode.value,
                    "ctas": [cta.model_dump() for cta in assembled["ctas"]],
                    "chip_actions": [chip.model_dump() for chip in assembled["chip_actions"]],
                    "cache_hit": cache_hit,
                    "latency_ms": latency_ms,
                    "tokens_used": agent_result.get("tokens_used"),
                    "timestamp": time.time()
                }
            ).to_sse()
            
            yield StreamEvent(event=EventType.DONE, data={}).to_sse()
            
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield StreamEvent(
                event=EventType.ERROR,
                data={"error": str(e)}
            ).to_sse()
    
    return stream_response(generate_stream())


async def _save_stream_messages(
    db: AsyncSession,
    conversation_id: str,
    session_id: str,
    mode_value: str,
    request: ChatRequest,
    assembled: Dict[str, Any],
    agent_result: Dict[str, Any],
    cache_hit: bool,
    latency_ms: int,
    confidence: float,
    reasoning: str
):
    """Background task to save stream messages and telemetry."""
    try:
        async def save_user():
            return await conversation_store.add_message(
                db, conversation_id,
                role="user",
                content=request.message,
                mode_used=mode_value
            )
        
        async def save_assistant():
            return await conversation_store.add_message(
                db, conversation_id,
                role="assistant",
                content=assembled["response"],
                mode_used=mode_value,
                action_triggered=request.action,
                tokens_used=agent_result.get("tokens_used"),
                model_used=agent_result.get("model_used"),
                latency_ms=latency_ms,
                ctas=[cta.model_dump() for cta in assembled["ctas"]],
                chip_actions=[chip.model_dump() for chip in assembled["chip_actions"]],
                cache_hit=cache_hit
            )
        
        # Run sequentially to avoid SQLAlchemy session conflicts  
        await save_user()
        assistant_message = await save_assistant()
        
        await telemetry_store.record(
            db,
            event_type="chat_stream_response",
            session_id=session_id,
            conversation_id=conversation_id,
            message_id=assistant_message.id,
            mode_chosen=mode_value,
            tokens_used=agent_result.get("tokens_used"),
            cache_hit=cache_hit,
            latency_ms=latency_ms,
            metadata={
                "confidence": confidence,
                "reasoning": reasoning,
                "action": request.action,
                "streaming": True
            }
        )
    except Exception as e:
        logger.error(f"Failed to save stream messages: {e}")



# =============================================================================
# A2A ENDPOINTS
# =============================================================================

@router.post("/a2a/generate", response_model=A2ACourseResponse)
async def generate_a2a_course(
    request: A2ACourseRequest,
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Generate a complete course using the A2A multi-agent pipeline (Synchronous).
    """
    try:
        from lyo_app.ai_agents.a2a import get_orchestrator
        orchestrator = get_orchestrator()
        
        # Inject user context if authenticated
        if current_user and not request.user_context:
            request.user_context = {
                "user_id": str(current_user.id),
                "level": "intermediate" # Could fetch from profile
            }
            
        return await asyncio.wait_for(
            orchestrator.generate_course(request),
            timeout=180.0
        )
    except asyncio.TimeoutError:
        logger.error("A2A course generation timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Course generation timed out"
        )
    except Exception as e:
        logger.error(f"A2A generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/a2a/stream")
async def stream_a2a_course(
    request: A2ACourseRequest,
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Generate a course using A2A with streaming updates (SSE).
    """
    from lyo_app.ai_agents.a2a import get_orchestrator
    orchestrator = get_orchestrator()
    
    # Inject user context if authenticated
    if current_user and not request.user_context:
        request.user_context = {
            "user_id": str(current_user.id),
            "level": "intermediate"
        }

    async def generate_events() -> AsyncGenerator[str, None]:
        try:
            async for event in orchestrator.generate_course_streaming(request):
                yield event.to_sse()
        except Exception as e:
            logger.error(f"A2A stream failed: {e}", exc_info=True)
            yield A2AStreamingEvent(
                type=EventType.ERROR,
                task_id="unknown",
                agent_name="orchestrator",
                data={"error": str(e)},
                message="Stream failed"
            ).to_sse()

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream"
    )

@router.get("/a2a/status/{task_id}")
async def get_a2a_task_status(task_id: str):
    """
    Get status of an A2A generation task.
    """
    from lyo_app.ai_agents.a2a import get_orchestrator
    orchestrator = get_orchestrator()
    state = orchestrator.get_pipeline_state()
    
    if state and state.pipeline_id == task_id:
        return {
            "task_id": state.pipeline_id,
            "status": state.final_status if state.final_status else "in_progress",
            "progress_percent": int(state.overall_progress * 100),
            "current_stage": state.current_phase.value if state.current_phase else None,
            "error": None # Simplified for now
        }
    
    raise HTTPException(status_code=404, detail="Task not found or expired")

@router.get("/a2a/result/{task_id}")
async def get_a2a_task_result(task_id: str):
    """
    Get final result of an A2A generation task.
    Returns format compatible with APICourseResult.
    """
    from lyo_app.ai_agents.a2a import get_orchestrator
    orchestrator = get_orchestrator()
    state = orchestrator.get_pipeline_state()
    
    if state and state.pipeline_id == task_id:
        # Check if finalized
        output = state.final_output
        if not output:
             raise HTTPException(status_code=400, detail="Result not ready")
             
        # Extract course data from assembly artifact
        # Note: The structure depends on what _assemble returns in orchestrator.py
        # It returns {"artifacts": {...}, "course_id": ...}
        
        # Simplified return for iOS compatibility
        return {
            "course_id": output.get("course_id", task_id),
            "title": output.get("title", f"Course on {state.request.topic}"),
            "description": output.get("description", "A2A Generated Course"),
            "modules": [], # TODO: Extract real modules from artifacts
            "estimated_duration": 45,
            "difficulty": state.request.difficulty
        }
        
    raise HTTPException(status_code=404, detail="Result not found or expired")

@router.post("/explain", response_model=QuickExplainerResponse)
async def quick_explain_endpoint(
    request: QuickExplainerRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Quick explanation endpoint for simple topic explanations.
    """
    try:
        context = {
            "depth": request.depth,
            "context": request.context
        }
        
        history = []
        if request.conversation_history:
            for msg in request.conversation_history:
                history.append({"role": msg.role, "content": msg.content})
        
        result = await agent_registry.process(
            mode=ChatMode.QUICK_EXPLAINER,
            message=request.topic,
            context=context,
            conversation_history=history
        )
        
        return QuickExplainerResponse(
            explanation=result.get("response", ""),
            key_points=result.get("key_points", []),
            related_topics=result.get("related_topics", [])
        )
    except Exception as e:
        logger.error(f"Explanation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate explanation"
        )





# =============================================================================
# COURSE PLANNER ENDPOINT
# =============================================================================

@router.post("/plan-course", response_model=CoursePlannerResponse)
async def plan_course_endpoint(
    request: CoursePlannerRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Course planning endpoint for creating structured learning paths.
    """
    try:
        context = {
            "goal": request.goal,
            "time_available": request.time_available,
            "current_level": request.current_level,
            "preferences": request.preferences
        }
        
        result = await agent_registry.process(
            mode=ChatMode.COURSE_PLANNER,
            message=request.topic,
            context=context
        )
        
        course_data = result.get("course_data", {})
        course_id = result.get("course_id", str(uuid4()))
        
        # Save course
        saved_course = await course_store.create(
            db,
            user_id=None,
            title=course_data.get("title", f"Learning Path: {request.topic}"),
            topic=request.topic,
            description=course_data.get("description"),
            modules=course_data.get("modules", []),
            difficulty=request.current_level,
            estimated_hours=course_data.get("estimated_hours"),
            learning_objectives=course_data.get("learning_objectives", []),
            prerequisites=course_data.get("prerequisites", [])
        )
        
        assembled = response_assembler.assemble(
            response=result.get("response", ""),
            mode=ChatMode.COURSE_PLANNER,
            ctas=result.get("ctas")
        )
        
        # Convert modules to response format
        from lyo_app.chat.schemas import CourseModule
        modules = []
        for mod in course_data.get("modules", []):
            modules.append(CourseModule(
                id=mod.get("id", str(uuid4())[:8]),
                title=mod.get("title", "Module"),
                description=mod.get("description", ""),
                lessons=mod.get("lessons", []),
                estimated_minutes=mod.get("estimated_minutes", 60)
            ))
        
        return CoursePlannerResponse(
            course_id=saved_course.id,
            title=course_data.get("title", f"Learning Path: {request.topic}"),
            description=course_data.get("description", ""),
            modules=modules,
            estimated_hours=course_data.get("estimated_hours", 10),
            learning_objectives=course_data.get("learning_objectives", []),
            prerequisites=course_data.get("prerequisites", []),
            ctas=assembled["ctas"]
        )
        
    except Exception as e:
        logger.error(f"Course plan error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# PRACTICE ENDPOINT
# =============================================================================

@router.post("/practice", response_model=PracticeResponse)
async def practice_endpoint(
    request: PracticeRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Practice/quiz generation endpoint.
    """
    try:
        context = {
            "topic": request.topic,
            "difficulty": request.difficulty,
            "question_count": request.question_count,
            "question_types": request.question_types,
            "focus_areas": request.focus_areas
        }
        
        result = await agent_registry.process(
            mode=ChatMode.PRACTICE,
            message=request.topic,
            context=context
        )
        
        quiz_data = result.get("quiz_data", {})
        quiz_id = result.get("quiz_id", str(uuid4()))
        
        assembled = response_assembler.assemble(
            response=result.get("response", ""),
            mode=ChatMode.PRACTICE,
            ctas=result.get("ctas")
        )
        
        # Convert questions to response format
        from lyo_app.chat.schemas import PracticeQuestion
        questions = []
        for q in quiz_data.get("questions", []):
            questions.append(PracticeQuestion(
                id=q.get("id", str(uuid4())[:8]),
                question=q.get("question", ""),
                question_type=q.get("question_type", "multiple_choice"),
                options=q.get("options"),
                correct_answer=q.get("correct_answer", ""),
                explanation=q.get("explanation", ""),
                difficulty=q.get("difficulty", request.difficulty)
            ))
        
        return PracticeResponse(
            quiz_id=quiz_id,
            topic=request.topic,
            questions=questions,
            total_questions=len(questions),
            estimated_time_minutes=len(questions) * 2,
            ctas=assembled["ctas"]
        )
        
    except Exception as e:
        logger.error(f"Practice error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# NOTE ENDPOINTS
# =============================================================================

@router.post("/notes", response_model=NoteResponse)
async def create_note_endpoint(
    request: NoteRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a note from content.
    """
    try:
        context = {
            "title": request.title,
            "extract_key_points": request.extract_key_points
        }
        
        result = await agent_registry.process(
            mode=ChatMode.NOTE_TAKER,
            message=request.content,
            context=context
        )
        
        note_data = result.get("note_data", {})
        
        # Save note (requires user_id in real implementation)
        # For now, we'll just return the processed note
        note_id = str(uuid4())
        
        assembled = response_assembler.assemble(
            response=result.get("response", ""),
            mode=ChatMode.NOTE_TAKER,
            ctas=result.get("ctas")
        )
        
        return NoteResponse(
            note_id=note_id,
            title=note_data.get("title", request.title or "Untitled Note"),
            content=note_data.get("content", request.content),
            summary=note_data.get("summary"),
            key_points=note_data.get("key_points", []),
            tags=note_data.get("tags", []),
            ctas=assembled["ctas"]
        )
        
    except Exception as e:
        logger.error(f"Note creation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# CTA TRACKING ENDPOINT
# =============================================================================

@router.post("/cta/click")
async def track_cta_click(
    request: CTAClickRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Track a CTA click for telemetry.
    """
    try:
        await telemetry_store.record(
            db,
            event_type="cta_click",
            session_id=request.session_id,
            conversation_id=request.conversation_id,
            message_id=request.message_id,
            cta_clicked=request.cta_id,
            metadata={"cta_type": request.cta_type}
        )
        
        return {"status": "recorded", "cta_id": request.cta_id}
        
    except Exception as e:
        logger.error(f"CTA tracking error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# TELEMETRY ENDPOINTS
# =============================================================================

@router.get("/telemetry/stats", response_model=TelemetryStatsResponse)
async def get_telemetry_stats(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    days: int = Query(7, ge=1, le=90, description="Number of days to include"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get telemetry statistics.
    
    Returns aggregated stats for:
    - Mode usage distribution
    - Token consumption
    - Cache hit rate
    - CTA click counts
    - Average latency
    """
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        stats = await telemetry_store.get_stats(
            db,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time
        )
        
        return TelemetryStatsResponse(
            by_mode=stats.get("by_mode", {}),
            totals=stats.get("totals", {}),
            cta_clicks=stats.get("cta_clicks", {}),
            period_start=start_time,
            period_end=end_time
        )
        
    except Exception as e:
        logger.error(f"Telemetry stats error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/telemetry/summary")
async def get_telemetry_summary(
    db: AsyncSession = Depends(get_db)
):
    """
    Get a quick telemetry summary for the last 24 hours.
    """
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=24)
        
        stats = await telemetry_store.get_stats(
            db,
            start_time=start_time,
            end_time=end_time
        )
        
        totals = stats.get("totals", {})
        
        # Calculate cache hit rate
        total_messages = totals.get("messages", 0)
        cache_hits = totals.get("cache_hits", 0)
        cache_hit_rate = (cache_hits / total_messages * 100) if total_messages > 0 else 0
        
        return {
            "period": "24h",
            "total_messages": total_messages,
            "total_tokens": totals.get("tokens", 0),
            "cache_hit_rate": round(cache_hit_rate, 2),
            "avg_latency_ms": totals.get("avg_latency_ms", 0),
            "top_modes": list(stats.get("by_mode", {}).keys())[:3],
            "total_cta_clicks": sum(stats.get("cta_clicks", {}).values())
        }
        
    except Exception as e:
        logger.error(f"Telemetry summary error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# COURSE MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/courses", response_model=List[ChatCourseRead])
async def get_courses(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Get generated courses.
    """
    try:
        courses = await course_store.get_by_topic(
            db, topic or "", limit=limit
        )
        return [ChatCourseRead.model_validate(c) for c in courses]
        
    except Exception as e:
        logger.error(f"Get courses error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/courses/{course_id}", response_model=ChatCourseRead)
async def get_course(
    course_id: str = Path(..., description="Course ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific course by ID.
    """
    try:
        course = await course_store.get_by_id(db, course_id)
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        return ChatCourseRead.model_validate(course)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get course error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# SELECTION POPUP ENDPOINTS
# (explain · add to notes · highlight)
# =============================================================================

@router.post("/selection/explain", response_model=SelectionExplainResponse)
async def explain_selection(
    request: SelectionExplainRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Explain a piece of text selected by the user in the chat thread.

    Called when the user taps *Explain* in the selection popup.
    Returns a short explanation plus key points, ready to display in a
    bottom sheet without navigating away from the conversation.
    """
    depth_instructions = {
        "brief":    "Give a concise 2-3 sentence explanation. No bullet lists.",
        "moderate": "Give a clear explanation in 1 short paragraph plus 2-3 bullet key points.",
        "detailed": "Give a thorough explanation with 3-5 bullet key points and 2-3 related topics.",
    }
    instruction = depth_instructions.get(request.depth, depth_instructions["brief"])

    history_context = ""
    if request.conversation_history:
        recent = request.conversation_history[-4:]
        history_context = "\n".join(
            f"{m.role.upper()}: {m.content[:300]}" for m in recent
        )

    system_prompt = (
        "You are Lyo, a friendly AI learning assistant. "
        "The user selected a piece of text from a conversation and wants a quick explanation. "
        f"{instruction} "
        "Return JSON with keys: explanation (string), key_points (list of strings), "
        "related_topics (list of strings). key_points and related_topics may be empty lists."
    )

    user_message = f'Selected text:\n"""\n{request.selected_text}\n"""'
    if history_context:
        user_message += f"\n\nConversation context:\n{history_context}"

    try:
        response = await ai_resilience_manager.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.4,
            max_tokens=400,
        )
        raw = response.get("content", "")
        # Parse structured JSON from the model
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = {"explanation": raw.strip(), "key_points": [], "related_topics": []}
    except Exception as exc:
        logger.warning("explain_selection AI call failed: %s", exc)
        data = {
            "explanation": "I couldn't generate an explanation right now. Please try again.",
            "key_points": [],
            "related_topics": [],
        }

    chip_actions = [
        ChipActionItem(id="add_note", action="add_to_notes", label="Add to notes", icon="note"),
        ChipActionItem(id="highlight", action="highlight", label="Highlight", icon="highlight"),
        ChipActionItem(id="practice", action="practice", label="Practice this", icon="quiz"),
    ]

    return SelectionExplainResponse(
        selected_text=request.selected_text,
        explanation=data.get("explanation", ""),
        key_points=data.get("key_points", []),
        related_topics=data.get("related_topics", []),
        chip_actions=chip_actions,
    )


@router.post("/selection/note", response_model=SelectionNoteResponse)
async def add_selection_to_notes(
    request: SelectionNoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Save a selected piece of chat text as a note.

    Called when the user taps *Add to notes* in the selection popup.
    The server auto-generates a title and tags when the client omits them.
    """
    user_id = str(current_user.id) if current_user else "anonymous"

    # Auto-generate title if not provided
    title = request.title
    if not title:
        # Truncate selected text to produce a natural title
        preview = request.selected_text[:60].strip()
        title = preview + ("…" if len(request.selected_text) > 60 else "")

    # Auto-generate a one-sentence summary via AI (best-effort, non-blocking)
    summary: Optional[str] = None
    try:
        sum_response = await ai_resilience_manager.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarise the following text in ONE sentence (≤20 words). "
                        "Return only the sentence, nothing else."
                    ),
                },
                {"role": "user", "content": request.selected_text[:1000]},
            ],
            temperature=0.3,
            max_tokens=60,
        )
        summary = sum_response.get("content", "").strip() or None
    except Exception as exc:
        logger.debug("Summary generation skipped: %s", exc)

    try:
        note = await notes_store.create(
            db,
            user_id=user_id,
            title=title,
            content=request.selected_text,
            summary=summary,
            tags=request.tags,
            source_message_id=request.message_id,
            source_conversation_id=request.conversation_id,
            note_type="key_concept",
        )
    except Exception as exc:
        logger.error("add_selection_to_notes: failed to save note for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save note. Please try again.",
        )

    return SelectionNoteResponse(
        note_id=str(note.id),
        title=note.title,
        content=note.content,
        summary=note.summary,
        tags=note.tags or [],
        created_at=note.created_at,
    )


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------

@router.post("/selection/highlight", response_model=HighlightRead, status_code=201)
async def create_highlight(
    request: HighlightCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Persist a yellow highlight on a chat message.

    The client sends the selected text and its character offsets within the
    message.  On the next conversation load the client fetches highlights via
    GET /chat/selection/highlights/{conversation_id} and re-renders them.
    """
    user_id = str(current_user.id) if current_user else "anonymous"

    highlight = await highlight_store.create(
        db,
        user_id=user_id,
        conversation_id=request.conversation_id,
        selected_text=request.selected_text,
        message_id=request.message_id,
        char_start=request.char_start,
        char_end=request.char_end,
        color=request.color,
        annotation=request.annotation,
    )
    return highlight


@router.get(
    "/selection/highlights/{conversation_id}",
    response_model=HighlightListResponse,
)
async def get_highlights(
    conversation_id: str = Path(..., description="Conversation ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Return all persisted highlights for a conversation.

    The response groups highlights by message_id so the client can apply them
    in a single pass when rendering the message list.
    Highlights not tied to a message live under the key ``__unanchored__``.
    """
    user_id = str(current_user.id) if current_user else "anonymous"
    highlights = await highlight_store.get_by_conversation(db, user_id, conversation_id)

    by_message: dict = {}
    for h in highlights:
        key = h.message_id or "__unanchored__"
        by_message.setdefault(key, []).append(HighlightRead.model_validate(h))

    return HighlightListResponse(
        conversation_id=conversation_id,
        highlights_by_message=by_message,
        total=len(highlights),
    )


@router.delete("/selection/highlights/{highlight_id}", status_code=204)
async def delete_highlight(
    highlight_id: str = Path(..., description="Highlight ID to remove"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Remove a highlight.  The yellow rendering will disappear on next reload.
    """
    user_id = str(current_user.id) if current_user else "anonymous"
    deleted = await highlight_store.delete(db, highlight_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Highlight not found")


@router.patch("/selection/highlights/{highlight_id}/annotation", response_model=HighlightRead)
async def update_highlight_annotation(
    body: AnnotationUpdate,
    highlight_id: str = Path(..., description="Highlight ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Update the margin annotation on an existing highlight."""
    user_id = str(current_user.id) if current_user else "anonymous"
    highlight = await highlight_store.update_annotation(db, highlight_id, user_id, body.annotation)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    return highlight


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def chat_health_check():
    """
    Health check for chat module.
    """
    return {
        "status": "healthy",
        "module": "chat",
        "features": {
            "routing": True,
            "agents": ["quick_explainer", "course_planner", "practice", "note_taker", "general"],
            "caching": response_cache is not None,
            "telemetry": True
        },
        "timestamp": datetime.utcnow().isoformat()
    }
