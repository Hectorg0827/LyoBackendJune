import logging
import json
from typing import Optional, Dict, Any, List
from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent, AgentResult
from lyo_app.ai.schemas.lyo2 import RouterDecision, RouterRequest, RouterResponse
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

class MultimodalRouter(BaseAgent[RouterDecision]):
    """
    Layer A: Multimodal Router
    Uses Gemini 2.0 Flash to classify user intent and extract entities.
    Determines if a request is a follow-up to an existing artifact.
    """
    
    def __init__(self):
        super().__init__(
            name="multimodal_router",
            output_schema=RouterDecision,
            model_name="gemini-2.0-flash",  # Stable Gemini 2.0 Flash
            temperature=0.1,  # Low temperature for deterministic behavior
            max_tokens=1024
        )

    def get_system_prompt(self) -> str:
        return """
You are the Lyo 2.0 Multimodal Router. Your job is to analyze user input (text, images, audio references) and decide the best course of action.
Lyo is an Outcome Engine for learning.

## Intents (use EXACTLY one of these values):
- EXPLAIN: User wants a concept explained or has a general question.
- COURSE: User wants to learn/study a topic, create a course, or requests "teach me X". Use this for any learning request that implies structured content.
- QUIZ: User wants to be tested on a topic.
- FLASHCARDS: User wants flashcards for study.
- STUDY_PLAN: User wants a schedule or plan to reach a goal.
- SUMMARIZE_NOTES: User has provided notes and wants a summary.
- SCHEDULE_REMINDERS: User wants to set study reminders.
- COMMUNITY: User wants to interact with the learning community.
- MODIFY_ARTIFACT: User is asking to change an existing quiz, plan, or flashcard set.
- GREETING: User is saying hello, hi, hey, or greeting.
- CHAT: User wants general conversation or small talk.
- HELP: User is asking for help or what Lyo can do.
- GENERAL: Any other request that doesn't fit above categories.
- UNKNOWN: Intent truly cannot be determined.

## suggested_tier (use EXACTLY one of these values):
- TINY: Simple questions, greetings, minor modifications.
- MEDIUM: Most standard requests (standard quiz, explanation).
- LARGE: Complex study plans, high-volume note summarization.

## Guidelines:
1. Detect entities like subject, topic, grade level, and test dates.
2. If the user is replying to an active artifact context, set `is_reply_to_artifact` to true.
3. Set `needs_clarification` to true ONLY if you genuinely cannot determine what the user wants. For greetings, chat, or general questions, set it to false.
4. Do NOT set needs_clarification=true for simple messages like "hello", "teach me X", etc.
5. Extract context from images or audio signals if provided.
6. CRITICAL: When RECENT CONVERSATION HISTORY is provided, treat short answers ("10th grade", "biology", "yes", etc.) as replies to the previous assistant message. Do NOT classify them as UNKNOWN or set needs_clarification=true — use the history to infer intent. For example: if the previous assistant asked "What grade level?" and the user says "10th grade", that is a COURSE reply, not ambiguous.

YOU MUST RESPOND ONLY WITH JSON.
"""

    def build_prompt(self, request: RouterRequest) -> str:
        # Construct the user prompt based on the request
        prompt_parts = []

        # Include recent conversation history FIRST so the LLM has full context
        # before seeing the latest user message. Without this, follow-up replies
        # like "10th grade" or "Biology" are classified with no context and trigger
        # unnecessary clarification questions.
        if request.conversation_history:
            history_lines = []
            for turn in request.conversation_history[-8:]:  # last 8 turns is plenty
                history_lines.append(f"{turn.role.upper()}: {turn.content}")
            prompt_parts.append("RECENT CONVERSATION HISTORY:\n" + "\n".join(history_lines))
        
        if request.text:
            prompt_parts.append(f"USER TEXT: {request.text}")
            
        if request.media:
            prompt_parts.append("MEDIA REFERENCES:")
            for m in request.media:
                prompt_parts.append(f"- Modality: {m.modality}, URI: {m.uri}, Mime: {m.mime_type}")
                
        if request.active_artifact:
            prompt_parts.append(f"ACTIVE ARTIFACT: {request.active_artifact.json()}")
            
        if request.state_summary:
            prompt_parts.append(f"USER STATE SUMMARY: {json.dumps(request.state_summary)}")
            
        return "\n".join(prompt_parts)

    async def route(self, request: RouterRequest) -> RouterResponse:
        """
        Main routing method.
        """
        result = await self.execute(request=request)
        
        if not result.success:
            # Router failed — log the real error for debugging, then use a
            # sensible fallback so the pipeline still produces an answer.
            logger.error(
                f"MultimodalRouter.execute() FAILED — error: {result.error}, "
                f"raw_response: {(result.raw_response or '')[:200]}"
            )
            # Default to EXPLAIN with high confidence so the planner/executor
            # still runs instead of dead-ending with a useless clarification.
            decision = RouterDecision(
                intent="EXPLAIN",
                confidence=0.5,
                needs_clarification=False,
                suggested_tier="MEDIUM"
            )
        else:
            decision = result.data
            
        import uuid
        return RouterResponse(
            decision=decision,
            trace_id=str(uuid.uuid4())
        )
