from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from .models import SkillDomain

class SkillTagBase(BaseModel):
    tag: str

class SkillTagCreate(SkillTagBase):
    pass

class SkillTagRead(SkillTagBase):
    id: int
    skill_id: int
    
    model_config = ConfigDict(from_attributes=True)

class SkillBase(BaseModel):
    name: str
    domain: SkillDomain
    description: Optional[str] = None
    is_active: bool = True

class SkillCreate(SkillBase):
    tags: Optional[List[str]] = None

class SkillRead(SkillBase):
    id: int
    created_at: datetime
    updated_at: datetime
    tags: List[SkillTagRead] = []
    
    model_config = ConfigDict(from_attributes=True)

class SkillEdgeBase(BaseModel):
    skill_id: int
    prerequisite_skill_id: int
    weight: int = 1

class SkillEdgeCreate(SkillEdgeBase):
    pass

class SkillEdgeRead(SkillEdgeBase):
    id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
