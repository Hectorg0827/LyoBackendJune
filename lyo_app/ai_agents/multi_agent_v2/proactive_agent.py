"""
Proactive Agent
A specialized A2A agent designed to autonomously draft contextual push notifications 
and interventions when the OS detects a drop in momentum or a new struggle point.
"""

import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from lyo_app.ai_agents.a2a.base import A2ABaseAgent
from lyo_app.ai_agents.a2a.schemas import TaskInput, AgentCapability, ArtifactType, AgentAction
from lyo_app.evolution.goals_models import UserGoal
from lyo_app.auth.models import User

logger = logging.getLogger(__name__)

class ProactiveAgentResponse(BaseModel):
    title: str
    body: str
    action_url: str
    actions: Optional[List[AgentAction]] = None

class ProactiveAgent(A2ABaseAgent[ProactiveAgentResponse]):
    """
    Drafts targeted, context-aware push notifications when the OS detects
    a negative trajectory or a newly formed struggle point.
    """
    
    def __init__(self):
        super().__init__(
            name="ProactiveAgent",
            description="Autonomous agent that drafts push notifications based on trajectory drops.",
            output_schema=ProactiveAgentResponse,
            capabilities=[AgentCapability.TUTORING],
            model_name="gpt-4o-mini", # Fast model preferred for background OS tasks
            temperature=0.7
        )
    
    @property
    def agent_id(self) -> str:
        return "proactive_agent"
        
    def get_output_artifact_type(self) -> ArtifactType:
        return ArtifactType.JSON_DATA
        
    def get_system_prompt(self) -> str:
        return """
You are the Lyo Proactive OS Agent. Your job is to monitor a learner's trajectory and autonomously intervene when they are struggling or losing momentum.
You draft personalized, encouraging, and highly specific push notifications to pull them back into a constructive learning loop.

When writing a notification:
1. **Title**: Keep it short, encouraging, and relevant to the objective.
2. **Body**: Address the specific drop in momentum or struggle point. Be empathetic but actionable (e.g. "I noticed you haven't reviewed system design lately. Want to do a quick 3-minute quiz?").
3. **Action URL**: Provide a deep link. Defaults to 'lyo://dashboard', or 'lyo://chat' if you want them to talk to you.
4. **Agency**: You can also use the following OS tools to help the user:
   - `create_task`: If they need to do something specific.
   - `schedule_event`: If they need to block time for a review.

Output EXACTLY JSON matching the requested schema. No conversational filler.
"""

    def build_prompt(self, task_input: TaskInput, **kwargs) -> str:
        # kwargs might contain dynamic context, but we inject the main trigger via task_input
        user_context = kwargs.get("user_context", "No additional context.")
        goal_name = kwargs.get("goal_name", "your goal")
        
        prompt = f"""{self.get_system_prompt()}

## OS Trigger Event
{task_input.context}

## System Context (Memory Insights)
{user_context}

## Active Goal Focus
{goal_name}

Based on this drop in momentum, draft the push notification.
"""
        return prompt

    async def execute(self, task_input: TaskInput, emit_event: Optional[callable] = None, **kwargs) -> Any:
        """
        Override execute to fetch dynamic goal and user context before building the prompt.
        """
        db = kwargs.get("db")
        # Fetch the user's permanent memory context
        user_id_int = int(task_input.user_id) if task_input.user_id else None
        
        user_context = ""
        goal_name = ""
        
        if user_id_int:
            # Get user context summary
            user_result = await db.execute(select(User).where(User.id == user_id_int))
            user = user_result.scalar_one_or_none()
            if user and user.user_context_summary:
                user_context = user.user_context_summary
                
            # If the context string from task_input has goal_id=X, try to extract and fetch
            # In a real system, we'd pass goal_id explicitely in TaskInput.metadata 
            # For now, we'll try to find any active goal for context as a fallback
            goal_result = await db.execute(
                select(UserGoal)
                .where(UserGoal.user_id == user_id_int)
                .order_by(UserGoal.updated_at.desc())
                .limit(1)
            )
            latest_goal = goal_result.scalar_one_or_none()
            if latest_goal:
                goal_name = latest_goal.target
                
        # Inject into kwargs for build_prompt
        kwargs["user_context"] = user_context
        kwargs["goal_name"] = goal_name
        
        return await super().execute(task_input, emit_event=emit_event, **kwargs)
