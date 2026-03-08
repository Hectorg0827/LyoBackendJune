"""
Service layer for managing User Goals and their mappings to the Skill Graph.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .goals_models import UserGoal, GoalSkillMapping, GoalProgressSnapshot, GoalStatus
from .goals_schemas import UserGoalCreate, GoalSkillMappingCreate, GoalProgressSnapshotCreate


async def create_user_goal(db: AsyncSession, goal_in: UserGoalCreate) -> UserGoal:
    """Create a new high-level goal for a user."""
    db_goal = UserGoal(
        user_id=goal_in.user_id,
        target=goal_in.target,
        description=goal_in.description,
        status=goal_in.status,
        target_date=goal_in.target_date
    )
    db.add(db_goal)
    await db.commit()
    await db.refresh(db_goal)
    
    if goal_in.skill_mappings:
        for mapping in goal_in.skill_mappings:
            db_mapping = GoalSkillMapping(
                goal_id=db_goal.id,
                skill_id=mapping.skill_id,
                importance_weight=mapping.importance_weight
            )
            db.add(db_mapping)
        await db.commit()
        await db.refresh(db_goal)
        
    return db_goal


async def get_user_goals(db: AsyncSession, user_id: int, status: Optional[GoalStatus] = None) -> List[UserGoal]:
    """Retrieve all goals for a specific user, optionally filtered by status."""
    query = (
        select(UserGoal)
        .where(UserGoal.user_id == user_id)
        .options(
            selectinload(UserGoal.skill_mappings),
            selectinload(UserGoal.progress_snapshots)
        )
    )
    if status is not None:
        query = query.where(UserGoal.status == status)
        
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_goal_status(db: AsyncSession, goal_id: int, new_status: GoalStatus) -> Optional[UserGoal]:
    """Update the status of an existing goal."""
    query = select(UserGoal).where(UserGoal.id == goal_id)
    result = await db.execute(query)
    db_goal = result.scalar_one_or_none()
    
    if db_goal:
        db_goal.status = new_status
        if new_status == GoalStatus.ACHIEVED:
            db_goal.completed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(db_goal)
        
    return db_goal


async def add_goal_skill_mapping(db: AsyncSession, goal_id: int, mapping_in: GoalSkillMappingCreate) -> GoalSkillMapping:
    """Map an additional skill to an existing goal."""
    db_mapping = GoalSkillMapping(
        goal_id=goal_id,
        skill_id=mapping_in.skill_id,
        importance_weight=mapping_in.importance_weight
    )
    db.add(db_mapping)
    await db.commit()
    await db.refresh(db_mapping)
    return db_mapping


async def record_progress_snapshot(db: AsyncSession, goal_id: int, snapshot_in: GoalProgressSnapshotCreate) -> GoalProgressSnapshot:
    """Record a point-in-time snapshot of the user's progress toward the goal."""
    db_snapshot = GoalProgressSnapshot(
        goal_id=goal_id,
        overall_completion_percentage=snapshot_in.overall_completion_percentage,
        momentum_score=snapshot_in.momentum_score
    )
    db.add(db_snapshot)
    await db.commit()
    await db.refresh(db_snapshot)
    return db_snapshot
