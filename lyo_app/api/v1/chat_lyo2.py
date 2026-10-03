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
    ConversationTurn, MediaRef, UIBlock, UIBlockType, Intent,
    ActionType, PlannedAction, LyoPlan,
)
from lyo_app.ai.multimodal import (
    canonical_message_content,
    load_media_attachments,
    recent_media_refs,
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
        current_media_supplied = bool(request.media)
        display_content = canonical_message_content(request.text, request.media)
        media_attachments = await load_media_attachments(request.media)
        if not request.text and request.media:
            request.text = "Please analyze the attached material and respond to what it contains."

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
            if display_content:
                await conversation_store.add_message(
                    db,
                    persistent_conversation.id,
                    "user",
                    display_content,
                    client_message_id=request.client_message_id,
                )

        if not media_attachments:
            historical_media = recent_media_refs(request.conversation_history)
            media_attachments = await load_media_attachments(
                historical_media, missing_ok=True
            )
            if media_attachments and historical_media:
                request.media = historical_media

        from lyo_app.teaching_runtime.model_usage import (
            bind_model_usage,
            learning_event_usage_recorder,
        )

        def _model_usage_scope(tier: str):
            conversation_key = (
                getattr(persistent_conversation, "id", None)
                or request.conversation_id
                or request.session_id
                or request.device_id
            )
            return bind_model_usage(
                learning_event_usage_recorder(
                    user_id=authenticated_user_id,
                    surface="chat",
                    session_id=conversation_key,
                    model_tier=tier,
                )
            )

        # 1. Layer A: Multimodal Routing
        logger.info(f"[{trace_id}] Layer A: Routing request for user {current_user.id}")
        with _model_usage_scope("orchestration"):
            routing_response = await router_agent.route(
                request,
                media_attachments=media_attachments,
            )
        decision = routing_response.decision

        from lyo_app.chat.experience import (
            effective_intent,
            fast_lane_plan,
            resolve_interaction_contract,
        )
        interaction_contract = resolve_interaction_contract(
            user_text=request.text or "",
            router_intent=decision.intent,
            has_media=bool(media_attachments),
            has_current_media=current_media_supplied,
            state_summary=request.state_summary,
        )
        contracted_intent = effective_intent(interaction_contract, decision.intent)
        if contracted_intent != decision.intent:
            decision = decision.model_copy(
                update={
                    "intent": contracted_intent,
                    "needs_clarification": False,
                    "clarification_question": None,
                }
            )

        from lyo_app.ai.lesson_composer import slugify_skill
        from lyo_app.teaching_runtime import (
            TeachingAction,
            TeachingSurface,
            decide_for_chat,
            record_policy_decision,
            resolve_chat_teaching_topic,
        )
        _policy_topic = resolve_chat_teaching_topic(
            intent=decision.intent,
            user_text=request.text or "",
            state_summary=request.state_summary,
            router_topic=getattr(getattr(decision, "entities", None), "topic", None),
            router_subject=getattr(getattr(decision, "entities", None), "subject", None),
        )
        _teaching_concept_id = (
            slugify_skill(_policy_topic) if _policy_topic else None
        )

        teaching_decision = await decide_for_chat(
            db=db,
            user_id=authenticated_user_id,
            user_text=request.text or "",
            intent=decision.intent.value if decision.intent else "GENERAL",
            concept_id=_teaching_concept_id,
            topic=_policy_topic,
            history=request.conversation_history,
            state_summary=request.state_summary,
            has_media=bool(media_attachments),
            has_current_media=current_media_supplied,
            interaction_contract={
                **interaction_contract.model_dump(mode="json"),
                "directives": interaction_contract.prompt_directives(),
            },
        )
        await record_policy_decision(
            db,
            user_id=authenticated_user_id,
            trace_id=trace_id,
            surface=TeachingSurface.CHAT,
            decision=teaching_decision,
            concept_id=_teaching_concept_id,
        )

        from lyo_app.chat.context_broker import build_context_bundle
        chat_context_bundle = await build_context_bundle(
            db=db,
            user_id=authenticated_user_id,
            contract=interaction_contract,
            concept_id=_teaching_concept_id,
            topic=_policy_topic,
        )
        
        # Check for clarification gate. A file plus a direct information
        # request already supplies the missing referent, so router-level text
        # ambiguity must not force a question before Lyo inspects the file.
        if (
            decision.needs_clarification
            and not interaction_contract.fast_lane
        ):
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
        if interaction_contract.fast_lane:
            plan = fast_lane_plan(interaction_contract, request.text or "")
        else:
            with _model_usage_scope("orchestration"):
                plan = await planner_agent.plan(request, decision)
        
        # 3. Layer C: Execution
        logger.info(f"[{trace_id}] Layer C: Executing plan")
        executor = LyoExecutor(db)
        with _model_usage_scope(teaching_decision.model_tier):
            execution_response = await executor.execute(
                user_id=str(current_user.id),
                plan=plan,
                original_request=request.text or "",
                conversation_history=[
                    {"role": turn.role, "content": turn.content}
                    for turn in request.conversation_history
                ],
                media_attachments=media_attachments,
                teaching_decision=teaching_decision.model_dump(mode="json"),
                interaction_contract={
                    **interaction_contract.model_dump(mode="json"),
                    "directives": interaction_contract.prompt_directives(),
                },
                context_bundle=chat_context_bundle,
            )
        
        # Add trace metadata
        latency_ms = int((time.time() - start_time) * 1000)
        execution_response.metadata.update({
            "trace_id": trace_id,
            "latency_ms": latency_ms,
            "intent": decision.intent,
            "tier": decision.suggested_tier,
            "conversation_id": request.conversation_id,
            "teaching_policy": teaching_decision.model_dump(mode="json"),
            "interaction_contract": interaction_contract.model_dump(mode="json"),
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{trace_id}] Lyo 2.0 execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {str(e)}"
        )
