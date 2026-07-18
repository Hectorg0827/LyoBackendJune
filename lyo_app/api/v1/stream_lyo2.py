import logging
import asyncio
import json
import uuid
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user_or_guest, get_db
from lyo_app.auth.schemas import UserRead
from lyo_app.ai.router import MultimodalRouter
from lyo_app.ai.planner import LyoPlanner
from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai.schemas.lyo2 import RouterRequest, ConversationTurn, UIBlock, UIBlockType, UnifiedChatResponse, ActionType, PlannedAction, Intent, RouterDecision, LyoPlan
from lyo_app.ai.schemas.smart_block import SmartBlock, QuizOption
try:
    from lyo_app.ai_agents.multi_agent_v2.agents.test_prep_agent import TestPrepAgent
except ModuleNotFoundError as exc:
    logger = logging.getLogger(__name__)
    logger.warning("Test prep agent module unavailable; using fallback clarification flow: %s", exc)

    class _FallbackTestPrepData:
        subject = None
        topics = []
        test_date = None
        readiness = None
        has_materials = False
        missing_critical_info = ["subject", "topics"]
        follow_up_question = (
            "What subject is your test on, and what topics should we focus on? "
            "You can also upload notes, a study guide, or a syllabus."
        )

    class TestPrepAgent:
        async def analyze_test_prep(self, request):
            from types import SimpleNamespace
            return SimpleNamespace(success=True, data=_FallbackTestPrepData())
from lyo_app.core.config import settings
from lyo_app.services.proactive_engagement import proactive_engagement_service
from lyo_app.ai_agents.optimization.performance_optimizer import ai_performance_optimizer, OptimizationLevel
from lyo_app.chat.models import ChatMode
from lyo_app.chat.stores import conversation_store

# Simple response builder to fix missing import
class LyoResponseBuilder:
    @staticmethod
    def build_command(command_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": command_type,
            "payload": payload
        }

    @staticmethod
    def build(command: Dict[str, Any], request_id: str, conversation_id: str) -> Dict[str, Any]:
        return {
            "command": command,
            "request_id": request_id,
            "conversation_id": conversation_id,
            "timestamp": time.time()
        }

lyo_response_builder = LyoResponseBuilder()

logger = logging.getLogger(__name__)

def safe_json_serialize(data: Any, event_type: str = "unknown") -> str:
    """
    Safely serialize data to JSON string with comprehensive error handling.

    This prevents iOS crashes from __SwiftValue serialization errors by:
    1. Using default=str to handle non-serializable types
    2. Double-encoding to ensure final output is JSON-safe
    3. Providing detailed error logging for debugging

    Args:
        data: The data to serialize
        event_type: Description of the event type for error logging

    Returns:
        JSON string that is guaranteed to be iOS-safe

    Raises:
        ValueError: If data cannot be made JSON-safe even with fallbacks
    """
    try:
        # First pass: Convert problematic types to strings
        intermediate = json.loads(json.dumps(data, default=str))

        # Second pass: Final JSON serialization
        result = json.dumps(intermediate)

        logger.debug(f"✅ Safe JSON serialization successful for {event_type}")
        return result

    except (TypeError, ValueError, OverflowError) as e:
        logger.error(f"❌ JSON serialization failed for {event_type}: {e}")
        logger.error(f"Problematic data type: {type(data)}")
        logger.error(f"Problematic data sample: {str(data)[:200]}")

        # Ultimate fallback: return a safe error message
        fallback = {
            "type": "serialization_error",
            "message": f"Data serialization failed for {event_type}",
            "error": str(e),
            "timestamp": time.time()
        }

        try:
            return json.dumps(fallback)
        except Exception as fallback_error:
            logger.critical(f"💥 Even fallback serialization failed: {fallback_error}")
            raise ValueError(f"Complete JSON serialization failure: {fallback_error}")

