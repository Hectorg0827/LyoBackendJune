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
from lyo_app.ai.schemas.lyo2 import RouterRequest, UIBlock, UIBlockType, UnifiedChatResponse, ActionType, PlannedAction, Intent
from lyo_app.ai.nexus.agent import LyoNexusAgent
from lyo_app.ai.nexus.factory import LyoNexusFactory
from lyo_app.ai.nexus.media_worker import LyoNexusMediaWorker
from lyo_app.ai_agents.multi_agent_v2.agents.test_prep_agent import TestPrepAgent
from lyo_app.core.config import settings
from lyo_app.a2ui.a2ui_compiler import lyo_response_builder

logger = logging.getLogger(__name__)

router = APIRouter()

router_agent = MultimodalRouter()
planner_agent = LyoPlanner()
test_prep_agent = TestPrepAgent()

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
                
            # Intercept TEST_PREP intent to gather structured details
            if decision.intent == Intent.TEST_PREP:
                logger.info(f"📚 [STREAM][{trace_id}] Analyzing Test Prep intent...")
                prep_result = await test_prep_agent.analyze_test_prep(request)
                if prep_result.success and prep_result.data:
                    data = prep_result.data
                    if data.missing_critical_info and data.follow_up_question:
                        # Yield a clarification if critical info is missing
                        logger.info(f"🤔 [STREAM][{trace_id}] Test Prep needs clarification: missing {data.missing_critical_info}")
                        yield f"data: {json.dumps({'type': 'clarification', 'text': data.follow_up_question})}\n\n"
                        return
                    # Optionally attach extracted data back to the request for the planner
                    request.text += f"\n[System: Extracted Test details: Subject={data.subject}, Topics={data.topics}, Date={data.test_date}]"

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

            # ── Deterministic A2UI injection ──────────────────────────
            # The LLM planner sometimes omits GENERATE_A2UI steps even
            # when the intent clearly demands rich UI. Ensure one exists.
            _has_a2ui_step = any(
                s.action_type == ActionType.GENERATE_A2UI for s in plan.steps
            )
            _intent_to_a2ui = {
                Intent.COURSE:              {"ui_type": "course", "title": request.text or ""},
                Intent.EXPLAIN:             {"ui_type": "explanation"},
                Intent.QUIZ:                {"ui_type": "quiz"},
                Intent.FLASHCARDS:          {"ui_type": "quiz"},
                Intent.STUDY_PLAN:          {"ui_type": "study_plan"},
                Intent.TEST_PREP:           {"ui_type": "study_plan"},
                # Fallback: ALL other text-generating intents get an explanation card
                Intent.CHAT:                {"ui_type": "explanation"},
                Intent.GENERAL:             {"ui_type": "explanation"},
                Intent.GREETING:            {"ui_type": "explanation"},
                Intent.HELP:                {"ui_type": "explanation"},
                Intent.SUMMARIZE_NOTES:     {"ui_type": "explanation"},
                Intent.COMMUNITY:           {"ui_type": "explanation"},
                Intent.SCHEDULE_REMINDERS:  {"ui_type": "explanation"},
                Intent.MODIFY_ARTIFACT:     {"ui_type": "explanation"},
                Intent.UNKNOWN:             {"ui_type": "explanation"},
            }
            if not _has_a2ui_step and decision.intent in _intent_to_a2ui:
                a2ui_params = _intent_to_a2ui[decision.intent]
                plan.steps.append(PlannedAction(
                    action_type=ActionType.GENERATE_A2UI,
                    description=f"Auto-injected A2UI step for intent {decision.intent}",
                    parameters=a2ui_params,
                ))
                logger.info(
                    f"📌 [STREAM][{trace_id}] Injected GENERATE_A2UI step "
                    f"(intent={decision.intent}, ui_type={a2ui_params['ui_type']})"
                )

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
                        conversation_history=history,
                        intent=decision.intent.value if decision.intent else None
                    ),
                    timeout=60.0 # Execution can take longer
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ [STREAM][{trace_id}] Execution timed out after 60s")
                yield f"data: {json.dumps({'type': 'error', 'message': 'Execution phase timed out'})}\n\n"
                return
                
            logger.info(f"✅ [STREAM][{trace_id}] Execution complete ({time.time()-e_start:.2f}s)")
            
            # --- Lyo-Nexus Slicing Engine ---
            logger.info(f"🔪 [STREAM][{trace_id}] Piping to Lyo-Nexus Agent...")
            
            async def dispatch_update(update_brick: Dict[str, Any]):
                # Callback used by LyoNexusMediaWorker to send async media updates
                logger.info(f"🔄 [STREAM][{trace_id}] Nexus Async Update: {update_brick['update_id']}")
                # We yield into the event_generator's stream (this is tricky in a real setup,
                # but for SSE, we would push to an async queue that event_generator reads from.
                # Since we can't easily yield from a detached task directly into the active SSE generator
                # without an async Queue, we'll log it. In a production WebSocket, we'd do await websocket.send_json().)
                pass # Queue implementation required for True Async SSE
                
            nexus_factory = LyoNexusFactory()
            nexus_media = LyoNexusMediaWorker(dispatch_update_callback=dispatch_update)
            nexus_agent = LyoNexusAgent(factory=nexus_factory, media_worker=nexus_media)
            
            # Simulate a token stream from the "Brain"
            async def mock_llm_stream(text: str) -> AsyncGenerator[str, None]:
                # In a real setup, this is response.text_stream from Gemini
                chunk_size = 10
                for i in range(0, len(text), chunk_size):
                    yield text[i:i+chunk_size]
                    await asyncio.sleep(0.005) # Simulating LLM generation time
            
            # Get the text we want to pipe
            raw_llm_text = execution_response.answer_block.content.get("text", "")
            
            # Process via Nexus
            async for json_brick in nexus_agent.process_stream(
                text_stream=mock_llm_stream(raw_llm_text),
                capabilities=["a2ui_v1"] # Mock manifest
            ):
                logger.info(f"🧱 [STREAM][{trace_id}] Nexus yielded {json_brick['type']} brick")
                # Wrap it so the old iOS client doesn't break, or send raw if iOS updated
                wrapped_block = UIBlock(
                    type=UIBlockType.A2UI_COMPONENT,
                    content={"component": json_brick}
                )
                yield f"data: {json.dumps({'type': 'a2ui', 'block': wrapped_block.model_dump()})}\n\n"
            
            if execution_response.artifact_block:
                # Send agent-tagged artifact event
                artifact = execution_response.artifact_block
                artifact_type = artifact.type
                
                # Map artifact types to agent roles for cinematic reveal
                agent_tag_map = {
                    UIBlockType.QUIZ: "quiz",
                    UIBlockType.STUDY_PLAN: "content",
                    UIBlockType.FLASHCARDS: "content",
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
            use_v2 = getattr(settings, "enable_a2ui_v2", False)
            for a2ui_block in execution_response.a2ui_blocks:
                logger.info(f"🎨 [STREAM][{trace_id}] Sending a2ui event (v2={use_v2})")
                yield f"data: {json.dumps({'type': 'a2ui', 'block': a2ui_block.model_dump()})}\n\n"

                # ── v2: Also emit a lyo_ui event with LyoResponse envelope ──
                if use_v2:
                    comp_dict = a2ui_block.content.get("component") if a2ui_block.content else None
                    if comp_dict:
                        lyo_resp = lyo_response_builder.build(
                            ui=None,  # raw dict, not A2UIComponent
                            request_id=trace_id,
                            conversation_id=trace_id,
                        )
                        # Attach the raw component with variant directly
                        lyo_resp["ui"] = comp_dict
                        yield f"data: {json.dumps({'type': 'lyo_ui', 'response': lyo_resp})}\n\n"
            
            # Send open_classroom payload (course creation trigger)
            # Safety net: if the COURSE pipeline ran but produce_course() returned
            # None (e.g. Gemini course-data agent failed), synthesise a minimal
            # payload from the request text so iOS classroom still opens.
            if (
                execution_response.open_classroom_payload is None
                and decision.intent == Intent.COURSE
            ):
                import re as _re
                topic_text = (request.text or "").strip()
                # Strip leading imperative phrases to get the bare topic
                topic_text = _re.sub(
                    r"^(create (a )?course (on|about)?|make (a )?course (on|about)?|"
                    r"build (a )?course (on|about)?|teach me (about|on)?|"
                    r"i want (a )?course (on|about)?|course on|course about)\s*",
                    "",
                    topic_text,
                    flags=_re.IGNORECASE,
                ).strip() or topic_text
                fallback_oc = {
                    "course": {
                        "id": str(uuid.uuid4()),
                        "title": topic_text.title() if topic_text else "Your Course",
                        "topic": topic_text,
                        "level": "beginner",
                        "duration": "4 weeks",
                        "objectives": [
                            f"Understand the fundamentals of {topic_text}",
                            f"Apply key concepts of {topic_text} in practice",
                            f"Build confidence with {topic_text}",
                        ],
                    }
                }
                # Only use the fallback when produce_course() truly returned nothing.
                # The executor already populates open_classroom_payload from
                # a2ui_producer.produce_course(), so this branch only fires when
                # that whole chain failed (e.g. Gemini course-data call error).
                execution_response = execution_response.model_copy(
                    update={"open_classroom_payload": fallback_oc}
                )
                logger.warning(
                    f"⚠️ [STREAM][{trace_id}] COURSE intent but no open_classroom_payload — "
                    f"using synthesised fallback for topic: '{topic_text[:60]}'"
                )

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

                # ── v2: Also emit lyo_command event ──
                if use_v2:
                    cmd = lyo_response_builder.build_command(
                        "open_classroom",
                        execution_response.open_classroom_payload
                    )
                    lyo_resp = lyo_response_builder.build(
                        command=cmd,
                        request_id=trace_id,
                        conversation_id=trace_id,
                    )
                    yield f"data: {json.dumps({'type': 'lyo_command', 'response': lyo_resp})}\n\n"
                
            yield f"data: {json.dumps({'type': 'actions', 'blocks': [b.model_dump() for b in execution_response.next_actions]})}\n\n"

            # ── v2: Also emit lyo_suggestions event ──
            if use_v2:
                v2_suggestions = []
                for action_block in execution_response.next_actions:
                    if action_block.content and "actions" in action_block.content:
                        for label in action_block.content["actions"]:
                            v2_suggestions.append({"text": label})
                if v2_suggestions:
                    lyo_resp = lyo_response_builder.build(
                        suggestions=v2_suggestions,
                        request_id=trace_id,
                        conversation_id=trace_id,
                    )
                    yield f"data: {json.dumps({'type': 'lyo_suggestions', 'response': lyo_resp})}\n\n"
            
            # Completion signal
            yield "data: [DONE]\n\n"
            logger.info(f"🏁 [STREAM][{trace_id}] Total session time: {time.time()-start_time:.2f}s")

        except Exception as e:
            logger.error(f"💥 [STREAM][{trace_id}] Critical failure: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
