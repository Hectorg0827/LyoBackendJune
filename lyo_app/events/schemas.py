from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, ConfigDict
from .models import EventType

class LearningEventBase(BaseModel):
    event_type: EventType
    skill_ids_json: Optional[List[Any]] = None
    metadata_json: Optional[Dict[str, Any]] = None
    measurable_outcome: Optional[float] = None

    # ── Evidence ─────────────────────────────────────────────────────────
    # What this event proves about one concept. All optional: events that
    # carry no graded evidence (reflections, voice turns) simply omit them
    # and contribute no rung. See lyo_app/events/evidence.py.
    concept_id: Optional[str] = None
    #: A ladder rung. Accepts the classroom's wire vocabulary too — the
    #: processor normalizes "retrieval" to "retention" before storing.
    evidence_type: Optional[str] = None
    evidence_confidence: Optional[float] = None
    hints_used: int = 0
    misconception: Optional[str] = None
    source_surface: Optional[str] = None

class LearningEventCreate(LearningEventBase):
    user_id: int

class LearningEventRead(LearningEventBase):
    id: int
    user_id: int
    timestamp: datetime
    processed_for_mastery: int
    
    model_config = ConfigDict(from_attributes=True)