def yield_safe_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """
    Yield a Server-Sent Event with guaranteed JSON safety.

    Args:
        event_type: The SSE event type
        data: The event data payload

    Returns:
        SSE-formatted string ready for streaming
    """
    try:
        safe_json = safe_json_serialize(data, event_type)
        return f"data: {safe_json}\n\n"
    except ValueError as e:
        logger.error(f"Failed to create safe SSE event for {event_type}: {e}")
        # Return a safe error event
        error_data = {
            "type": "error",
            "message": f"Event serialization failed: {event_type}"
        }
        return f"data: {json.dumps(error_data)}\n\n"

import re as _re

def _to_smart_blocks(
    answer_text: Optional[str], artifact: Optional[UIBlock]
) -> List[Dict[str, Any]]:
    """Convert a plain answer plus optional legacy UIBlock artifact into
    SmartBlock dicts — the unified block vocabulary all three clients render.
    Unknown artifact types are skipped rather than guessed at."""
    blocks: List[Dict[str, Any]] = []
    if answer_text:
        blocks.append(SmartBlock.text(answer_text).model_dump())

    if artifact is None:
        return blocks
    content = artifact.content or {}

    if artifact.type == UIBlockType.QUIZ:
        options: List[QuizOption] = []
        for i, opt in enumerate(content.get("options", [])):
            # Planner output is loose: options arrive as plain strings or as
            # dicts that may lack the "id" QuizOption requires.
            if isinstance(opt, str):
                options.append(QuizOption(id=str(i), text=opt))
            elif isinstance(opt, dict):
                options.append(
                    QuizOption(id=str(opt.get("id", i)), text=str(opt.get("text", "")))
                )
        blocks.append(
            SmartBlock.quiz(
                question=str(content.get("question", "")),
                options=options,
                correct_index=int(content.get("correct_index", 0)),
                explanation=content.get("explanation"),
                hint=content.get("hint"),
            ).model_dump()
        )
    elif artifact.type == UIBlockType.FLASHCARDS:
        for card in content.get("cards", []):
            if isinstance(card, dict):
                blocks.append(
                    SmartBlock.flashcard(
                        front=str(card.get("front", "")),
                        back=str(card.get("back", "")),
                    ).model_dump()
                )
    elif artifact.type == UIBlockType.STUDY_PLAN:
        plan = content.get("plan") or content.get("text") or ""
        if plan:
            blocks.append(SmartBlock.text(str(plan), subtype="summary").model_dump())

    return blocks


