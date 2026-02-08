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

## Intents:
- EXPLAIN: User wants a concept explained.
- QUIZ: User wants to be tested on a topic.
- FLASHCARDS: User wants flashcards for study.
- STUDY_PLAN: User wants a schedule or plan to reach a goal.
- SUMMARIZE_NOTES: User has provided notes and wants a summary.
- SCHEDULE_REMINDERS: User wants to set study reminders.
- COMMUNITY: User wants to interact with the learning community.
- MODIFY_ARTIFACT: User is asking to change an existing quiz, plan, or flashcard set (e.g., "too hard", "make it shorter").
- UNKNOWN: Intent cannot be determined.

## Guidelines:
1. Detect entities like subject, topic, grade level, and test dates.
2. If the user is replying to an active artifact context, set `is_reply_to_artifact` to true and detect the intent (often MODIFY_ARTIFACT).
3. Determine if clarification is needed before proceeding. If so, provide a single, targeted question.
4. Suggest a processing tier (TINY, MEDIUM, LARGE) based on complexity.
   - TINY: Simple questions, minor modifications.
   - MEDIUM: Most standard requests (standard quiz, explanation).
   - LARGE: Complex study plans, high-volume note summarization.
5. Extract context from images or audio signals if provided in the description.

YOU MUST RESPOND ONLY WITH JSON.
"""

    def build_prompt(self, request: RouterRequest) -> str:
        # Construct the user prompt based on the request
        prompt_parts = []
        
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
            # Fallback to UNKNOWN if routing fails
            decision = RouterDecision(
                intent="UNKNOWN",
                confidence=0.0,
                needs_clarification=True,
                clarification_question="I'm sorry, I'm having trouble understanding. Could you rephrase that?"
            )
        else:
            decision = result.data
            
        import uuid
        return RouterResponse(
            decision=decision,
            trace_id=str(uuid.uuid4())
        )
