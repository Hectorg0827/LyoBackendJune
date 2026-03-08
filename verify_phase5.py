import asyncio
import json
import logging
from datetime import datetime

# Satisfy SQLAlchemy Mapper & OS Agency
try:
    import lyo_app.ai_study.models
    import lyo_app.models.clips
    import lyo_app.models.social
    import lyo_app.models.enhanced
    import lyo_app.ai_agents.models
    import lyo_app.learning.models
    from lyo_app.ai_agents.multi_agent_v2.tools import tool_registry
except ImportError:
    pass

from lyo_app.core.database import AsyncSessionLocal
from lyo_app.ai_agents.multi_agent_v2.proactive_agent import ProactiveAgent
from lyo_app.ai_agents.a2a.schemas import TaskInput
from lyo_app.models.enhanced import Task
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_phase5")

async def test_proactive_agency():
    print("--- Phase 5: OS Agency Verification ---")
    agent = ProactiveAgent()
    
    async with AsyncSessionLocal() as db:
        # Create a trigger message simulating Phase 4 detection
        task_input = TaskInput(
            user_id="1",
            user_message="User is stuck on Python Recursion. Momentum score dropped to -2.0.",
            context="The OS detected a significant struggle point in Python Recursion. Immediate intervention required.",
            include_thinking=True
        )
        
        print("Executing ProactiveAgent with Agency enabled...")
        output = await agent.execute(task_input, db=db)
        
        print(f"\nTask Status: {output.status}")
        print(f"Agent Response Message: {output.response_message}")
        if output.error_message:
            print(f"Error Message: {output.error_message}")

        if not output.output_artifacts:
            print("\nFAILURE: No artifacts produced.")
            return

        artifact = output.output_artifacts[0]
        data = artifact.data
        print(f"Drafted Notification Title: {data.get('title')}")
        print(f"Drafted Notification Body: {data.get('body')}")
        
        actions = data.get("actions", [])
        if actions:
            print(f"\nAgent requested {len(actions)} actions:")
            for action in actions:
                print(f" - Tool: {action.get('tool_name')}")
                print(f" - Parameters: {action.get('parameters')}")
        else:
            print("\nWARNING: Agent did not request any autonomous actions.")

        # Check the database for the created task if 'create_task' was triggered
        res = await db.execute(
            select(Task)
            .where(Task.user_id == 1)
            .where(Task.task_type == "member_action")
            .order_by(Task.created_at.desc())
        )
        tasks = res.scalars().all()
        
        if tasks:
            print(f"\nSUCCESS: Found {len(tasks)} OS-triggered tasks in the database.")
            latest = tasks[0]
            print(f"Latest Task Title: {latest.task_params.get('title')}")
        else:
            print("\nFAILURE: No member_action tasks found in DB.")

if __name__ == "__main__":
    asyncio.run(test_proactive_agency())
