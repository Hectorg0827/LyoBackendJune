from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from .goals_models import GoalStatus

class GoalSkillMappingBase(BaseModel):
    skill_id: int
    importance_weight: float = 1.0

class GoalSkillMappingCreate(GoalSkillMappingBase):
    pass

class GoalSkillMappingRead(GoalSkillMappingBase):
    id: int
    goal_id: int
    
    model_config = ConfigDict(from_attributes=True)

class GoalProgressSnapshotBase(BaseModel):
    overall_completion_percentage: float
    momentum_score: float

class GoalProgressSnapshotCreate(GoalProgressSnapshotBase):
    pass

class GoalProgressSnapshotRead(GoalProgressSnapshotBase):
    id: int
    goal_id: int
    recorded_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class UserGoalBase(BaseModel):
    target: str
    description: Optional[str] = None
    status: GoalStatus = GoalStatus.ACTIVE
    target_date: Optional[datetime] = None

class UserGoalCreate(UserGoalBase):
    user_id: int
    skill_mappings: Optional[List[GoalSkillMappingCreate]] = None

class UserGoalRead(UserGoalBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    skill_mappings: List[GoalSkillMappingRead] = []
    progress_snapshots: List[GoalProgressSnapshotRead] = []
    
    model_config = ConfigDict(from_attributes=True)
