import logging
import asyncio
import json
import uuid
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user_or_guest, get_db
from lyo_app.auth.schemas import UserRead
from lyo_app.ai.router import MultimodalRouter
from lyo_app.ai.planner import LyoPlanner
from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai.schemas.lyo2 import RouterRequest, UIBlock, UIBlockType, UnifiedChatResponse, ActionType, PlannedAction, Intent
from lyo_app.ai_agents.multi_agent_v2.agents.test_prep_agent import TestPrepAgent
from lyo_app.core.config import settings
from lyo_app.services.proactive_engagement import proactive_engagement_service
from lyo_app.ai_agents.optimization.performance_optimizer import ai_performance_optimizer, OptimizationLevel
from lyo_app.ai.schemas.smart_block import SmartBlock, SmartBlockType, QuizOption, MasteryNode

logger = logging.getLogger(__name__)


import re as _re

# --- Minimal lyo_response_builder for v2 lyo_command events ---
class _LyoResponseBuilder:
    def build_command(self, action, payload=None):
        return {
            "action": action,
            "payload": payload or {}
        }

    def build(self, command, request_id=None, conversation_id=None):
        # Matches LyoResponseSchema in lyo2_v2.py
        return {
            "version": "2.0",
            "message": "",
            "ui": None,
            "command": command,
            "suggestions": [],
            "request_id": request_id,
            "conversation_id": conversation_id
        }

lyo_response_builder = _LyoResponseBuilder()

def _extract_course_topic(user_text: str) -> str:
    topic = _re.sub(
        r"^(create (a )?course (on|about|for)?|make (a )?course (on|about|for)?|"
        r"build (a )?course (on|about|for)?|teach me( about| on)?|"
        r"i want (a )?course (on|about)?|course on|course about|"
        r"give me a course( on)?|a course on)\s*",
        "", user_text.strip(), flags=_re.IGNORECASE,
    ).strip()
    return topic or user_text.strip()

