import logging
import asyncio
import json
import uuid
import time
from datetime import datetime
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

router_agent = MultimodalRouter()
planner_agent = LyoPlanner()

@router.post("/chat/stream")
async def stream_lyo2_chat(
    request: RouterRequest,
    fastapi_request: Request,
    current_user: UserRead = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db)
):
    """
    Lyo 2.0 Streaming Chat Endpoint (SSE).
    Returns a stream of UI blocks as they are ready.
    """
    trace_id = str(uuid.uuid4())
    logger.info(f"🚀 [STREAM] Starting session {trace_id} for user {current_user.id}")
    
    async def event_generator() -> AsyncGenerator[str, None]:
        start_time = time.time()
        
        try:
            # 1. Send initial skeleton blocks immediately
            logger.info(f"📡 [STREAM][{trace_id}] Sending skeleton event")
            yield f"data: {json.dumps({'type': 'skeleton', 'blocks': ['answer', 'artifact']})}\n\n"
            await asyncio.sleep(0.01) # Yield to event loop
            
            # 2. Layer A: Routing
            logger.info(f"🔍 [STREAM][{trace_id}] Starting Routing...")
            r_start = time.time()
            try:
                routing_response = await asyncio.wait_for(router_agent.route(request), timeout=35.0)
            except asyncio.TimeoutError:
                logger.error(f"❌ [STREAM][{trace_id}] Routing timed out after 35s")
                yield f"data: {json.dumps({'type': 'error', 'message': 'Routing phase timed out'})}\n\n"
                return
                
            decision = routing_response.decision
            logger.info(f"✅ [STREAM][{trace_id}] Routing complete ({time.time()-r_start:.2f}s): {decision.intent} (confidence={decision.confidence})")
            
            if decision.needs_clarification and decision.confidence > 0.3:
                # Only ask for clarification if the router is reasonably confident
                # that it truly cannot understand. Low-confidence clarifications
                # from fallback routing should not block the pipeline.
                logger.info(f"🤔 [STREAM][{trace_id}] Needs clarification: {decision.clarification_question}")
                yield f"data: {json.dumps({'type': 'clarification', 'text': decision.clarification_question})}\n\n"
                return

            # 3. Layer B: Planning
            logger.info(f"📋 [STREAM][{trace_id}] Starting Planning...")
            p_start = time.time()
            try:
                plan = await asyncio.wait_for(planner_agent.plan(request, decision), timeout=35.0)
            except asyncio.TimeoutError:
                logger.error(f"❌ [STREAM][{trace_id}] Planning timed out after 35s")
                yield f"data: {json.dumps({'type': 'error', 'message': 'Planning phase timed out'})}\n\n"
                return
            
            logger.info(f"✅ [STREAM][{trace_id}] Planning complete ({time.time()-p_start:.2f}s): {len(plan.steps)} steps")

            # 4. Layer C: Execution (Simulated Streaming)
            logger.info(f"⚡ [STREAM][{trace_id}] Starting Execution...")
            e_start = time.time()
            executor = LyoExecutor(db)
            
            # Build conversation history for multi-turn context
            history = [
                {"role": turn.role, "content": turn.content}
                for turn in request.conversation_history
            ] if request.conversation_history else []
            
            try:
                execution_response = await asyncio.wait_for(
                    executor.execute(
                        user_id=str(current_user.id),
                        plan=plan,
                        original_request=request.text or "",
                        conversation_history=history
                    ),
                    timeout=60.0 # Execution can take longer
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ [STREAM][{trace_id}] Execution timed out after 60s")
                yield f"data: {json.dumps({'type': 'error', 'message': 'Execution phase timed out'})}\n\n"
                return
                
            logger.info(f"✅ [STREAM][{trace_id}] Execution complete ({time.time()-e_start:.2f}s)")
            
            # --- Multipart Agent Block Markers ---
            # Wrap the answer text with agent markers for cinematic reveal on iOS.
            # The iOS AgenticClassroomViewModel parses [tutor], [quiz], [content], etc.
            # to split the response into visually distinct agent blocks.
            answer_text = execution_response.answer_block.content.get("text", "")
            if answer_text and not any(f"[{tag}]" in answer_text for tag in ["tutor", "quiz", "sentiment", "content", "metacognition"]):
                # Wrap the main answer with a [tutor] marker
                enriched_content = dict(execution_response.answer_block.content)
                enriched_content["text"] = f"[tutor]\n{answer_text}"
                enriched_block = UIBlock(
                    type=execution_response.answer_block.type,
                    content=enriched_content,
                    version_id=execution_response.answer_block.version_id
                )
                yield f"data: {json.dumps({'type': 'answer', 'block': enriched_block.model_dump()})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'answer', 'block': execution_response.answer_block.model_dump()})}\n\n"
            
            if execution_response.artifact_block:
                # Send agent-tagged artifact event
                artifact = execution_response.artifact_block
                artifact_type = artifact.type
                
                # Map artifact types to agent roles for cinematic reveal
                agent_tag_map = {
                    UIBlockType.QUIZ: "quiz",
                    UIBlockType.STUDY_PLAN: "content",
                    UIBlockType.FLASHCARDS: "content",
                    UIBlockType.CODE: "tutor",
                }
                agent_tag = agent_tag_map.get(artifact_type, "content")
                
                # Tag the artifact content with agent marker
                tagged_content = dict(artifact.content) if artifact.content else {}
                tagged_content["_agent"] = agent_tag
                
                tagged_artifact = UIBlock(
                    type=artifact.type,
                    content=tagged_content,
                    version_id=artifact.version_id
                )
                yield f"data: {json.dumps({'type': 'artifact', 'block': tagged_artifact.model_dump()})}\n\n"
            
            # Send A2UI component blocks (rich interactive UI)
            for a2ui_block in execution_response.a2ui_blocks:
                logger.info(f"🎨 [STREAM][{trace_id}] Sending a2ui event")
                yield f"data: {json.dumps({'type': 'a2ui', 'block': a2ui_block.model_dump()})}\n\n"
            
            # Send open_classroom payload (course creation trigger)
            if execution_response.open_classroom_payload:
                logger.info(f"🏫 [STREAM][{trace_id}] Sending open_classroom event")
                oc_block = {
                    "type": "OpenClassroomBlock",
                    "content": {
                        "type": "OPEN_CLASSROOM",
                        **execution_response.open_classroom_payload
                    }
                }
                yield f"data: {json.dumps({'type': 'open_classroom', 'block': oc_block})}\n\n"
                
            yield f"data: {json.dumps({'type': 'actions', 'blocks': [b.model_dump() for b in execution_response.next_actions]})}\n\n"
            
            # Completion signal
            yield "data: [DONE]\n\n"
            logger.info(f"🏁 [STREAM][{trace_id}] Total session time: {time.time()-start_time:.2f}s")

        except Exception as e:
            logger.error(f"💥 [STREAM][{trace_id}] Critical failure: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
