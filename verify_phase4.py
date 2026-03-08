import asyncio
import logging
from datetime import datetime, timedelta
from lyo_app.core.database import AsyncSessionLocal

# Satisfy SQLAlchemy Mapper
try:
    import lyo_app.ai_study.models
    import lyo_app.models.clips
    import lyo_app.models.social
    import lyo_app.models.enhanced
    import lyo_app.ai_agents.models
    import lyo_app.learning.models
except ImportError:
    pass

from lyo_app.evolution.goals_models import UserGoal, GoalStatus, GoalProgressSnapshot
from lyo_app.personalization.models import LearnerMastery
from lyo_app.auth.models import User
from lyo_app.evolution.intervention_worker import check_trajectory_drops_task
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)

async def seed_test_data():
    print("Seeding test data for Phase 4 verification...")
    async with AsyncSessionLocal() as db:
        # 1. Create a user if not exists (User 1 usually exists)
        # We'll just update User 1 to have a struggle point
        await db.execute(text("UPDATE users SET user_context_summary = '### Challenging Areas:\n- Recursion in Python\n- AsyncIO loops', updated_at = :now WHERE id = 1"), {"now": datetime.utcnow()})
        
        # 2. Add an active goal with a recent negative momentum snapshot
        goal = UserGoal(
            id=999,
            user_id=1,
            target="Master Quantum Computing",
            status=GoalStatus.ACTIVE,
            created_at=datetime.utcnow() - timedelta(days=7),
            updated_at=datetime.utcnow()
        )
        # Check if exists
        res = await db.execute(text("SELECT id FROM user_goals WHERE id = 999"))
        if not res.scalar():
            db.add(goal)
            await db.flush()
        
        snapshot = GoalProgressSnapshot(
            goal_id=999,
            overall_completion_percentage=10.0,
            momentum_score=-1.5,
            recorded_at=datetime.utcnow() - timedelta(hours=2)
        )
        db.add(snapshot)
        
        # 3. Add a decayed skill
        mastery = LearnerMastery(
            user_id=1,
            skill_id="python_basics",
            mastery_level=0.9,
            last_seen=datetime.utcnow() - timedelta(days=45) # 45 days ago -> high decay
        )
        db.add(mastery)
        
        await db.commit()
        print("Test data seeded successfully.")

def run_intervention_check():
    print("Running check_trajectory_drops_task...")
    # This task is a Celery task, but we can call it directly for testing
    # It uses a sync DB session internally via get_sync_db()
    result = check_trajectory_drops_task()
    print(f"Intervention Check Result: {result}")

if __name__ == "__main__":
    asyncio.run(seed_test_data())
    run_intervention_check()
