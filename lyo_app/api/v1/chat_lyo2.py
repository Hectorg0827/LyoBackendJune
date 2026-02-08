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
from lyo_app.ai.schemas.lyo2 import RouterRequest, RouterResponse, UnifiedChatResponse, ActiveArtifactContext, MediaRef
from lyo_app.api.v1.chat import ChatRequest, ConversationMessage

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
        # 1. Layer A: Multimodal Routing
        logger.info(f"[{trace_id}] Layer A: Routing request for user {current_user.id}")
        routing_response = await router_agent.route(request)
        decision = routing_response.decision
        
        # Check for clarification gate
        if decision.needs_clarification:
            logger.info(f"[{trace_id}] Clarification needed: {decision.clarification_question}")
            from lyo_app.ai.schemas.lyo2 import UIBlock, UIBlockType
            return UnifiedChatResponse(
                answer_block=UIBlock(
                    type=UIBlockType.TUTOR_MESSAGE,
                    content={"text": decision.clarification_question}
                ),
                metadata={"clarification_needed": True, "trace_id": trace_id}
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
            original_request=request.text or ""
        )
        
        # Add trace metadata
        latency_ms = int((time.time() - start_time) * 1000)
        execution_response.metadata.update({
            "trace_id": trace_id,
            "latency_ms": latency_ms,
            "intent": decision.intent,
            "tier": decision.suggested_tier
        })
        
        return execution_response

    except Exception as e:
        logger.error(f"[{trace_id}] Lyo 2.0 execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {str(e)}"
        )