def _to_smart_blocks(
    answer_text: Optional[str],
    artifact: Optional[UIBlock],
) -> list[dict]:
    """Convert legacy UIBlock answer + artifact into SmartBlock dicts.

    Returns a list of serialised SmartBlocks so older clients can ignore
    the ``smart_blocks`` event while newer clients consume it.
    """
    blocks: list[SmartBlock] = []

    if answer_text:
        blocks.append(SmartBlock.text(answer_text))

    if artifact is not None:
        content = artifact.content or {}
        if artifact.type == UIBlockType.QUIZ:
            options = [
                QuizOption(id=str(i), text=o.get("text", o) if isinstance(o, dict) else str(o))
                for i, o in enumerate(content.get("options", []))
            ]
            blocks.append(SmartBlock.quiz(
                question=content.get("question", ""),
                options=options,
                correct_index=content.get("correct_index", 0),
                explanation=content.get("explanation"),
            ))
        elif artifact.type == UIBlockType.FLASHCARDS:
            cards = content.get("cards", [])
            for card in cards:
                blocks.append(SmartBlock.flashcard(
                    front=card.get("front", ""),
                    back=card.get("back", ""),
                ))
        elif artifact.type == UIBlockType.STUDY_PLAN:
            blocks.append(SmartBlock.text(
                content.get("plan", json.dumps(content, default=str)),
                subtype="summary",
            ))

    return [b.model_dump() for b in blocks]


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
            collected_bricks = []
            
            skeleton_brick = {"type": "skeleton", "blocks": ["answer", "artifact"]}
            collected_bricks.append(skeleton_brick)
            yield f"data: {json.dumps(skeleton_brick)}\n\n"
            # Note: the yield itself surrenders control to the event loop;
            # an explicit sleep(0.01) is not needed and adds 10 ms of latency.
            
            # 2. Performance & Cache Layer (New for Phase 17)
            # Ensure optimizer is ready
            await ai_performance_optimizer.initialize()
            
            # Optimize request based on system load
            opt_data = await ai_performance_optimizer.optimize_request(
                agent_type=request.forced_intent.value if request.forced_intent else "general",
                request_data=request.model_dump()
            )
            
            # Check for cached full response (Skip remaining layers if hit)
            cache_key = opt_data.get("cache_key")
            cached_full_resp = await ai_performance_optimizer.cache_manager.get("full_response", key=cache_key)
            if cached_full_resp:
                logger.info(f"✨ [STREAM][{trace_id}] Full cache hit! Yielding optimized response.")
                for brick in cached_full_resp:
                    yield f"data: {json.dumps(brick)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Apply optimized config (e.g. reduced tokens if memory is high)
            opt_config = opt_data.get("processing_config", {})
            
            # 2. Layer A: Routing
            logger.info(f"🔍 [STREAM][{trace_id}] Starting Routing...")
            r_start = time.time()
            
            if request.forced_intent:
                logger.info(f"🎯 [STREAM][{trace_id}] Bypassing router. Forced intent: {request.forced_intent.value}")
                decision = RouterDecision(
                    intent=request.forced_intent,
                    confidence=1.0,
                    needs_clarification=False,
                    suggested_tier="MEDIUM"
                )
            else:
                try:
                    # Fire nudge fetch and routing in parallel — nudges were
                    # previously sequential (200-500 ms of DB latency wasted
                    # before the router could even start).
                    nudges_task = asyncio.create_task(
                        proactive_engagement_service.get_pending_nudges_for_user(current_user.id, db)
                    )
                    routing_task = asyncio.create_task(
                        asyncio.wait_for(router_agent.route(request), timeout=35.0)
                    )

                    # Await routing first (it's on the critical path)
                    routing_response = await routing_task
                    decision = routing_response.decision

                    # Await nudges (likely already done; cost is near-zero)
                    try:
                        nudges = await nudges_task
                        if nudges:
                            proactive_context = "\n**Proactive System Nudges (Incorporate these into your greeting if relevant):**\n"
                            for n in nudges:
                                proactive_context += f"- [{n.nudge_type}] {n.title}: {n.message}\n"
                            request.text = f"[Proactive Context: {proactive_context}]\n" + (request.text or "")
                    except Exception as ne:
                        logger.warning(f"Failed to fetch proactive nudges: {ne}")
                except asyncio.TimeoutError:
                    logger.error(f"❌ [STREAM][{trace_id}] Routing timed out after 35s")
                    yield f"data: {json.dumps({'type': 'error', 'message': 'My magical circuits got a little crossed while thinking about that. Could we try again?'})}\n\n"
                    return
                
            logger.info(f"✅ [STREAM][{trace_id}] Routing complete ({time.time()-r_start:.2f}s): {decision.intent} (confidence={decision.confidence})")
            
            if decision.intent == Intent.COURSE:
                _topic = _extract_course_topic(request.text or "")
                _preview_oc = {
                    "course": {
                        "id": str(uuid.uuid4()),
                        "title": _topic.title() if _topic else "Your Course",
                        "topic": _topic,
                        "level": "beginner",
                        "duration": "~30 min",
                        "objectives": [
                            f"Understand the core concepts of {_topic}",
                            "Apply your knowledge with guided exercises",
                            "Build skills through structured practice",
                        ],
                    }
                }
                yield f"data: {json.dumps({'type': 'open_classroom', 'block': {'type': 'OpenClassroomBlock', 'content': {'type': 'OPEN_CLASSROOM', **_preview_oc}}})}\n\n"
                
                # v2: emit lyo_command for iOS v2 pipeline
                cmd = lyo_response_builder.build_command("open_classroom", _preview_oc)
                lyo_resp = lyo_response_builder.build(command=cmd, request_id=trace_id, conversation_id=trace_id)
                brick_data = {"type": "lyo_command", "response": lyo_resp}
                collected_bricks.append(brick_data)
                yield f"data: {json.dumps(brick_data)}\n\n"
                    
                logger.info(f"🏫 [STREAM][{trace_id}] Fast course preview sent for: '{_topic[:60]}'")
            
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
                yield f"data: {json.dumps({'type': 'error', 'message': 'My magical circuits got a little crossed while thinking about that. Could we try again?'})}\n\n"
                return
            
            logger.info(f"✅ [STREAM][{trace_id}] Planning complete ({time.time()-p_start:.2f}s): {len(plan.steps)} steps")

            # ── Ensure a GENERATE_TEXT step exists ─────────────────────
            # The LLM planner sometimes omits GENERATE_TEXT steps.
            # Ensure one exists so the executor always produces final_text.
            _has_text_step = any(
                s.action_type == ActionType.GENERATE_TEXT for s in plan.steps
            )
            if not _has_text_step:
                plan.steps.append(PlannedAction(
                    action_type=ActionType.GENERATE_TEXT,
                    description=f"Auto-injected text generation for intent {decision.intent}",
                    parameters={"content": None},
                ))
                logger.info(
                    f"📌 [STREAM][{trace_id}] Injected GENERATE_TEXT step "
                    f"(intent={decision.intent})"
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
                yield f"data: {json.dumps({'type': 'error', 'message': 'My magical circuits got a little crossed while thinking about that. Could we try again?'})}\n\n"
                return
                
            logger.info(f"✅ [STREAM][{trace_id}] Execution complete ({time.time()-e_start:.2f}s)")
            
            # ── Emit plain-text answer event ─────────────────────────
            raw_llm_text = execution_response.answer_block.content.get("text", "")
            
            # Optimize final response text (Phase 17)
            raw_llm_text = await ai_performance_optimizer.optimize_response(
                agent_type=decision.intent.value,
                response=raw_llm_text,
                context={
                    "user_id": current_user.id,
                    "intent": decision.intent.value,
                    "current_mood": "neutral"
                }
            )
            
            if raw_llm_text:
                answer_brick = {
                    "type": "answer",
                    "block": {
                        "type": "TutorMessageBlock",
                        "content": {"text": raw_llm_text},
                        "priority": 0
                    }
                }
                collected_bricks.append(answer_brick)
                yield f"data: {json.dumps(answer_brick)}\n\n"
                logger.info(f"📝 [STREAM][{trace_id}] Emitted answer event ({len(raw_llm_text)} chars)")
            
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
            
            # ── Emit SmartBlocks event (v2 unified format) ──────────
            smart_block_dicts = _to_smart_blocks(raw_llm_text, execution_response.artifact_block)
            if smart_block_dicts:
                sb_brick = {"type": "smart_blocks", "blocks": smart_block_dicts}
                collected_bricks.append(sb_brick)
                yield f"data: {json.dumps(sb_brick)}\n\n"
                logger.info(f"🧱 [STREAM][{trace_id}] Emitted {len(smart_block_dicts)} smart_blocks")

            # Send open_classroom payload (course creation trigger)
            if (
                execution_response.open_classroom_payload is None
                and decision.intent == Intent.COURSE
            ):
                topic_text = _extract_course_topic(request.text or "")
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
                execution_response = execution_response.model_copy(
                    update={"open_classroom_payload": fallback_oc}
                )
                logger.warning(
                    f"⚠️ [STREAM][{trace_id}] COURSE intent but no open_classroom_payload — "
                    f"using synthesised fallback for topic: '{topic_text[:60]}'"
                )

            if execution_response.open_classroom_payload:
                logger.info(f"🏫 [STREAM][{trace_id}] Sending open_classroom event")
                oc_brick = {
                    "type": "open_classroom",
                    "block": {
                        "type": "OpenClassroomBlock",
                        "content": {
                            "type": "OPEN_CLASSROOM",
                            **execution_response.open_classroom_payload
                        },
                        "priority": 0
                    }
                }
                collected_bricks.append(oc_brick)
                yield f"data: {json.dumps(oc_brick)}\n\n"
                
            # Emit v1 actions event
            action_labels = []
            for action_block in execution_response.next_actions:
                if action_block.content and "actions" in action_block.content:
                    action_labels.extend(action_block.content["actions"])
            if action_labels:
                actions_brick = {
                    "type": "actions",
                    "blocks": [{"type": "CTARow", "content": {"actions": action_labels}, "priority": 0}]
                }
                collected_bricks.append(actions_brick)
                yield f"data: {json.dumps(actions_brick)}\n\n"
            
            # --- Cache the full response (Phase 17) ---
            if 'cache_key' in locals() and cache_key and collected_bricks:
                try:
                    await ai_performance_optimizer.cache_manager.set(
                        "full_response", 
                        key=cache_key, 
                        value=collected_bricks,
                        expire=3600 * 12 # Cache for 12 hours
                    )
                    logger.info(f"💾 [STREAM][{trace_id}] Persisted full response to cache.")
                except Exception as e:
                    logger.warning(f"⚠️ Cache save failed: {e}")

            # Completion signal
            yield "data: [DONE]\n\n"
            logger.info(f"🏁 [STREAM][{trace_id}] Total session time: {time.time()-start_time:.2f}s")

        except Exception as e:
            logger.error(f"💥 [STREAM][{trace_id}] Critical failure: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
