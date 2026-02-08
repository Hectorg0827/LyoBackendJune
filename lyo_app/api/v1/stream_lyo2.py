import logging
import asyncio
import json
import uuid
import time
from typing import AsyncGenerator, Dict, Any
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user_or_guest, get_db
from lyo_app.auth.schemas import UserRead
from lyo_app.ai.router import MultimodalRouter
from lyo_app.ai.planner import LyoPlanner
from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai.schemas.lyo2 import RouterRequest, UIBlock, UIBlockType, UnifiedChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/chat/stream")
async def stream_lyo2_chat(
    request: RouterRequest,
    fastapi_request: Request,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db)
):
    """
    Lyo 2.0 Streaming Chat Endpoint (SSE).
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        trace_id = str(uuid.uuid4())
        
        try:
            # 1. Send initial skeleton blocks immediately
            yield f"data: {json.dumps({'type': 'skeleton', 'blocks': ['answer', 'artifact']})}\n\n"
            await asyncio.sleep(0.01) # Yield to event loop
            
            # --- FAST TRACK: GREETINGS ---
            # Pre-routing check for simple greetings to ensure sub-100ms latency
            greetings = {"hi", "hello", "hey", "ciao", "hola", "yo", "greeting", "greetings"}
            clean_text = (request.text or "").strip().lower().replace("!", "").replace(".", "")
            
            if clean_text in greetings:
                logger.info(f"[{trace_id}] Greeting detected: '{clean_text}'. Bypassing router.")
                from lyo_app.chat.agents import agent_registry
                from lyo_app.chat.models import ChatMode
                
                chat_history = TURN_TO_DICT(request.conversation_history)
                async for token in agent_registry.process_stream(
                    mode=ChatMode.GENERAL,
                    message=request.text or "",
                    context={"learner_context": request.state_summary},
                    conversation_history=chat_history
                ):
                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                
                yield "data: [DONE]\n\n"
                return

            # 2. Layer A: Routing
            from lyo_app.ai.router import MultimodalRouter
            router_agent = MultimodalRouter()
            
            routing_response = await router_agent.route(request)
            decision = routing_response.decision
            
            # FAST TRACK: Chat / Conversation (LLM Decision)
            from lyo_app.ai.schemas.lyo2 import Intent
            if decision.intent == Intent.CHAT or decision.intent == Intent.UNKNOWN:
                from lyo_app.chat.agents import agent_registry
                from lyo_app.chat.models import ChatMode
                
                chat_history = TURN_TO_DICT(request.conversation_history)
                async for token in agent_registry.process_stream(
                    mode=ChatMode.GENERAL,
                    message=request.text or "",
                    context={"learner_context": request.state_summary},
                    conversation_history=chat_history
                ):
                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                
                yield "data: [DONE]\n\n"
                return

            if decision.needs_clarification:
                yield f"data: {json.dumps({'type': 'clarification', 'text': decision.clarification_question})}\n\n"
                return

            # 3. Layer B: Planning
            from lyo_app.ai.planner import LyoPlanner
            planner_agent = LyoPlanner()
            plan = await planner_agent.plan(request, decision)
            
            # 4. Layer C: Execution (Streaming)
            from lyo_app.ai.executor import LyoExecutor
            executor = LyoExecutor(db)
            
            history = TURN_TO_DICT(request.conversation_history)
            
            # Streaming Execution
            async for event in executor.execute_stream(
                user_id=str(current_user.id),
                plan=plan,
                original_request=request.text or "",
                conversation_history=history
            ):
                if event["type"] == "token":
                     yield f"data: {json.dumps({'type': 'token', 'token': event.get('token', event.get('text', ''))})}\n\n"
                elif event["type"] == "artifact":
                     yield f"data: {json.dumps({'type': 'artifact', 'block': event['block'].model_dump()})}\n\n"
                elif event["type"] == "answer_done":
                     yield f"data: {json.dumps({'type': 'answer', 'block': event['block'].model_dump()})}\n\n"
                elif event["type"] == "actions":
                     yield f"data: {json.dumps({'type': 'actions', 'blocks': [b.model_dump() for b in event['blocks']]})}\n\n"
                      
            # Completion signal
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Streaming failed for {trace_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

def TURN_TO_DICT(history):
    if not history: return []
    return [
        {"role": turn.role, "content": turn.content}
        for turn in history
    ]
