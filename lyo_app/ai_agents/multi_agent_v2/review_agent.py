"""
Weekly Review Agent
A specialized agent designed to handle the WEEKLY_REVIEW intent.
Instead of tutoring a specific subject, it acts as an executive coach 
analyzing the member's Goal Trajectory and Event History.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from lyo_app.ai_agents.a2a.base import A2ABaseAgent
from lyo_app.ai_agents.a2a.schemas import TaskInput, TaskOutput, TaskStatus, MessageRole, AgentCapability, ArtifactType
from pydantic import BaseModel

from lyo_app.evolution.goals_models import UserGoal, GoalStatus
from lyo_app.evolution.goals_service import get_user_goals
from lyo_app.events.models import LearningEvent

logger = logging.getLogger(__name__)

class WeeklyReviewAgentResponse(BaseModel):
    content: str
    
class WeeklyReviewAgent(A2ABaseAgent[WeeklyReviewAgentResponse]):
    """
    Acts as an executive OS coach.
    Analyzes active goals and learning events to provide macro feedback.
    """
    
    def __init__(self):
        super().__init__(
            name="WeeklyReviewAgent",
            description="Executive OS coach that analyzes Goal Trajectories and Event History.",
            output_schema=WeeklyReviewAgentResponse,
            capabilities=[AgentCapability.TUTORING],
            model_name="gemini-1.5-pro", # Can be overridden by AI Orchestrator
            temperature=0.7
        )
    
    @property
    def agent_id(self) -> str:
        return "weekly_review_agent"
        
    def get_output_artifact_type(self) -> ArtifactType:
        return ArtifactType.TEXT_CONTENT
        
    def get_system_prompt(self) -> str:
        return """
You are the Lyo Executive Coach. The member has requested a Weekly Review of their OS Trajectory.
You are not here to teach a specific lesson. You are here to zoom out and analyze their momentum.

Review the provided Data Context containing:
- Their active Life/Capability Goals
- Their recent Learning Events from the past 7 days

Your objective:
1. Summarize their weekly momentum (where did they spend time, what did they achieve).
2. Look for gaps: are they neglecting a specific Active Goal?
3. Provide one concrete, high-level recommendation (a 'Next Best Upgrade') for their upcoming week.

Be encouraging, analytical, and direct. Use the insight that Lyo is their Personal Self-Evolution OS.
"""

    def build_prompt(self, task_input: TaskInput, **kwargs) -> str:
        trajectory_data = kwargs.get("trajectory_data", {})
        data_context = f"OS Trajectory Data:\n{trajectory_data}"
        
        user_msg = task_input.user_message or "Give me my weekly review"
        return f"{self.get_system_prompt()}\n\n{data_context}\n\nMember Request: {user_msg}"

    async def _fetch_trajectory_data(self, db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """Gather the member's OS context for the past week."""
        # 1. Fetch Goals
        active_goals = await get_user_goals(db, user_id, status=GoalStatus.ACTIVE)
        goals_data = [{"id": g.id, "target": g.target} for g in active_goals]
        
        # 2. Fetch Recent Events
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        result = await db.execute(
            select(LearningEvent)
            .where(LearningEvent.user_id == user_id)
            .where(LearningEvent.timestamp >= seven_days_ago)
        )
        recent_events = result.scalars().all()
        
        events_summary = {}
        for event in recent_events:
            event_type = event.event_type.value
            events_summary[event_type] = events_summary.get(event_type, 0) + 1
            
        return {
            "active_goals": goals_data,
            "events_last_7_days": events_summary,
            "total_events": len(recent_events)
        }

    async def execute(self, task: TaskInput, **kwargs) -> TaskOutput:
        """Execute the weekly review analysis."""
        try:
            # Note: the A2ABaseAgent doesn't natively bubble up the DB Session to execute() 
            # In a real environment, we'd inject this. For the sake of the review agent 
            # we will create an ad-hoc session if none provided in metadata.
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy.orm import sessionmaker
            from lyo_app.core.config import settings
            
            engine = create_async_engine(settings.database_url)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session() as db:
                user_id = int(task.user_id) if task.user_id and str(task.user_id).isdigit() else 0
                
                if user_id > 0:
                    trajectory_data = await self._fetch_trajectory_data(db, user_id)
                else:
                    trajectory_data = {"active_goals": [], "events_last_7_days": {}, "total_events": 0}
                
            # Build the specific prompt for this run using the required A2A method
            prompt = self.build_prompt(task, trajectory_data=trajectory_data)
            
            # Send to LLM
            # Since this is a macro-review, we prefer a capable model
            from lyo_app.ai_agents.orchestrator import ai_orchestrator, ModelType, TaskComplexity
            
            llm_response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.COMPLEX,
                model_preference=ModelType.CLAUDE_3_5_SONNET,
                max_tokens=800
            )
            
            content = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
            
            return TaskOutput(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                response_message=content
            )
            
        except Exception as e:
            logger.error(f"WeeklyReviewAgent execution failed: {e}")
            return TaskOutput(
                task_id=task.task_id if task else "unknown",
                status=TaskStatus.FAILED,
                error_message=str(e),
                response_message="I'm having trouble pulling your trajectory data right now. Let's try your weekly review a bit later."
            )
