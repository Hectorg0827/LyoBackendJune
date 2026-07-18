import logging
import time
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user_or_guest, get_db
from lyo_app.auth.schemas import UserRead
from lyo_app.ai.router import MultimodalRouter
from lyo_app.ai.planner import LyoPlanner
from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai.schemas.lyo2 import (
    RouterRequest, RouterResponse, UnifiedChatResponse, ActiveArtifactContext,
    ConversationTurn, MediaRef, UIBlock, UIBlockType,
)
from lyo_app.api.v1.chat import ChatRequest, ConversationMessage
from lyo_app.chat.models import ChatMode
from lyo_app.chat.stores import conversation_store

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize Lyo 2.0 Components
# In production, these might be singletons or injected via dependencies
router_agent = MultimodalRouter()
planner_agent = LyoPlanner()

@router.post("/chat", response_model=UnifiedChatResponse)
async def lyo2_chat(
    request: RouterRequest,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db)
):
    """
    Lyo 2.0 Unified Chat Endpoint.
    Works for both authenticated users and guests (API-key only).
    """
    return await _process_lyo2_request(request, current_user, db)

@router.post("/legacy", response_model=UnifiedChatResponse)
async def lyo2_legacy_chat(
    request: ChatRequest,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db)
):
    """
    Legacy-compatible endpoint that routes through Lyo 2.0.
    """
    # Adapt ChatRequest to RouterRequest
    history = []
    if request.conversation_history:
        for msg in request.conversation_history:
            history.append({"role": msg.role, "content": msg.content})
            
    adapted_request = RouterRequest(
        text=request.message,
        history=history
    )
    
    return await _process_lyo2_request(adapted_request, current_user, db)

async def _process_lyo2_request(request: RouterRequest, current_user: UserRead, db: AsyncSession) -> UnifiedChatResponse:
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    try:
        persistent_conversation = None
        assistant_client_message_id = None
        authenticated_user_id = (
            str(current_user.id) if getattr(current_user, "id", 0) not in (0, "0", None) else None
        )
        if authenticated_user_id:
            if request.conversation_id:
                persistent_conversation = await conversation_store.get_owned_conversation(
                    db, request.conversation_id, authenticated_user_id
                )
                if persistent_conversation is None:
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
            persisted = await conversation_store.get_messages(
                db, persistent_conversation.id, limit=30
            )
            request.conversation_history = [
                ConversationTurn(role=message.role, content=message.content)
                for message in persisted
                if message.role in ("user", "assistant", "system")
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
                replayed = await conversation_store.get_message_by_client_id(
                    db, persistent_conversation.id, assistant_client_message_id
                )
                if replayed:
                    return UnifiedChatResponse(
                        answer_block=UIBlock(
                            type=UIBlockType.TUTOR_MESSAGE,
                            content={"text": replayed.content},
                        ),
                        metadata={
                            "trace_id": trace_id,
                            "conversation_id": persistent_conversation.id,
                            "replayed": True,
                        },
                    )
            if request.text:
                await conversation_store.add_message(
                    db,
                    persistent_conversation.id,
                    "user",
                    request.text,
                    client_message_id=request.client_message_id,
                )

        # 1. Layer A: Multimodal Routing
        logger.info(f"[{trace_id}] Layer A: Routing request for user {current_user.id}")
        routing_response = await router_agent.route(request)
        decision = routing_response.decision
        
        # Check for clarification gate
        if decision.needs_clarification:
            logger.info(f"[{trace_id}] Clarification needed: {decision.clarification_question}")
            clarification = decision.clarification_question or "Could you clarify what you would like to learn?"
            if persistent_conversation:
                await conversation_store.add_message(
                    db,
                    persistent_conversation.id,
                    "assistant",
                    clarification,
                    client_message_id=assistant_client_message_id,
                )
            return UnifiedChatResponse(
                answer_block=UIBlock(
                    type=UIBlockType.TUTOR_MESSAGE,
                    content={"text": clarification}
                ),
                metadata={
                    "clarification_needed": True,
                    "trace_id": trace_id,
                    "conversation_id": request.conversation_id,
                }
            )
            
        # 2. Layer B: Planning
        logger.info(f"[{trace_id}] Layer B: Planning execution for intent {decision.intent}")
        plan = await planner_agent.plan(request, decision)
        
        # 3. Layer C: Execution
        logger.info(f"[{trace_id}] Layer C: Executing plan")
        executor = LyoExecutor(db)
        execution_response = await executor.execute(
            user_id=str(current_user.id),
            plan=plan,
            original_request=request.text or "",
            conversation_history=[
                {"role": turn.role, "content": turn.content}
                for turn in request.conversation_history
            ]
        )
        
        # Add trace metadata
        latency_ms = int((time.time() - start_time) * 1000)
        execution_response.metadata.update({
            "trace_id": trace_id,
            "latency_ms": latency_ms,
            "intent": decision.intent,
            "tier": decision.suggested_tier,
            "conversation_id": request.conversation_id,
        })

        answer_text = execution_response.answer_block.content.get("text", "")
        if persistent_conversation and answer_text:
            await conversation_store.add_message(
                db,
                persistent_conversation.id,
                "assistant",
                answer_text,
                mode_used=decision.intent.value.lower() if decision.intent else ChatMode.GENERAL.value,
                client_message_id=assistant_client_message_id,
            )
        
        return execution_response

    except Exception as e:
        logger.error(f"[{trace_id}] Lyo 2.0 execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {str(e)}"
        )
