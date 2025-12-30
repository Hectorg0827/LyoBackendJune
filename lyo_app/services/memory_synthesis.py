"""
Memory Synthesis Service - Long-term User Memory for AI Companion

This service transforms Lyo from a stateless tool into an indispensable companion
by maintaining persistent memory of user interactions, learning patterns, and
personal context across sessions.

The memory blob is a concise, structured summary that gets injected into every
AI session, making the AI feel like it truly knows the user.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_

from lyo_app.auth.models import User
from lyo_app.ai_agents.models import MentorInteraction, UserEngagementState
from lyo_app.ai_agents.orchestrator import ai_orchestrator, TaskComplexity, ModelType
from lyo_app.personalization.models import LearnerState, LearnerMastery, SpacedRepetitionSchedule

logger = logging.getLogger(__name__)


@dataclass
class MemoryInsight:
    """A single insight extracted from user interactions."""
    category: str  # learning_style, emotional_pattern, topic_interest, struggle_point, success_pattern
    content: str
    confidence: float  # 0-1
    source: str  # session, quiz, course, community
    timestamp: datetime


@dataclass
class UserMemory:
    """Complete memory profile for a user."""
    user_id: int
    summary: str  # The concise memory blob for AI prompts
    learning_style: Dict[str, Any]
    emotional_patterns: List[str]
    topic_interests: List[str]
    struggle_points: List[str]
    success_patterns: List[str]
    preferred_tone: str
    communication_style: str
    recent_wins: List[str]
    last_updated: datetime
    version: int


class MemorySynthesisService:
    """
    Synthesizes long-term memory from user interactions.

    This is the core service that makes Lyo feel like it "knows" the user.
    It aggregates signals from:
    - Mentor chat sessions
    - Quiz performance
    - Course progress
    - Engagement patterns
    - Emotional states

    And produces a concise memory blob that's injected into every AI session.
    """

    # Memory blob constraints
    MAX_SUMMARY_WORDS = 300
    MAX_INSIGHTS_PER_CATEGORY = 5
    SYNTHESIS_PROMPT_TEMPLATE = """You are a memory synthesis AI. Your job is to create a concise, personal profile
of a learner based on their interaction history. This profile will be used by an AI tutor to personalize
every future interaction.

## User Interaction Data:
{interaction_data}

## Current Profile (if exists):
{current_profile}

## Instructions:
Create a concise memory profile (max 300 words) that captures:

1. **Learning Style**: How do they learn best? (visual, examples, step-by-step, etc.)
2. **Communication Preference**: Do they prefer casual or formal? Quick answers or detailed explanations?
3. **Emotional Patterns**: When do they get frustrated? What motivates them?
4. **Strengths**: What topics/skills come easily to them?
5. **Struggle Points**: What concepts do they find difficult? What analogies helped?
6. **Recent Progress**: What breakthroughs or wins have they had recently?
7. **Personal Context**: Any relevant life context (student, professional, time constraints, etc.)

Write in second person ("You prefer...", "You've shown...") so the AI tutor can reference it naturally.
Be specific and actionable. Avoid generic statements.

