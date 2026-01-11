"""
Personalization service with Deep Knowledge Tracing
"""

import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from .models import LearnerState, LearnerMastery, AffectSample, SpacedRepetitionSchedule, AffectState
from .schemas import (
    PersonalizationStateUpdate, KnowledgeTraceRequest, 
    NextActionRequest, NextActionResponse, ActionType, MasteryProfile
)

logger = logging.getLogger(__name__)

class DeepKnowledgeTracer:
    """
    Deep Knowledge Tracing implementation for skill mastery estimation
    """
    
    def __init__(self):
        self.learning_rate = 0.1
        self.forgetting_rate = 0.05
        
    async def update_mastery(
        self,
        db: AsyncSession,
        user_id: int,
        skill_id: str,
        correct: bool,
        time_taken: float,
        hints_used: int
    ) -> float:
        """
        Update skill mastery using DKT algorithm
        """
        # Get or create mastery record
        result = await db.execute(
            select(LearnerMastery).where(
                and_(
                    LearnerMastery.user_id == user_id,
                    LearnerMastery.skill_id == skill_id
                )
            )
        )
        mastery = result.scalar_one_or_none()
        
        if not mastery:
            mastery = LearnerMastery(
                user_id=user_id,
                skill_id=skill_id
            )
            db.add(mastery)
        
        # Update attempts
        mastery.attempts += 1
        if correct:
            mastery.successes += 1
        
        # DKT update rule
        prior = mastery.mastery_level
        
        # Performance signal
        performance = 1.0 if correct else 0.0
        
        # Adjust for hints (hints reduce learning signal)
        performance *= (1.0 - 0.1 * min(hints_used, 5))
        
        # Time factor (faster = better understanding)
        expected_time = 30.0  # seconds
        time_factor = min(expected_time / max(time_taken, 1.0), 2.0)
        performance *= (0.5 + 0.5 * time_factor)
        
        # Bayesian update
        learning_delta = self.learning_rate * (performance - prior)
        forgetting_delta = self.forgetting_rate * (0.5 - prior)
        
        # Update mastery
        new_mastery = prior + learning_delta - forgetting_delta
        mastery.mastery_level = max(0.0, min(1.0, new_mastery))
        
        # Update uncertainty (decreases with more data)
        mastery.uncertainty = max(0.1, mastery.uncertainty * 0.95)
        
        # Update timing
        mastery.last_seen = datetime.utcnow()
        if mastery.avg_time_to_solve:
            mastery.avg_time_to_solve = 0.7 * mastery.avg_time_to_solve + 0.3 * time_taken
        else:
            mastery.avg_time_to_solve = time_taken
        
        mastery.hints_used += hints_used
        
        # Check for mastery achievement
        if mastery.mastery_level >= 0.8 and not mastery.mastery_achieved:
            mastery.mastery_achieved = datetime.utcnow()
        
        await db.commit()
        return mastery.mastery_level
    
    async def get_skill_readiness(
        self,
        db: AsyncSession,
        user_id: int,
        skill_id: str
    ) -> Tuple[float, float]:
        """
        Get readiness to learn a skill (mastery, confidence)
        """
        result = await db.execute(
            select(LearnerMastery).where(
                and_(
                    LearnerMastery.user_id == user_id,
                    LearnerMastery.skill_id == skill_id
                )
            )
        )
        mastery = result.scalar_one_or_none()
        
        if not mastery:
            return 0.0, 0.0
        
        # Factor in forgetting curve
        days_since = (datetime.utcnow() - mastery.last_seen).days
        retention = np.exp(-self.forgetting_rate * days_since)
        
        effective_mastery = mastery.mastery_level * retention
        confidence = 1.0 - mastery.uncertainty
        
        return effective_mastery, confidence

