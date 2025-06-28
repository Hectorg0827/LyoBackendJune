import asyncio
from lyo_app.core.celery_app import celery_app
from lyo_app.ai_agents.sentiment_agent import sentiment_engagement_agent
from lyo_app.ai_agents.mentor_agent import AIMentor
from lyo_app.core.database import get_db_session

@celery_app.task(name="ai.analyze_activity")
def analyze_user_activity_task(user_id: int, action: str, metadata: dict, user_message: str = None):
    """Celery task to analyze user activity asynchronously with AI agents."""
    async def run():
        async with get_db_session() as db:
            # 1. Sentiment & engagement analysis
            await sentiment_engagement_agent.analyze_user_action(
                user_id=user_id,
                action=action,
                metadata=metadata,
                db=db,
                user_message=user_message
            )
            
            # 2. Proactive mentoring if needed
            mentor = AIMentor()
            # Call proactive check-in based on analyzed action
            try:
                await mentor.proactive_check_in(
                    user_id=user_id,
                    reason=action,
                    db=db
                )
            except Exception as e:
                # Log mentor errors but do not fail the task
                print(f"Error in proactive_check_in for user {user_id}: {e}")
    asyncio.run(run())
