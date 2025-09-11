"""
Production tasks API routes.
Background task tracking and management.
"""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from lyo_app.core.database import get_db
from lyo_app.models.production import User, Task
from lyo_app.auth.production import require_user

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class TaskResponse(BaseModel):
    id: str
    task_type: str
    status: str
    progress: float = 0.0
    result: Dict[str, Any] = None
    error: str = None
    metadata: Dict[str, Any] = None
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    task_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """
    List user's background tasks.
    """
    try:
        query = select(Task).where(Task.user_id == current_user.id)
        
        # Filter by task type if provided
        if task_type:
            query = query.where(Task.task_type == task_type)
            
        # Filter by status if provided
        if status:
            query = query.where(Task.status == status)
            
        query = query.offset(skip).limit(limit).order_by(Task.created_at.desc())
        
        result = await db.execute(query)
        tasks = result.scalars().all()
        
        task_responses = []
        for task in tasks:
            task_responses.append(TaskResponse(
                id=str(task.id),
                task_type=task.task_type,
                status=task.status,
                progress=task.progress,
                result=task.result,
                error=task.error,
                metadata=task.metadata,
                created_at=task.created_at.isoformat(),
                updated_at=task.updated_at.isoformat()
            ))
        
        return task_responses
        
    except Exception as e:
        logger.error(f"Task listing error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list tasks")


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get specific task details.
    """
    try:
        query = select(Task).where(
            Task.id == task_id,
            Task.user_id == current_user.id
        )
        
        result = await db.execute(query)
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return TaskResponse(
            id=str(task.id),
            task_type=task.task_type,
            status=task.status,
            progress=task.progress,
            result=task.result,
            error=task.error,
            metadata=task.metadata,
            created_at=task.created_at.isoformat(),
            updated_at=task.updated_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get task error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get task")


@router.delete("/{task_id}")
async def cancel_task(
    task_id: UUID,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel a running task.
    """
    try:
        query = select(Task).where(
            Task.id == task_id,
            Task.user_id == current_user.id
        )
        
        result = await db.execute(query)
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task.status in ["completed", "failed", "cancelled"]:
            raise HTTPException(status_code=400, detail="Task cannot be cancelled")
        
        # Update task status to cancelled
        task.status = "cancelled"
        task.error = "Cancelled by user"
        
        await db.commit()
        
        logger.info(f"Task cancelled: {task_id} by {current_user.email}")
        
        return {"message": "Task cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Task cancellation error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Task cancellation failed")
