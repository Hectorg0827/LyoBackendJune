import asyncio
import logging
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from lyo_app.core.database import AsyncSessionLocal, engine
from lyo_app.auth.models import User
# Pre-import related models to avoid SQLAlchemy mapper errors
try:
    import lyo_app.ai_study.models
    import lyo_app.learning.models
    import lyo_app.models.enhanced
    import lyo_app.models.clips
    import lyo_app.models.social
    import lyo_app.ai_agents.models
except ImportError:
    pass

from lyo_app.events.models import LearningEvent, EventType
from lyo_app.events.processor import log_learning_event
from lyo_app.events.schemas import LearningEventCreate
from lyo_app.personalization.models import LearnerState, AffectState, LearnerMastery
from lyo_app.services.memory_synthesis import MemorySynthesisService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_phase6():
    print("\n--- Phase 6: Live OS (Multimodal & Affect-Aware) Verification ---\n")
    
    async with AsyncSessionLocal() as db:
        # 1. Setup - Create or find a test user
        result = await db.execute(select(User).where(User.username == "phase6_tester"))
        user = result.scalar_one_or_none()
        
        if not user:
            print("Creating test user...")
            user = User(
                email="phase6@example.com",
                username="phase6_tester",
                hashed_password="hashed_password",
                first_name="Phase6",
                last_name="Tester"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        user_id = user.id

        # 2. Reset LearnerState to defaults (ENGAGED)
        result = await db.execute(select(LearnerState).where(LearnerState.user_id == user_id))
        state = result.scalar_one_or_none()
        if not state:
            state = LearnerState(user_id=user_id, current_affect=AffectState.ENGAGED)
            db.add(state)
        else:
            state.current_affect = AffectState.ENGAGED
            state.valence = 0.0
            state.arousal = 0.5
        await db.commit()
        print(f"User {user_id} LearnerState reset to ENGAGED.")

        # 3. Simulate a VOIC_INTERACTION with Frustration
        print("\nStep 1: Logging Frustrated Voice Interaction...")
        voice_event = LearningEventCreate(
            user_id=user_id,
            event_type=EventType.VOICE_INTERACTION,
            metadata_json={
                "transcript": "I don't understand binary search trees at all, it's so frustrating and confusing!",
                "emotion_signals": {
                    "valence": -0.8,
                    "arousal": 0.9,
                    "confidence": 0.95
                }
            }
        )
        
        await log_learning_event(db, voice_event)
        
        # Verify LearnerState Update
        await db.refresh(state)
        print(f"Detected Affect: {state.current_affect.value}")
        assert state.current_affect == AffectState.FRUSTRATED, "Should have detected FRUSTRATED state"

        # 4. Simulate a Learning Event (Quiz Answer) and verify Affect-Responsive DKT
        print("\nStep 2: Monitoring Affect-Responsive DKT Mastery Update...")
        # Get prior mastery
        result = await db.execute(select(LearnerMastery).where(
            and_(LearnerMastery.user_id == user_id, LearnerMastery.skill_id == "binary_trees")
        ))
        mastery_record = result.scalar_one_or_none()
        prior_uncertainty = mastery_record.uncertainty if mastery_record else 0.5
        
        quiz_event = LearningEventCreate(
            user_id=user_id,
            event_type=EventType.QUIZ_ANSWER,
            skill_ids_json=["binary_trees"],
            measurable_outcome=1.0, # Correct answer
            metadata_json={"time_spent": 45}
        )
        
        await log_learning_event(db, quiz_event)
        
        # Refresh mastery record
        result = await db.execute(select(LearnerMastery).where(
            and_(LearnerMastery.user_id == user_id, LearnerMastery.skill_id == "binary_trees")
        ))
        mastery_record = result.scalar_one()
        
        print(f"New Mastery Level: {mastery_record.mastery_level:.4f}")
        print(f"New Uncertainty: {mastery_record.uncertainty:.4f} (Prior: {prior_uncertainty:.4f})")
        
        # Due to FRUSTRATED affect, uncertainty should INCREASE or decrease LESS than normal
        # Normally it would be uncertainty * 0.95. For FRUSTRATED it's * 1.1.
        assert mastery_record.uncertainty > prior_uncertainty * 0.95, "Uncertainty should be higher due to frustration"
        print("✅ Affect-Responsive Weighting verified (Uncertainty remained high due to frustration).")

        # 5. Verify Memory Insight Generation
        print("\nStep 3: Verifying Memory Insight Generation...")
        # Check if user.user_context_summary contains the transcript or a synthesis of it
        # Actually, since MemorySynthesisService._save_user_memory saves to user.user_context_summary
        await db.refresh(user)
        print(f"User Memory Blob: {user.user_context_summary[:100]}...")
        assert "Voice interaction transcript" in user.user_context_summary or "frustrating" in user.user_context_summary.lower()
        print("✅ Voice-to-Memory synthesis verified.")

    print("\n--- Phase 6 Verification SUCCESS ---")

if __name__ == "__main__":
    asyncio.run(verify_phase6())
