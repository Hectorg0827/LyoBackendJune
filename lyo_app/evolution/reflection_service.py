"""
Reflection Service
Harvests and processes qualitative, self-reported data from the member.
Hooks into Memory Synthesis and adjusts the Mastery DKT weights.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from lyo_app.events.models import LearningEvent, EventType
from lyo_app.events.processor import log_learning_event
from lyo_app.events.schemas import LearningEventCreate
from lyo_app.services.memory_synthesis import memory_synthesis_service, MemoryInsight

logger = logging.getLogger(__name__)

class ReflectionPayload(BaseModel):
    user_id: int
    skill_ids: List[int]
    confidence_rating: int  # 1-5 scale
    difficulty_rating: int  # 1-5 scale
    emotional_state: str    # 'flow', 'frustrated', 'bored', 'anxious'
    qualitative_notes: Optional[str] = None
    obstacles_identified: Optional[List[str]] = None

async def process_reflection(db: AsyncSession, payload: ReflectionPayload) -> LearningEvent:
    """
    Ingests a member's reflection, normalizes the qualitative data, 
    and pipes it into the standard LearningEvent Log.
    """
    
    logger.info(f"Processing Reflection for user {payload.user_id} on skills {payload.skill_ids}")
    
    # 1. Normalize the qualitative data into measurable outcomes for the compound loop.
    # A confidence rating of 5 is highly positive vs a 1 which indicates a block.
    confidence_normalized = float(payload.confidence_rating) / 5.0
    
    # 2. Package metadata for Memory Synthesis
    metadata = {
        "difficulty": payload.difficulty_rating,
        "emotion": payload.emotional_state,
        "notes": payload.qualitative_notes,
        "obstacles": payload.obstacles_identified or []
    }
    
    # 3. Create the event and pipe it into the main compound loop
    event_create = LearningEventCreate(
        user_id=payload.user_id,
        event_type=EventType.REFLECTION,
        skill_ids_json=payload.skill_ids,
        metadata_json=metadata,
        measurable_outcome=confidence_normalized
    )
    
    # This automatically triggers DKT/Goals/XP updates in the background
    event = await log_learning_event(db, event_create)
    
    # 4. Asynchronous trigger to Memory Synthesis
    await _trigger_memory_synthesis(payload, db)
    
    return event


async def _trigger_memory_synthesis(payload: ReflectionPayload, db: AsyncSession):
    """
    Pipes the qualitative reflection data into the member's permanent memory block.
    """
    if not payload.qualitative_notes and not payload.obstacles_identified:
        return
        
    logger.info(f"Triggering asynchronous memory synthesis for user {payload.user_id} based on reflection.")
    
    # Map emotion/difficulty into a permanent insight category
    category = "learning_style"
    if payload.emotional_state in ["frustrated", "anxious", "bored"]:
        category = "emotional_pattern"
    elif payload.difficulty_rating >= 4:
        category = "struggle_point"
    elif payload.confidence_rating >= 4:
        category = "success_pattern"
        
    # Construct the content string
    content_parts = []
    if payload.qualitative_notes:
        content_parts.append(f"Noted: '{payload.qualitative_notes}'")
    if payload.obstacles_identified:
        content_parts.append(f"Blocked by: {', '.join(payload.obstacles_identified)}")
    
    insight_content = " | ".join(content_parts)
    
    insight = MemoryInsight(
        category=category,
        content=insight_content,
        confidence=0.9, # High confidence since it's explicitly self-reported
        source="reflection_loop",
        timestamp=datetime.utcnow()
    )
    
    await memory_synthesis_service.update_memory_insight(
        user_id=payload.user_id,
        insight=insight,
        db=db
    )