def _extract_course_topic(user_text: str) -> str:
    topic = _re.sub(
        r"^(create (a )?course (on|about|for)?|make (a )?course (on|about|for)?|"
        r"build (a )?course (on|about|for)?|teach me( about| on)?|"
        r"i want (a )?course (on|about)?|course on|course about|"
        r"give me a course( on)?|a course on)\s*",
        "", user_text.strip(), flags=_re.IGNORECASE,
    ).strip()
    return topic or user_text.strip()

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
            # Resolve one server-owned conversation before any AI work.  The
            # bearer identity, never a client-supplied user_id, owns the row.
            persistent_conversation = None
            assistant_client_message_id = None
            replayed_assistant = None
            authenticated_user_id = (
                str(current_user.id) if getattr(current_user, "id", 0) not in (0, "0", None) else None
            )
            if authenticated_user_id:
                if request.conversation_id:
                    persistent_conversation = await conversation_store.get_owned_conversation(
                        db, request.conversation_id, authenticated_user_id
                    )
                    if persistent_conversation is None:
                        # A new client can begin with a provisional local UUID.
                        # Adopt a server UUID and announce it below.
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

                # Server history is canonical.  Clients can omit local history
                # and resume seamlessly after reinstall, refresh, or device swap.
                persisted_history = await conversation_store.get_messages(
                    db, persistent_conversation.id, limit=30
                )
                request.conversation_history = [
                    ConversationTurn(role=message.role, content=message.content)
                    for message in persisted_history
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
                    replayed_assistant = await conversation_store.get_message_by_client_id(
                        db,
                        persistent_conversation.id,
                        assistant_client_message_id,
                    )
                if request.text:
                    await conversation_store.add_message(
                        db,
                        persistent_conversation.id,
                        role="user",
                        content=request.text,
                        mode_used=ChatMode.GENERAL.value,
                        client_message_id=request.client_message_id,
                    )
                yield yield_safe_sse_event(
                    "conversation",
                    {
                        "type": "conversation",
                        "conversation_id": persistent_conversation.id,
                    },
                )
                if replayed_assistant:
                    yield yield_safe_sse_event(
                        "answer",
                        {
                            "type": "answer",
                            "block": {
                                "type": "TutorMessageBlock",
                                "content": {"text": replayed_assistant.content},
                                "priority": 0,
                            },
                            "replayed": True,
                        },
                    )
                    yield "data: [DONE]\n\n"
                    return

            collected_bricks = []
            
            skeleton_brick = {"type": "skeleton", "blocks": ["answer", "artifact"]}
            collected_bricks.append(skeleton_brick)
            yield yield_safe_sse_event("skeleton", skeleton_brick)
            await asyncio.sleep(0.01) # Yield to event loop
            
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
            # Personalized/multi-turn answers must never be served from the
            # global prompt cache: the cache key does not encode user history.
            cached_full_resp = None
            if not authenticated_user_id:
                cached_full_resp = await ai_performance_optimizer.cache_manager.get(
                    "full_response", key=cache_key
                )
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
                    # 2b. Fetch Proactive Nudges (New for Phase 16)
                    proactive_context = ""
                    try:
                        nudges = await proactive_engagement_service.get_pending_nudges_for_user(current_user.id, db)
                        if nudges:
                            proactive_context = "\n**Proactive System Nudges (Incorporate these into your greeting if relevant):**\n"
                            for n in nudges:
                                proactive_context += f"- [{n.nudge_type}] {n.title}: {n.message}\n"
                            # Append to request text for the router/planner/executor to see
                            request.text = f"[Proactive Context: {proactive_context}]\n" + (request.text or "")
                    except Exception as ne:
                        logger.warning(f"Failed to fetch proactive nudges: {ne}")

                    routing_response = await asyncio.wait_for(router_agent.route(request), timeout=35.0)
                    decision = routing_response.decision
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
                oc_event_data = {'type': 'open_classroom', 'block': {'type': 'OpenClassroomBlock', 'content': {'type': 'OPEN_CLASSROOM', **_preview_oc}}}
                yield yield_safe_sse_event("open_classroom_preview", oc_event_data)
                
                # v2: emit lyo_command for iOS v2 pipeline
                try:
                    cmd = lyo_response_builder.build_command("open_classroom", _preview_oc)
                    lyo_resp = lyo_response_builder.build(command=cmd, request_id=trace_id, conversation_id=trace_id)
                    brick_data = {"type": "lyo_command", "response": lyo_resp}
                    collected_bricks.append(brick_data)
                    yield yield_safe_sse_event("lyo_command", brick_data)
                except (TypeError, ValueError) as e:
                    logger.error(f"JSON serialization error for lyo_command: {e}")
                    # Continue without this brick
                    
                logger.info(f"🏫 [STREAM][{trace_id}] Fast course preview sent for: '{_topic[:60]}'")
            
            if decision.needs_clarification and decision.confidence > 0.3:
                # Only ask for clarification if the router is reasonably confident
                # that it truly cannot understand. Low-confidence clarifications
                # from fallback routing should not block the pipeline.
                logger.info(f"🤔 [STREAM][{trace_id}] Needs clarification: {decision.clarification_question}")
                if persistent_conversation and decision.clarification_question:
                    await conversation_store.add_message(
                        db,
                        persistent_conversation.id,
                        role="assistant",
                        content=decision.clarification_question,
                        mode_used=ChatMode.GENERAL.value,
                        client_message_id=assistant_client_message_id,
                    )
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
                        if persistent_conversation:
                            await conversation_store.add_message(
                                db,
                                persistent_conversation.id,
                                role="assistant",
                                content=data.follow_up_question,
                                mode_used=ChatMode.TEST_PREP.value,
                                client_message_id=assistant_client_message_id,
                            )
                        yield f"data: {json.dumps({'type': 'clarification', 'text': data.follow_up_question})}\n\n"
                        return
                    # Optionally attach extracted data back to the request for the planner
                    request.text += f"\n[System: Extracted Test details: Subject={data.subject}, Topics={data.topics}, Date={data.test_date}]"

            # 3. Layer B: Planning
            logger.info(f"📋 [STREAM][{trace_id}] Starting Planning (Intent: {decision.intent})...")
            p_start = time.time()
            try:
                # OPTIMIZATION: Fast Path for simple intents
                if decision.intent in [Intent.GREETING, Intent.CHAT] and decision.confidence > 0.7:
                    logger.info(f"⚡ [STREAM][{trace_id}] Fast Path: Skipping Planner for {decision.intent}")
                    plan = LyoPlan(steps=[
                        PlannedAction(
                            action_type=ActionType.GENERATE_TEXT,
                            description=f"Handle {decision.intent.value} request directly",
                            parameters={"content": None}
                        )
                    ])
                else:
                    plan = await asyncio.wait_for(planner_agent.plan(request, decision), timeout=25.0)
            except asyncio.TimeoutError:
                logger.error(f"❌ [STREAM][{trace_id}] Planning timed out after 25s")
                # Fallback plan
                plan = LyoPlan(steps=[
                    PlannedAction(
                        action_type=ActionType.GENERATE_TEXT,
                        description="Fallback generation after planner timeout",
                        parameters={"content": None}
                    )
                ])
            
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
                yield yield_safe_sse_event("answer", answer_brick)
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

                # Safe JSON serialization using the new helper
                artifact_event_data = {'type': 'artifact', 'block': tagged_artifact.model_dump()}
                yield yield_safe_sse_event("artifact", artifact_event_data)

            # Unified SmartBlock emission: same content as the legacy
            # answer/artifact events above, in the versioned block vocabulary
            # shared by all three clients. Additive — v1 consumers ignore it.
            smart_blocks = _to_smart_blocks(
                raw_llm_text, execution_response.artifact_block
            )
            if smart_blocks:
                yield yield_safe_sse_event(
                    "smart_blocks", {"type": "smart_blocks", "blocks": smart_blocks}
                )

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
                try:
                    from lyo_app.ai_classroom.conversation_flow import get_conversation_manager, ConversationSession
                    cm = get_conversation_manager()
                    
                    oc_payload = execution_response.open_classroom_payload
                    # Ensure oc_payload has a 'course' dict (sometimes it's nested in payload, sometimes it's direct)
                    if isinstance(oc_payload, dict) and "course" in oc_payload:
                        cinfo = oc_payload["course"]
                        s_id = cinfo.get("id")
                        c_topic = cinfo.get("topic")
                        
                        if s_id:
                            sess = ConversationSession(
                                session_id=str(s_id),
                                user_id=getattr(request, "user_id", "guest_session")
                            )
                            sess.current_topic = c_topic
                            sess.current_course_id = str(s_id)
                            cm._sessions[str(s_id)] = sess
                            logger.info(f"💾 Stored ConversationSession({s_id}) for topic '{c_topic}'")
                except Exception as e:
                    logger.error(f"Failed to save cm session: {e}", exc_info=True)

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
            if (
                not authenticated_user_id
                and 'cache_key' in locals()
                and cache_key
                and collected_bricks
            ):
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

            if persistent_conversation and raw_llm_text:
                await conversation_store.add_message(
                    db,
                    persistent_conversation.id,
                    role="assistant",
                    content=raw_llm_text,
                    mode_used=decision.intent.value.lower() if decision.intent else ChatMode.GENERAL.value,
                    client_message_id=assistant_client_message_id,
                )

            # Completion signal
            yield "data: [DONE]\n\n"
            logger.info(f"🏁 [STREAM][{trace_id}] Total session time: {time.time()-start_time:.2f}s")

        except Exception as e:
            logger.error(f"💥 [STREAM][{trace_id}] Critical failure: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
