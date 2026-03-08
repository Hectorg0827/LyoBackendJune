from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, ConfigDict
from .models import EventType

class LearningEventBase(BaseModel):
    event_type: EventType
    skill_ids_json: Optional[List[Any]] = None
    metadata_json: Optional[Dict[str, Any]] = None
    measurable_outcome: Optional[float] = None

class LearningEventCreate(LearningEventBase):
    user_id: int

class LearningEventRead(LearningEventBase):
    id: int
    user_id: int
    timestamp: datetime
    processed_for_mastery: int
    
    model_config = ConfigDict(from_attributes=True)
