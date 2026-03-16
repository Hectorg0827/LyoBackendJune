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
from lyo_app.personalization.models import LearnerState

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
    async def build_os_context(user_id: Optional[int], db: AsyncSession, query: Optional[str] = None) -> str:
        """
        Fetches the member's persistent memory and active macro-goals.
        Returns a formatted string.
        """
        if not user_id:
            return ""
            
        try:
            # 1. Fetch Static Memory Profile (user_context_summary)
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            memory_profile = user.user_context_summary if user and user.user_context_summary else "No permanent memory profile established yet."
            
            # 1b. Fetch Affective State (New for Phase 16)
            affect_str = "Neutral"
            learner_result = await db.execute(select(LearnerState).where(LearnerState.user_id == user_id))
            learner = learner_result.scalar_one_or_none()
            if learner:
                affect_str = f"{learner.current_affect.value} (Valence: {learner.valence}, Arousal: {learner.arousal})"
            
            # 2. Fetch Relevant RAG Insights (New for Phase 15)
            rag_insights = ""
            if query:
                try:
                    from lyo_app.services.rag_service import RAGService
                    rag = RAGService(db)
                    relevant_insights = await rag.retrieve_user_memory(user_id, query, limit=5)
                    if relevant_insights:
                        rag_insights = "\n**Relevant Insights for Current Topic:**\n"
                        # Include IDs for potential agent tool calls (manage_memory delete/update)
                        rag_insights += "\n".join([f"- [ID:{i['id']}][{i['category']}] {i['insight']}" for i in relevant_insights])
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"RAG retrieval failed in context builder: {e}")

            # 3. Fetch Active Goals
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

**Current Affective State:** {affect_str}
{rag_insights}

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
