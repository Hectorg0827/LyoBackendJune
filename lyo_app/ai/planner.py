import logging
import json
from typing import Optional, Dict, Any, List
from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent, AgentResult
from lyo_app.ai.schemas.lyo2 import LyoPlan, RouterDecision, RouterRequest
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

class LyoPlanner(BaseAgent[LyoPlan]):
    """
    Layer B: Planner
    Converts RouterDecision into a detailed Execution Plan (LyoPlan).
    Determines tools to call, artifacts to create, and constraints.
    """
    
    def __init__(self):
        super().__init__(
            name="lyo_planner",
            output_schema=LyoPlan,
            model_name="gemini-2.5-flash",  # Fast and capable model for planning
            temperature=0.2,
            max_tokens=2048
        )

    def get_system_prompt(self) -> str:
        return """
You are the Lyo 2.0 Planner. Your job is to take a Router Decision and create a step-by-step Execution Plan.
Lyo is an Outcome Engine. Plans should be efficient and focus on the user's ultimate learning goal.

## Action Types you can use:
- RAG_RETRIEVE: Fetch information from the knowledge base using criteria.
- CREATE_ARTIFACT: Create a new version of a Quiz, Study Plan, or Flashcards.
- UPDATE_ARTIFACT: Modify an existing artifact version based on user feedback.
- CALENDAR_SYNC: Propose schedule entries.
- SEARCH_WEB: Use when RAG is insufficient and fresh info is needed.
- GENERATE_TEXT: Generate the final tutor response/explanation.
- GENERATE_AUDIO: Generate a short audio summary (if voice mode might be relevant).

## Planning Rules:
1. Always start with RAG_RETRIEVE if the topic is educational and needs grounding.
2. If the user wants a Quiz/Flashcards, include a CREATE_ARTIFACT step.
3. If intent is MODIFY_ARTIFACT, use UPDATE_ARTIFACT and specify the changes.
4. Final step should usually be GENERATE_TEXT to construct the message to the user.
5. Define safety constraints (e.g., "don't invent historical dates", "keep it beginner level").
6. Specify if grounding is required for the executor.

YOU MUST RESPOND ONLY WITH JSON.
"""

    def build_prompt(self, request: RouterRequest, decision: RouterDecision) -> str:
        # Include conversation history so the planner can make context-aware plans
        history_text = ""
        if request.conversation_history:
            recent = request.conversation_history[-10:]  # Last 10 turns for planning context
            history_text = "\nCONVERSATION HISTORY:\n"
            for turn in recent:
                history_text += f"  {turn.role.upper()}: {turn.content}\n"
        
        return f"""
USER REQUEST:
{request.text}

ROUTER DECISION:
{decision.json()}

USER STATE:
{json.dumps(request.state_summary)}
{history_text}
Create a plan to fulfill this request. Take conversation history into account for continuity.
"""

    async def plan(self, request: RouterRequest, decision: RouterDecision) -> LyoPlan:
        """
        Generate an execution plan.
        """
        result = await self.execute(request=request, decision=decision)
        
        if not result.success:
            logger.error(
                f"LyoPlanner.execute() FAILED — error: {result.error}, "
                f"raw_response: {(result.raw_response or '')[:200]}"
            )
            # Fallback plan: still attempt to answer the user's question
            # directly via text generation rather than giving up.
            return LyoPlan(
                steps=[
                    {"action_type": "GENERATE_TEXT", "description": f"Answer the user's question: {(request.text or '')[:200]}", "parameters": {}}
                ],
                grounding_required=False
            )
            
        return result.data