class PersonalizationEngine:
    """
    Main personalization engine coordinating all components
    """
    
    def __init__(self):
        self.dkt = DeepKnowledgeTracer()
        
    async def update_state(
        self,
        db: AsyncSession,
        update: PersonalizationStateUpdate
    ) -> Dict[str, Any]:
        """
        Update learner state with new signals
        """
        # Get or create learner state
        result = await db.execute(
            select(LearnerState).where(
                LearnerState.user_id == update.learner_id
            )
        )
        state = result.scalar_one_or_none()
        
        if not state:
            state = LearnerState(user_id=update.learner_id)
            db.add(state)
        
        # Update affect if provided
        if update.affect:
            state.valence = update.affect.valence
            state.arousal = update.affect.arousal
            state.affect_confidence = update.affect.confidence
            
            # Determine affect state
            if update.affect.valence < -0.3 and update.affect.arousal > 0.5:
                state.current_affect = AffectState.FRUSTRATED
            elif update.affect.valence < 0 and update.affect.arousal < 0.3:
                state.current_affect = AffectState.BORED
            elif update.affect.valence > 0.3 and update.affect.arousal > 0.6:
                state.current_affect = AffectState.FLOW
            else:
                state.current_affect = AffectState.ENGAGED
            
            # Store aggregated sample
            sample = AffectSample(
                user_id=update.learner_id,
                valence=update.affect.valence,
                arousal=update.affect.arousal,
                confidence=update.affect.confidence,
                source=update.affect.source,
                lesson_id=int(update.context.lesson_id) if update.context and update.context.lesson_id else None,
                skill_id=update.context.skill if update.context else None,
                activity_type="unknown"
            )
            db.add(sample)
        
        # Update session state
        if update.session:
            state.fatigue_level = update.session.fatigue
            state.focus_level = update.session.focus
            
            if update.session.duration_minutes and update.session.duration_minutes > 25:
                state.fatigue_level = min(1.0, state.fatigue_level + 0.2)
        
        state.updated_at = datetime.utcnow()
        await db.commit()
        
        return {
            "status": "updated",
            "current_affect": state.current_affect.value,
            "fatigue": state.fatigue_level,
            "focus": state.focus_level,
            "recommendations": await self._get_recommendations(state)
        }

    async def build_prompt_context(
        self,
        db: AsyncSession,
        learner_id: str,
        current_skill: Optional[str] = None
    ) -> str:
        """Build a compact, privacy-preserving learner context block for LLM prompts.

        This reuses existing personalization tables (no parallel memory system).
        Returns an empty string if no learner state exists yet.
        """
        user_id = learner_id

        state_result = await db.execute(
            select(LearnerState).where(LearnerState.user_id == user_id)
        )
        state = state_result.scalar_one_or_none()

        mastery_result = await db.execute(
            select(LearnerMastery)
            .where(LearnerMastery.user_id == user_id)
            .order_by(desc(LearnerMastery.mastery_level))
        )
        masteries = mastery_result.scalars().all()

        if not state and not masteries:
            return ""

        strengths = [m.skill_id for m in masteries if m.mastery_level >= 0.7][:5]
        weaknesses = [m.skill_id for m in masteries if m.mastery_level < 0.3][:5]
        in_progress = [m.skill_id for m in masteries if 0.3 <= m.mastery_level < 0.7][:5]

        readiness_line = ""
        if current_skill:
            mastery, confidence = await self.dkt.get_skill_readiness(db, user_id, current_skill)
            readiness_line = f"Current skill: {current_skill} (effective mastery {mastery:.2f}, confidence {confidence:.2f})"

        parts: List[str] = []

        if state:
            parts.append(
                "Learner preferences: "
                f"pace={state.preferred_pace}, visual={bool(state.prefers_visual)}, audio={bool(state.prefers_audio)}, reading_level={state.reading_level}"
            )
            parts.append(
                "Learner state: "
                f"affect={state.current_affect.value}, fatigue={state.fatigue_level:.2f}, focus={state.focus_level:.2f}"
            )
        if strengths:
            parts.append("Strengths (mastered): " + ", ".join(strengths))
        if in_progress:
            parts.append("In progress: " + ", ".join(in_progress))
        if weaknesses:
            parts.append("Struggling with: " + ", ".join(weaknesses))
        if readiness_line:
            parts.append(readiness_line)

        # Layer 1 continuity: recent chat sessions (authenticated users)
        try:
            from lyo_app.chat.models import ChatConversation, ChatMessage

            conv_result = await db.execute(
                select(ChatConversation)
                .where(ChatConversation.user_id == str(user_id))
                .order_by(desc(ChatConversation.updated_at))
                .limit(2)
            )
            conversations = conv_result.scalars().all()

            session_lines: List[str] = []
            for conv in conversations:
                topic = conv.topic or (conv.context_data or {}).get("topic")
                topic_prefix = f"Topic: {topic}" if topic else "Topic: (unspecified)"

                # Pull last user+assistant turns (compact)
                msg_result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.conversation_id == conv.id)
                    .order_by(desc(ChatMessage.created_at))
                    .limit(4)
                )
                msgs = list(reversed(msg_result.scalars().all()))

                last_user = next((m.content for m in reversed(msgs) if m.role == "user"), "")
                last_assistant = next((m.content for m in reversed(msgs) if m.role == "assistant"), "")

                def _truncate(s: str, n: int) -> str:
                    s = (s or "").strip().replace("\n", " ")
                    return s if len(s) <= n else s[: n - 1] + "…"

                if last_user or last_assistant:
                    session_lines.append(
                        f"- {topic_prefix}. Last time you asked: '{_truncate(last_user, 120)}'. We covered: '{_truncate(last_assistant, 160)}'"
                    )
            if session_lines:
                parts.append("Recent sessions:")
                parts.extend(session_lines)
        except Exception as e:
            logger.debug(f"Skipping chat continuity context: {e}")

        return "\n".join(parts).strip()
    
    async def trace_knowledge(
        self,
        db: AsyncSession,
        request: KnowledgeTraceRequest
    ) -> Dict[str, Any]:
        """
        Update knowledge tracking from assessment
        """
        # Update mastery
        new_mastery = await self.dkt.update_mastery(
            db,
            request.learner_id,
            request.skill_id,
            request.correct,
            request.time_taken_seconds,
            request.hints_used
        )
        
        # Update spaced repetition schedule
        await self._update_repetition_schedule(
            db,
            request.learner_id,
            request.skill_id,
            request.item_id,
            request.correct
        )
        
        return {
            "skill_id": request.skill_id,
            "new_mastery": new_mastery,
            "correct": request.correct,
            "updated": True
        }
    
    async def get_next_action(
        self,
        db: AsyncSession,
        request: NextActionRequest
    ) -> NextActionResponse:
        """
        Determine next best action based on state
        """
        # Get learner state
        result = await db.execute(
            select(LearnerState).where(
                LearnerState.user_id == request.learner_id
            )
        )
        state = result.scalar_one_or_none()
        
        if not state:
            # Default for new learner
            return NextActionResponse(
                action=ActionType.EXPLANATION,
                difficulty="medium",
                reason=["new_learner", "building_baseline"]
            )
        
        # Decision logic based on state
        reasons = []
        
        # Check fatigue
        if state.fatigue_level > 0.7:
            return NextActionResponse(
                action=ActionType.BREAK,
                difficulty="none",
                reason=["high_fatigue", "break_recommended"],
                content={"duration_minutes": 5, "type": "mindfulness"}
            )
        
        # Check affect
        if state.current_affect.value == "frustrated":
            if state.valence < -0.5:
                # High frustration - provide worked example
                return NextActionResponse(
                    action=ActionType.WORKED_EXAMPLE,
                    difficulty="easy",
                    reason=["frustration_detected", "scaffolding_needed"]
                )
            else:
                # Mild frustration - hint
                return NextActionResponse(
                    action=ActionType.HINT,
                    difficulty="current",
                    reason=["mild_frustration", "hint_provided"]
                )
        
        if state.current_affect.value == "bored":
            # Increase challenge
            return NextActionResponse(
                action=ActionType.CHALLENGE,
                difficulty="hard",
                reason=["boredom_detected", "increasing_challenge"]
            )
        
        # Check for spaced repetition
        due_items = await self._get_due_repetitions(db, request.learner_id)
        if due_items:
            return NextActionResponse(
                action=ActionType.REVIEW,
                difficulty="mixed",
                reason=["spaced_repetition_due"],
                spaced_repetition_due=True,
                content={"items": due_items[:3]}
            )
        
        # Default: practice at optimal difficulty
        if request.current_skill:
            mastery, confidence = await self.dkt.get_skill_readiness(
                db, request.learner_id, request.current_skill
            )
            
            if mastery < 0.3:
                difficulty = "easy"
            elif mastery < 0.7:
                difficulty = "medium"
            else:
                difficulty = "hard"
        else:
            difficulty = "medium"
        
        return NextActionResponse(
            action=ActionType.PRACTICE_QUESTION,
            difficulty=difficulty,
            reason=["continue_practice", f"mastery_building"],
            metadata={"optimal_difficulty": state.optimal_difficulty}
        )
    
    async def get_mastery_profile(
        self,
        db: AsyncSession,
        learner_id: str
    ) -> MasteryProfile:
        """
        Get complete mastery profile
        """
        result = await db.execute(
            select(LearnerMastery).where(
                LearnerMastery.user_id == learner_id
            ).order_by(desc(LearnerMastery.mastery_level))
        )
        masteries = result.scalars().all()
        
        skills = {m.skill_id: m.mastery_level for m in masteries}
        strengths = [m.skill_id for m in masteries if m.mastery_level >= 0.7][:5]
        weaknesses = [m.skill_id for m in masteries if m.mastery_level < 0.3][:5]
        
        # Get learner state
        result = await db.execute(
            select(LearnerState).where(
                LearnerState.user_id == learner_id
            )
        )
        state = result.scalar_one_or_none()
        
        return MasteryProfile(
            learner_id=learner_id,
            skills=skills,
            strengths=strengths,
            weaknesses=weaknesses,
            recommended_focus=weaknesses[:3],
            learning_velocity=state.learning_velocity if state else 0.5,
            optimal_difficulty=state.optimal_difficulty if state else 0.5
        )
    
    async def _get_recommendations(self, state: LearnerState) -> List[str]:
        """Generate personalized recommendations"""
        recs = []
        
        if state.fatigue_level > 0.6:
            recs.append("Consider taking a 5-minute break")
        
        if state.current_affect.value == "flow":
            recs.append("You're in the zone! Keep going")
        elif state.current_affect.value == "frustrated":
            recs.append("Try reviewing the fundamentals")
        elif state.current_affect.value == "bored":
            recs.append("Ready for a challenge?")
        
        return recs
    
    async def _update_repetition_schedule(
        self,
        db: AsyncSession,
        user_id: int,
        skill_id: str,
        item_id: str,
        correct: bool
    ):
        """Update spaced repetition schedule"""
        result = await db.execute(
            select(SpacedRepetitionSchedule).where(
                and_(
                    SpacedRepetitionSchedule.user_id == user_id,
                    SpacedRepetitionSchedule.item_id == item_id
                )
            )
        )
        schedule = result.scalar_one_or_none()
        
        if not schedule:
            schedule = SpacedRepetitionSchedule(
                user_id=user_id,
                skill_id=skill_id,
                item_id=item_id
            )
            db.add(schedule)
        
        # SM-2 algorithm
        if correct:
            if schedule.repetitions == 0:
                schedule.interval = 1
            elif schedule.repetitions == 1:
                schedule.interval = 6
            else:
                schedule.interval = int(schedule.interval * schedule.easiness_factor)
            
            schedule.repetitions += 1
            schedule.easiness_factor = max(1.3, schedule.easiness_factor + 0.1)
        else:
            schedule.repetitions = 0
            schedule.interval = 1
            schedule.easiness_factor = max(1.3, schedule.easiness_factor - 0.2)
        
        schedule.last_review = datetime.utcnow()
        schedule.next_review = datetime.utcnow() + timedelta(days=schedule.interval)
        schedule.last_grade = 5 if correct else 2
        
        await db.commit()
    
    async def _get_due_repetitions(
        self,
        db: AsyncSession,
        user_id: int
    ) -> List[str]:
        """Get items due for repetition"""
        result = await db.execute(
            select(SpacedRepetitionSchedule).where(
                and_(
                    SpacedRepetitionSchedule.user_id == user_id,
                    SpacedRepetitionSchedule.next_review <= datetime.utcnow()
                )
            ).limit(10)
        )
        schedules = result.scalars().all()
        
        return [s.item_id for s in schedules]

# Singleton instance
personalization_engine = PersonalizationEngine()
