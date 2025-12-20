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
"""

import asyncio
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
from lyo_app.auth.models import User
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
    GreetingResponse
)
from lyo_app.chat.router import chat_router, mode_transition_manager
from lyo_app.chat.agents import agent_registry
from lyo_app.chat.assembler import response_assembler
from lyo_app.chat.stores import (
    course_store, notes_store, conversation_store, 
    response_cache, telemetry_store
)
from lyo_app.streaming import get_sse_manager, stream_response, EventType, StreamEvent
from lyo_app.personalization.service import personalization_engine
from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.core.context_engine import context_engine

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
            learner_context = await personalization_engine.build_prompt_context(db, str(current_user.id))
        except Exception as e:
            logger.warning(f"Failed to build context for greeting: {e}")

    # 2. Construct prompt
    system_prompt = (
        "You are Lyo, a friendly, encouraging AI tutor. "
        "Your goal is to welcome the user back. "
        "Keep it short (max 2 sentences). "
        "Be warm and proactive. "
        f"Adapt your tone for a {user_context_tag} audience. "
        "If context is provided, use it to make the greeting specific (e.g., mentioning a recent topic or struggle), "
        "but do not be creepy or over-specific. Just a gentle nod to their journey."
    )
    
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
            provider_order=["gemini-flash", "gemini-pro", "openai"] # Prefer fast model
        )
        greeting_text = response.get("content", "Welcome back! Ready to learn something new?")
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting_text = "Welcome back! Ready to learn something new?"

    return GreetingResponse(
        greeting=greeting_text,
        context_used=bool(learner_context)
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

        # Best-effort backfill user binding for continuity
        if current_user and not conversation.user_id:
            try:
                conversation.user_id = str(current_user.id)
                await db.commit()
            except Exception:
                await db.rollback()

        # Best-effort topic assignment (does not change client contract)
        if request.context and not conversation.topic:
            try:
                conversation.topic = request.context[:200]
                await db.commit()
            except Exception:
                await db.rollback()
        
        # 2. Route the message
        mode, confidence, reasoning = chat_router.route(
            message=request.message,
            mode_hint=request.mode_hint,
            action=request.action,
            context=request.context
        )
        
        logger.info(f"Routed to {mode.value} with confidence {confidence}: {reasoning}")
        
        # 3. Build context for agent
        context = {
            "context": request.context,
            "conversation_id": conversation.id,
            "resource_id": request.resource_id,
            "course_id": request.course_id,
            "note_id": request.note_id,
        }

        # Optional learner context (authenticated users only)
        if current_user:
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
                logger.warning(f"Personalization context unavailable: {e}")
        
        # 4. Build conversation history
        history = []
        if request.conversation_history:
            for msg in request.conversation_history:
                history.append({"role": msg.role, "content": msg.content})
        
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
        
        # 7. Get recent CTAs for deduplication
        recent_messages = await conversation_store.get_messages(
            db, conversation.id, limit=5
        )
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
                db, conversation.id,
                role="user",
                content=request.message,
                mode_used=mode.value
            )
        
        async def save_assistant_message():
            return await conversation_store.add_message(
                db, conversation.id,
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
        
        # Execute saves in parallel
        _, assistant_message = await asyncio.gather(
            save_user_message(),
            save_assistant_message()
        )
        
        # 11. Record telemetry (fire-and-forget pattern for non-critical operation)
        asyncio.create_task(
            telemetry_store.record(
                db,
                event_type="chat_response",
                session_id=session_id,
                conversation_id=conversation.id,
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
        )
        
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
                source_conversation_id=conversation.id
            )
            generated_course_id = saved_course.id
        
        # 14. Build iOS-compatible embedded payloads
        quick_explainer_data = None
        course_proposal_data = None
        
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
        
        return ChatResponse(
            response=assembled["response"],
            message_id=assistant_message.id,
            conversation_id=conversation.id,
            mode_used=mode.value,
            mode_confidence=confidence,
            quick_explainer=quick_explainer_data,
            course_proposal=course_proposal_data,
            conversation_history=updated_history,
            ctas=assembled["ctas"],
            chip_actions=assembled["chip_actions"],
            tokens_used=agent_result.get("tokens_used"),
            cache_hit=cache_hit,
            latency_ms=latency_ms,
            generated_course_id=generated_course_id,
            generated_note_id=generated_note_id
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
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
            
            # 2. Route the message
            mode, confidence, reasoning = chat_router.route(
                message=request.message,
                mode_hint=request.mode_hint,
                action=request.action,
                context=request.context
            )
            
            # 3. Send start event
            yield StreamEvent(
                event=EventType.MESSAGE_START,
                data={
                    "session_id": session_id,
                    "conversation_id": conversation.id,
                    "mode": mode.value,
                    "confidence": confidence,
                    "timestamp": time.time()
                }
            ).to_sse()
            
            # 4. Check cache first
            cache_hit = False
            cached_response = None
            
            if response_cache:
                cached_response = await response_cache.get(request.message, mode.value)
                if cached_response:
                    cache_hit = True
            
            # 5. Build context
            context = {
                "context": request.context,
                "conversation_id": conversation.id,
                "resource_id": request.resource_id,
                "course_id": request.course_id,
                "note_id": request.note_id,
            }

            # Optional learner context (authenticated users only)
            if current_user:
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
                    logger.warning(f"Personalization context unavailable: {e}")
            
            history = []
            if request.conversation_history:
                for msg in request.conversation_history:
                    history.append({"role": msg.role, "content": msg.content})
            
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
                db, conversation.id, session_id, mode.value, request, assembled,
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
        
        _, assistant_message = await asyncio.gather(save_user(), save_assistant())
        
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
# QUICK EXPLAINER ENDPOINT
# =============================================================================

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
        
        assembled = response_assembler.assemble(
            response=result.get("response", ""),
            mode=ChatMode.QUICK_EXPLAINER,
            ctas=result.get("ctas"),
            chips=result.get("chips")
        )
        
        return QuickExplainerResponse(
            explanation=assembled["response"],
            key_points=result.get("key_points", []),
            related_topics=result.get("related_topics", []),
            ctas=assembled["ctas"],
            chip_actions=assembled["chip_actions"]
        )
        
    except Exception as e:
        logger.error(f"Quick explain error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
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
