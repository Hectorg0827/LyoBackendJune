"""
Global OS Context Manager
Centralizes the fetching and injection of user MemoryInsights and Goal trajectories
into AI prompts to ensure the OS understands the member's permanent profile.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from lyo_app.auth.models import User
from lyo_app.evolution.goals_models import UserGoal, GoalStatus

# Required to resolve the 'User' relationship mappings
try:
    import lyo_app.ai_study.models
    import lyo_app.models.clips
    import lyo_app.models.social
    import lyo_app.models.enhanced
    import lyo_app.ai_agents.models
    import lyo_app.learning.models
except ImportError:
    pass

class GlobalContextBuilder:
    """
    Builds the OS context block to be injected into LLM System Prompts.
    """
    
    @staticmethod
    async def build_os_context(user_id: Optional[int], db: AsyncSession) -> str:
        """
        Fetches the member's persistent memory and active macro-goals.
        Returns a formatted string.
        """
        if not user_id:
            return ""
            
        try:
            # 1. Fetch MemoryInsights (user_context_summary)
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            memory_profile = user.user_context_summary if user and user.user_context_summary else "No permanent memory profile established yet."
            
            # 2. Fetch Active Goals
            goals_result = await db.execute(
                select(UserGoal)
                .where(UserGoal.user_id == user_id)
                .where(UserGoal.status == GoalStatus.ACTIVE)
            )
            goals = goals_result.scalars().all()
            goals_list = [f"- {g.target}" for g in goals] if goals else ["- General Learning (No active goals set)"]
            goals_str = "\n".join(goals_list)
            
            context = f"""
### GLOBAL OS PROFILE ###
You are communicating within the Personal Self-Evolution OS.

**Member Memory Profile & Insights:**
{memory_profile}

**Member's Active Macro-Goals:**
{goals_str}
#########################
"""
            return context
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to build OS context for user {user_id}: {e}")
            return ""

global_context_builder = GlobalContextBuilder()
