import logging
from typing import Optional, List, Any, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import LearningEvent, EventType
from .schemas import LearningEventCreate

# Assume we eventually inject dependencies for XP Service, Goals Service, and DKT Service
from lyo_app.evolution.goals_service import get_user_goals, record_progress_snapshot
from lyo_app.evolution.goals_schemas import GoalProgressSnapshotCreate
from lyo_app.personalization.service import personalization_engine
from lyo_app.personalization.schemas import PersonalizationStateUpdate, AffectSignals
from lyo_app.personalization.models import LearnerMastery
from lyo_app.services.memory_synthesis import MemorySynthesisService, MemoryInsight

logger = logging.getLogger(__name__)

async def log_learning_event(db: AsyncSession, event_in: LearningEventCreate) -> LearningEvent:
    """
    Core entrypoint for logging a new learning event.
    Logs the event to the DB and triggers the compounding growth loop.
    """
    db_event = LearningEvent(
        user_id=event_in.user_id,
        event_type=event_in.event_type,
        skill_ids_json=event_in.skill_ids_json,
        metadata_json=event_in.metadata_json,
        measurable_outcome=event_in.measurable_outcome
    )
    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)
    
    # Trigger the background processing for the compounding evolution loop
    # In a real distributed system, this would be pushed to Celery/Redis
    await _process_evolution_loop(db, db_event)
    
    return db_event


async def _process_evolution_loop(db: AsyncSession, event: LearningEvent):
    """
    Executes the self-evolution background job for a given event.
    Coordinates updates across:
    1. DKT (Deep Knowledge Tracing) Mastery Engine
    2. Gamification (XP / Streaks)
    3. Goals Trajectory Engine
    4. Memory Synthesis (via AI background task)
    """
    try:
        logger.info(f"Processing Evolution Loop for user {event.user_id}, event {event.id}")
        
        # 1. Update DKT Mastery
        if event.skill_ids_json:
            for skill_id in event.skill_ids_json:
                # Convert the measurable outcome (e.g. normalized confidence) to a 'correct' boolean for the DKT logic
                is_positive_event = (event.measurable_outcome or 0.0) >= 0.5
                
                # We use a default time_taken of 30s and 0 hints for reflection/generic events
                await personalization_engine.dkt.update_mastery(
                    db=db,
                    user_id=event.user_id,
                    skill_id=str(skill_id),
                    correct=is_positive_event,
                    time_taken=30.0,
                    hints_used=0
                )
        
        # 2. Update Gamification (XP)
        # Example: await gamification_service.award_xp_for_event(event)

        # 3. Update Goals Trajectory
        # Fetch active goals related to this event's skills and recalculate momentum/completion
        if event.skill_ids_json:
            active_goals = await get_user_goals(db, user_id=event.user_id)
            for goal in active_goals:
                # Naive check: does this goal map to any skills in the event?
                goal_skill_ids = [mapping.skill_id for mapping in goal.skill_mappings]
                if any(skill_id in goal_skill_ids for skill_id in event.skill_ids_json):
                    # Calculate real completion % from DKT mastery averages for goal skills
                    mastery_sum = 0.0
                    mastery_count = 0
                    for gsk in goal_skill_ids:
                        m_row = await db.execute(
                            select(LearnerMastery.mastery_level).where(
                                LearnerMastery.user_id == event.user_id,
                                LearnerMastery.skill_id == str(gsk),
                            )
                        )
                        m_val = m_row.scalar_one_or_none()
                        mastery_sum += (m_val or 0.0)
                        mastery_count += 1

                    completion_pct = (mastery_sum / mastery_count * 100.0) if mastery_count else 0.0
                    # Momentum: positive if new event has good outcome, else flat
                    momentum = 1.5 if (event.measurable_outcome or 0.0) >= 0.5 else 0.5

                    snapshot = GoalProgressSnapshotCreate(
                        overall_completion_percentage=min(100.0, completion_pct),
                        momentum_score=momentum,
                    )
                    await record_progress_snapshot(db, goal.id, snapshot)
        
        # 4. Handle Voice Interactions (Live Context)
        if event.event_type == EventType.VOICE_INTERACTION:
            await _process_voice_interaction(db, event)

        # Mark as processed
        event.processed_for_mastery = 1
        await db.commit()
        
    except Exception as e:
        logger.error(f"Failed to process evolution loop for event {event.id}: {str(e)}")
        event.processed_for_mastery = -1
        await db.commit()

async def _process_voice_interaction(db: AsyncSession, event: LearningEvent):
    """
    Specific processor for voice interactions.
    Updates affect state and extracts memory insights.
    """
    meta = event.metadata_json or {}
    transcript = meta.get("transcript", "")
    emotion = meta.get("emotion_signals", {})
    
    # 1. Update Learner Affect State
    if emotion:
        update = PersonalizationStateUpdate(
            learner_id=str(event.user_id),
            affect=AffectSignals(
                valence=emotion.get("valence", 0.0),
                arousal=emotion.get("arousal", 0.5),
                confidence=emotion.get("confidence", 0.8),
                source=["voice_tone", "sentiment"]
            )
        )
        await personalization_engine.update_state(db, update)

    # 2. Update Long-term Memory
    if transcript:
        memory_service = MemorySynthesisService()
        insight = MemoryInsight(
            category="emotional_pattern" if emotion else "topic_interest",
            content=f"Voice interaction transcript: {transcript}",
            confidence=0.8,
            source="voice_interaction",
            timestamp=event.timestamp
        )
        await memory_service.update_memory_insight(event.user_id, insight, db)