## Memory Profile:"""

    def __init__(self):
        self.insights_cache: Dict[int, List[MemoryInsight]] = {}

    async def synthesize_session_memory(
        self,
        user_id: int,
        session_id: str,
        db: AsyncSession
    ) -> Optional[str]:
        """
        Synthesize memory from a completed session.
        Called as a post-session Celery task.

        Returns the updated memory summary.
        """
        try:
            # Get user's current memory profile
            user = await self._get_user(user_id, db)
            if not user:
                logger.error(f"User {user_id} not found for memory synthesis")
                return None

            current_memory = user.user_context_summary or ""

            # Get session interactions
            interactions = await self._get_session_interactions(user_id, session_id, db)
            if not interactions:
                logger.info(f"No interactions found for session {session_id}")
                return current_memory

            # Get supporting context
            learner_state = await self._get_learner_state(user_id, db)
            recent_mastery = await self._get_recent_mastery_changes(user_id, db)
            engagement_patterns = await self._get_engagement_patterns(user_id, db)

            # Build interaction data for synthesis
            interaction_data = self._format_interaction_data(
                interactions=interactions,
                learner_state=learner_state,
                mastery_changes=recent_mastery,
                engagement_patterns=engagement_patterns
            )

            # Generate updated memory using AI
            updated_memory = await self._generate_memory_synthesis(
                interaction_data=interaction_data,
                current_profile=current_memory
            )

            # Save updated memory
            await self._save_user_memory(user_id, updated_memory, db)

            logger.info(f"Memory synthesized for user {user_id}, session {session_id}")
            return updated_memory

        except Exception as e:
            logger.exception(f"Failed to synthesize memory for user {user_id}: {e}")
            return None

    async def synthesize_full_memory(
        self,
        user_id: int,
        db: AsyncSession,
        lookback_days: int = 30
    ) -> Optional[str]:
        """
        Full memory synthesis from all recent interactions.
        Used for periodic refresh or initial profile creation.
        """
        try:
            user = await self._get_user(user_id, db)
            if not user:
                return None

            # Get all interactions in lookback period
            since = datetime.utcnow() - timedelta(days=lookback_days)
            interactions = await self._get_all_interactions(user_id, since, db)

            # Get comprehensive context
            learner_state = await self._get_learner_state(user_id, db)
            all_mastery = await self._get_all_mastery(user_id, db)
            engagement_patterns = await self._get_engagement_patterns(user_id, db)
            spaced_rep_data = await self._get_spaced_repetition_summary(user_id, db)

            # Build comprehensive interaction data
            interaction_data = self._format_comprehensive_data(
                interactions=interactions,
                learner_state=learner_state,
                all_mastery=all_mastery,
                engagement_patterns=engagement_patterns,
                spaced_rep=spaced_rep_data,
                user=user
            )

            # Generate fresh memory synthesis
            updated_memory = await self._generate_memory_synthesis(
                interaction_data=interaction_data,
                current_profile=user.user_context_summary or ""
            )

            await self._save_user_memory(user_id, updated_memory, db)
            return updated_memory

        except Exception as e:
            logger.exception(f"Failed full memory synthesis for user {user_id}: {e}")
            return None

    async def get_memory_for_prompt(
        self,
        user_id: int,
        db: AsyncSession
    ) -> str:
        """
        Get the memory blob formatted for injection into AI prompts.
        This is called at the start of every AI session.
        """
        user = await self._get_user(user_id, db)
        if not user or not user.user_context_summary:
            return self._get_default_memory()

        return f"""
## About This Student (from our previous sessions):
{user.user_context_summary}

## How to Use This Memory:
- Reference their past successes when they struggle
- Adapt your teaching style to their preferences
- Acknowledge their progress and growth
- Avoid approaches that haven't worked for them
"""

    async def update_memory_insight(
        self,
        user_id: int,
        insight: MemoryInsight,
        db: AsyncSession
    ) -> bool:
        """
        Add a specific insight to user memory.
        Called when important learning moments are detected.
        """
        try:
            user = await self._get_user(user_id, db)
            if not user:
                return False

            # Parse current memory into structured format
            current_insights = self._parse_memory_to_insights(user.user_context_summary or "")

            # Add new insight
            current_insights.append(insight)

            # Prune old/low-confidence insights
            pruned_insights = self._prune_insights(current_insights)

            # Re-synthesize memory with new insight
            updated_memory = self._insights_to_memory(pruned_insights)

            await self._save_user_memory(user_id, updated_memory, db)
            return True

        except Exception as e:
            logger.exception(f"Failed to update memory insight for user {user_id}: {e}")
            return False

    # ==================== Private Methods ====================

    async def _get_user(self, user_id: int, db: AsyncSession) -> Optional[User]:
        """Fetch user from database."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _get_session_interactions(
        self,
        user_id: int,
        session_id: str,
        db: AsyncSession
    ) -> List[MentorInteraction]:
        """Get all interactions from a specific session."""
        result = await db.execute(
            select(MentorInteraction)
            .where(
                and_(
                    MentorInteraction.user_id == user_id,
                    MentorInteraction.session_id == session_id
                )
            )
            .order_by(MentorInteraction.timestamp)
        )
        return result.scalars().all()

    async def _get_all_interactions(
        self,
        user_id: int,
        since: datetime,
        db: AsyncSession
    ) -> List[MentorInteraction]:
        """Get all interactions since a date."""
        result = await db.execute(
            select(MentorInteraction)
            .where(
                and_(
                    MentorInteraction.user_id == user_id,
                    MentorInteraction.timestamp >= since
                )
            )
            .order_by(desc(MentorInteraction.timestamp))
            .limit(100)  # Cap at 100 most recent
        )
        return result.scalars().all()

    async def _get_learner_state(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Optional[LearnerState]:
        """Get user's learner state."""
        result = await db.execute(
            select(LearnerState).where(LearnerState.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _get_recent_mastery_changes(
        self,
        user_id: int,
        db: AsyncSession,
        days: int = 7
    ) -> List[LearnerMastery]:
        """Get mastery records that changed recently."""
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(LearnerMastery)
            .where(
                and_(
                    LearnerMastery.user_id == user_id,
                    LearnerMastery.last_seen >= since
                )
            )
            .order_by(desc(LearnerMastery.last_seen))
            .limit(20)
        )
        return result.scalars().all()

    async def _get_all_mastery(
        self,
        user_id: int,
        db: AsyncSession
    ) -> List[LearnerMastery]:
        """Get all mastery records for user."""
        result = await db.execute(
            select(LearnerMastery)
            .where(LearnerMastery.user_id == user_id)
            .order_by(desc(LearnerMastery.mastery_level))
            .limit(50)
        )
        return result.scalars().all()

    async def _get_engagement_patterns(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Analyze engagement patterns from interaction history."""
        # Get state distribution over last 30 days
        since = datetime.utcnow() - timedelta(days=30)

        result = await db.execute(
            select(MentorInteraction)
            .where(
                and_(
                    MentorInteraction.user_id == user_id,
                    MentorInteraction.timestamp >= since
                )
            )
        )
        interactions = result.scalars().all()

        # Analyze patterns
        sentiment_sum = 0
        sentiment_count = 0
        helpful_count = 0
        total_rated = 0

        for inter in interactions:
            if inter.sentiment_detected is not None:
                sentiment_sum += inter.sentiment_detected
                sentiment_count += 1
            if inter.was_helpful is not None:
                total_rated += 1
                if inter.was_helpful:
                    helpful_count += 1

        return {
            "total_interactions": len(interactions),
            "avg_sentiment": sentiment_sum / sentiment_count if sentiment_count > 0 else 0,
            "helpfulness_rate": helpful_count / total_rated if total_rated > 0 else None,
            "interaction_frequency": len(interactions) / 30  # per day
        }

    async def _get_spaced_repetition_summary(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Get summary of spaced repetition progress."""
        result = await db.execute(
            select(SpacedRepetitionSchedule)
            .where(SpacedRepetitionSchedule.user_id == user_id)
        )
        schedules = result.scalars().all()

        if not schedules:
            return {"active_items": 0}

        due_count = sum(
            1 for s in schedules
            if s.next_review and s.next_review <= datetime.utcnow()
        )

        avg_easiness = sum(s.easiness_factor for s in schedules) / len(schedules)

        return {
            "active_items": len(schedules),
            "items_due": due_count,
            "avg_easiness_factor": avg_easiness,
            "total_repetitions": sum(s.repetitions for s in schedules)
        }

    def _format_interaction_data(
        self,
        interactions: List[MentorInteraction],
        learner_state: Optional[LearnerState],
        mastery_changes: List[LearnerMastery],
        engagement_patterns: Dict[str, Any]
    ) -> str:
        """Format interaction data for the synthesis prompt."""
        parts = []

        # Session conversation summary
        parts.append("### Recent Conversation:")
        for inter in interactions[-10:]:  # Last 10 messages
            if inter.user_message:
                parts.append(f"Student: {inter.user_message[:200]}")
            parts.append(f"Mentor: {inter.mentor_response[:200]}")

        # Learner state
        if learner_state:
            parts.append(f"\n### Learner State:")
            parts.append(f"- Overall mastery: {learner_state.overall_mastery:.1%}")
            parts.append(f"- Learning velocity: {learner_state.learning_velocity:.2f}")
            parts.append(f"- Current affect: {learner_state.current_affect.value if learner_state.current_affect else 'unknown'}")
            parts.append(f"- Preferred pace: {learner_state.preferred_pace}")
            parts.append(f"- Prefers visual: {learner_state.prefers_visual}")

        # Recent mastery changes
        if mastery_changes:
            parts.append(f"\n### Recent Learning Progress:")
            for m in mastery_changes[:5]:
                parts.append(f"- {m.skill_id}: {m.mastery_level:.1%} mastery")
                if m.misconceptions:
                    parts.append(f"  Misconceptions: {m.misconceptions[:2]}")

        # Engagement patterns
        parts.append(f"\n### Engagement Patterns:")
        parts.append(f"- Avg sentiment: {engagement_patterns.get('avg_sentiment', 0):.2f}")
        parts.append(f"- Interactions per day: {engagement_patterns.get('interaction_frequency', 0):.1f}")
        if engagement_patterns.get('helpfulness_rate') is not None:
            parts.append(f"- Helpfulness rate: {engagement_patterns['helpfulness_rate']:.1%}")

        return "\n".join(parts)

    def _format_comprehensive_data(
        self,
        interactions: List[MentorInteraction],
        learner_state: Optional[LearnerState],
        all_mastery: List[LearnerMastery],
        engagement_patterns: Dict[str, Any],
        spaced_rep: Dict[str, Any],
        user: User
    ) -> str:
        """Format comprehensive data for full memory synthesis."""
        parts = []

        # User basic info
        parts.append("### User Profile:")
        if user.first_name:
            parts.append(f"- Name: {user.first_name}")
        if user.bio:
            parts.append(f"- Bio: {user.bio[:200]}")

        # Learning profile from JSON field
        if user.learning_profile:
            parts.append(f"- Learning profile: {user.learning_profile}")

        # Interaction highlights (sample to avoid token overload)
        parts.append("\n### Conversation Highlights (sampled):")
        for inter in interactions[::3][:15]:  # Every 3rd, up to 15
            if inter.user_message:
                sentiment = f" [sentiment: {inter.sentiment_detected:.1f}]" if inter.sentiment_detected else ""
                parts.append(f"Q: {inter.user_message[:150]}{sentiment}")

        # Mastery summary
        if all_mastery:
            parts.append("\n### Skill Mastery:")
            strong = [m for m in all_mastery if m.mastery_level >= 0.7]
            weak = [m for m in all_mastery if m.mastery_level < 0.4]

            if strong:
                parts.append(f"Strong in: {', '.join(m.skill_id for m in strong[:5])}")
            if weak:
                parts.append(f"Needs work: {', '.join(m.skill_id for m in weak[:5])}")

        # Learner state
        if learner_state:
            parts.append(f"\n### Current State:")
            parts.append(f"- Mastery: {learner_state.overall_mastery:.1%}")
            parts.append(f"- Pace preference: {learner_state.preferred_pace}")
            parts.append(f"- Visual learner: {learner_state.prefers_visual}")
            parts.append(f"- Context: {learner_state.current_active_context}")

        # Spaced repetition
        if spaced_rep.get('active_items', 0) > 0:
            parts.append(f"\n### Spaced Repetition:")
            parts.append(f"- Active items: {spaced_rep['active_items']}")
            parts.append(f"- Items due: {spaced_rep['items_due']}")

        return "\n".join(parts)

    async def _generate_memory_synthesis(
        self,
        interaction_data: str,
        current_profile: str
    ) -> str:
        """Generate memory synthesis using AI orchestrator."""
        prompt = self.SYNTHESIS_PROMPT_TEMPLATE.format(
            interaction_data=interaction_data,
            current_profile=current_profile or "No existing profile."
        )

        try:
            response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.MEDIUM,
                model_preference=ModelType.CLAUDE_3_5_SONNET,  # Use capable model for synthesis
                max_tokens=500
            )

            # Extract content from response
            if hasattr(response, 'content'):
                return response.content.strip()
            return str(response).strip()

        except Exception as e:
            logger.error(f"Failed to generate memory synthesis: {e}")
            # Return current profile if synthesis fails
            return current_profile

    async def _save_user_memory(
        self,
        user_id: int,
        memory: str,
        db: AsyncSession
    ) -> bool:
        """Save updated memory to user record."""
        try:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user:
                user.user_context_summary = memory
                user.updated_at = datetime.utcnow()
                await db.commit()
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to save user memory: {e}")
            await db.rollback()
            return False

    def _get_default_memory(self) -> str:
        """Return default memory for new users."""
        return """
## About This Student:
This is a new student. No previous interaction history available yet.

## How to Approach:
- Start by understanding their learning goals
- Ask about their background and experience level
- Pay attention to their communication style and adapt accordingly
- Note any preferences or struggles for future reference
"""

    def _parse_memory_to_insights(self, memory: str) -> List[MemoryInsight]:
        """Parse memory blob back into structured insights."""
        # For now, return empty list - full implementation would parse the text
        return []

    def _prune_insights(self, insights: List[MemoryInsight]) -> List[MemoryInsight]:
        """Prune old or low-confidence insights."""
        # Keep most recent and highest confidence
        sorted_insights = sorted(
            insights,
            key=lambda x: (x.confidence, x.timestamp),
            reverse=True
        )

        # Keep top insights per category
        by_category: Dict[str, List[MemoryInsight]] = {}
        for insight in sorted_insights:
            if insight.category not in by_category:
                by_category[insight.category] = []
            if len(by_category[insight.category]) < self.MAX_INSIGHTS_PER_CATEGORY:
                by_category[insight.category].append(insight)

        return [i for cat in by_category.values() for i in cat]

    def _insights_to_memory(self, insights: List[MemoryInsight]) -> str:
        """Convert structured insights back to memory blob."""
        if not insights:
            return self._get_default_memory()

        parts = []
        by_category: Dict[str, List[MemoryInsight]] = {}

        for insight in insights:
            if insight.category not in by_category:
                by_category[insight.category] = []
            by_category[insight.category].append(insight)

        if "learning_style" in by_category:
            parts.append("**Learning Style:**")
            for i in by_category["learning_style"]:
                parts.append(f"- {i.content}")

        if "success_pattern" in by_category:
            parts.append("\n**What Works:**")
            for i in by_category["success_pattern"]:
                parts.append(f"- {i.content}")

        if "struggle_point" in by_category:
            parts.append("\n**Challenging Areas:**")
            for i in by_category["struggle_point"]:
                parts.append(f"- {i.content}")

        return "\n".join(parts)


# Global service instance
memory_synthesis_service = MemorySynthesisService()
