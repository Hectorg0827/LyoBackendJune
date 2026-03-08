"""
Autonomous Intervention Engine Worker
Scans user trajectories and memory insights to trigger proactive interventions.
"""

import logging
from datetime import datetime, timedelta

from celery import current_task
from sqlalchemy import select, func, and_

from lyo_app.core.celery_app import celery_app
from lyo_app.tasks.proactive_engagement import get_sync_db, run_async
from lyo_app.evolution.goals_models import UserGoal, GoalStatus, GoalProgressSnapshot
from lyo_app.personalization.models import LearnerMastery
from lyo_app.auth.models import User
import math

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="lyo_app.evolution.intervention_worker.check_trajectory_drops")
def check_trajectory_drops_task(self):
    """
    Background worker that runs daily across all active accounts.
    Fetches UserGoal momentum scores and triggers the ProactiveAgent
    if thresholds are breached (e.g., negative momentum).
    """
    logger.info("Running autonomous intervention check for trajectory drops...")
    db = get_sync_db()
    
    try:
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        
        # We look for snapshots created in the last 24 hours that show negative momentum
        result = db.execute(
            select(
                GoalProgressSnapshot.goal_id,
                UserGoal.user_id,
                GoalProgressSnapshot.momentum_score
            )
            .join(UserGoal, GoalProgressSnapshot.goal_id == UserGoal.id)
            .where(
                and_(
                    UserGoal.status == GoalStatus.ACTIVE,
                    GoalProgressSnapshot.recorded_at >= last_24h,
                    GoalProgressSnapshot.momentum_score < 0.0
                )
            )
        )
        
        breached_snapshots = result.fetchall()
        logger.info(f"Found {len(breached_snapshots)} goals with negative momentum")
        
        queued_count = 0
        for goal_id, user_id, momentum in breached_snapshots:
            # Trigger proactive agent
            trigger_proactive_agent_task.delay(
                user_id=user_id,
                goal_id=goal_id,
                trigger_reason="momentum_drop",
                context_data={"momentum_score": momentum}
            )
            queued_count += 1
            
        # 2. Check for DKT Mastery Decay
        # We look for skills where effective mastery has dropped below 0.6
        # Formula: retention = exp(-0.023 * days_since)
        mastery_results = db.execute(
            select(LearnerMastery)
            .where(LearnerMastery.mastery_level >= 0.7) # Previously mastered
        )
        
        for mastery in mastery_results.scalars().all():
            days_since = (now - mastery.last_seen).days
            retention = math.exp(-0.023 * days_since)
            effective_mastery = mastery.mastery_level * retention
            
            if effective_mastery < 0.6:
                trigger_proactive_agent_task.delay(
                    user_id=mastery.user_id,
                    goal_id=0, # General mastery intervention
                    trigger_reason="mastery_decay",
                    context_data={"skill_id": mastery.skill_id, "decayed_score": effective_mastery}
                )
                queued_count += 1

        # 3. Check for struggle points in Memory Insights
        # We check users updated in the last 24h for "Challenging Areas"
        struggle_users = db.execute(
            select(User)
            .where(
                and_(
                    User.updated_at >= last_24h,
                    User.user_context_summary.like('%Challenging Areas:%')
                )
            )
        )
        
        for user in struggle_users.scalars().all():
            trigger_proactive_agent_task.delay(
                user_id=user.id,
                goal_id=0,
                trigger_reason="struggle_detected",
                context_data={"memory_summary": user.user_context_summary[:200]}
            )
            queued_count += 1
            
        return {
            "status": "success",
            "goals_checked": len(breached_snapshots),
            "interventions_queued": queued_count
        }
        
    except Exception as e:
        logger.exception(f"Trajectory intervention check failed: {e}")
        raise
    finally:
        db.close()

@celery_app.task(bind=True, name="lyo_app.evolution.intervention_worker.trigger_proactive_agent")
def trigger_proactive_agent_task(
    self, 
    user_id: int, 
    goal_id: int, 
    trigger_reason: str,
    context_data: dict
):
    """
    Instantiates the ProactiveAgent to draft and send a targeted push notification.
    """
    logger.info(f"Triggering ProactiveAgent for user {user_id} (Reason: {trigger_reason})")
    
    try:
        async def _run_agent():
            # We will implement this agent next in lyo_app/ai_agents/multi_agent_v2/proactive_agent.py
            from lyo_app.ai_agents.multi_agent_v2.proactive_agent import ProactiveAgent
            from lyo_app.tasks.proactive_engagement import AsyncSessionLocal
            from lyo_app.tasks.notifications import send_push_notification_task
            from lyo_app.ai_agents.a2a.schemas import TaskInput
            
            async with AsyncSessionLocal() as db_session:
                agent = ProactiveAgent()
                
                # We simulate an A2A task input outlining the trigger
                input_data = TaskInput(
                    objective="Generate an autonomous push notification addressing the user's trajectory drop.",
                    context=f"User {user_id} had a negative trajectory on Goal {goal_id}. Reason: {trigger_reason}, Score: {context_data.get('momentum_score', 'N/A')}",
                    user_id=str(user_id)
                )
                
                # Execute agent autonomously
                result = await agent.execute(
                    task_input=input_data,
                    db=db_session
                )
                
                if result.is_success and result.artifacts:
                    # Parse the generated push notification
                    import json
                    from pydantic import ValidationError
                    
                    try:
                        # Depending on how the artifact is formatted, we assume it's JSON content
                        notification_data = json.loads(result.artifacts[0].content)
                        title = notification_data.get("title", "Lyo OS Update")
                        body = notification_data.get("body", "")
                        action_url = notification_data.get("action_url", "lyo://dashboard")
                    except (json.JSONDecodeError, AttributeError):
                        # Fallback parsing
                        title = "Your Learning Trajectory"
                        body = result.artifacts[0].content[:200]
                        action_url = "lyo://dashboard"
                    
                    send_push_notification_task.delay(
                        user_id=str(user_id),
                        title=title,
                        body=body,
                        data={
                            "type": "proactive_intervention",
                            "action_url": action_url
                        }
                    )
                    return True
                else:
                    logger.warning(f"ProactiveAgent failed to generate notification for user {user_id}")
                    return False

        result = run_async(_run_agent())
        return {"status": "sent" if result else "failed", "user_id": user_id}

    except Exception as e:
        logger.exception(f"Failed to run ProactiveAgent for user {user_id}: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=2)
