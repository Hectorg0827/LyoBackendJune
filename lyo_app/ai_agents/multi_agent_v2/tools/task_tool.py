"""
Task Tool for the Lyo OS.
Allows agents to create and manage personal tasks for the member.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from .base import BaseTool, ToolResult
from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.models.enhanced import Task, TaskState
import uuid

class TaskParameters(BaseModel):
    title: str = Field(..., description="The title of the task.")
    description: Optional[str] = Field(None, description="Detailed description of what needs to be done.")
    priority: str = Field("medium", description="Priority level (low, medium, high).")
    due_date: Optional[str] = Field(None, description="Due date in ISO format (YYYY-MM-DD).")

class TaskTool(BaseTool):
    """
    Tool to create and manage personal tasks in the Lyo OS.
    """
    name = "create_task"
    description = "Create a new personal task for the member in their Evolution dashboard."
    parameters_schema = TaskParameters

    async def execute(self, user_id: int, db: AsyncSession = None, **kwargs) -> ToolResult:
        title = kwargs.get("title")
        description = kwargs.get("description", "")
        
        if not db:
            return ToolResult(
                success=False,
                output=None,
                message="Database session required for TaskTool."
            )

        try:
            # We reuse the enhanced Task model with a specific type
            new_task = Task(
                user_id=user_id,
                idempotency_key=str(uuid.uuid4()),
                task_type="member_action",
                task_params={
                    "title": title,
                    "description": description,
                    "priority": kwargs.get("priority", "medium"),
                    "due_date": kwargs.get("due_date")
                },
                state=TaskState.QUEUED,
                message=f"Action created by Lyo OS: {title}"
            )
            
            db.add(new_task)
            await db.commit()
            
            return ToolResult(
                success=True,
                output={"task_id": new_task.id},
                message=f"Successfully created task: {title}"
            )
        except Exception as e:
            await db.rollback()
            return ToolResult(
                success=False,
                output=None,
                message=f"Failed to create task: {str(e)}"
            )
