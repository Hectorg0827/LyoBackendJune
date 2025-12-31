"""
Ambient Presence Manager

Manages Lyo's ambient availability across the platform.
Decides when and how to surface assistance without being intrusive.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from .models import (
    AmbientPresenceState,
    QuickAction,
    QuickActionType,
    InlineHelpLog
)
from lyo_app.personalization.models import LearnerMastery

logger = logging.getLogger(__name__)


class AmbientPresenceManager:
    """
    Manages Lyo's ambient presence and contextual assistance.
    """

    def __init__(self):
        # Thresholds for triggering inline help
        self.TIME_THRESHOLD_SECONDS = 30  # Show help after 30s on difficult content
        self.SCROLL_THRESHOLD = 3  # Show help after 3+ scrolls
        self.DAILY_INLINE_LIMIT = 5  # Max 5 inline helps per day
        self.DIFFICULTY_THRESHOLD = 0.7  # Show help if topic difficulty > 0.7

    async def update_presence(
        self,
        db: AsyncSession,
        user_id: int,
        context: Dict[str, Any]
    ) -> AmbientPresenceState:
        """
        Update user's presence state with current context.

        Called when user navigates or interacts with content.
        """
        # Get or create presence state
        stmt = select(AmbientPresenceState).where(
            AmbientPresenceState.user_id == user_id
        )
        result = await db.execute(stmt)
        state = result.scalar_one_or_none()

        if not state:
            state = AmbientPresenceState(
                user_id=user_id,
                organization_id=context.get('organization_id')
            )
            db.add(state)

        # Update state
        state.is_active = True
        state.last_seen_at = datetime.utcnow()
        state.current_page = context.get('page')
        state.current_topic = context.get('topic')
        state.current_content_id = context.get('content_id')
        state.time_on_page = context.get('time_on_page', 0.0)
        state.scroll_count = context.get('scroll_count', 0)
        state.mouse_hesitations = context.get('mouse_hesitations', 0)
        state.context = context

        await db.commit()
        await db.refresh(state)

        return state

    async def should_show_inline_help(
        self,
        db: AsyncSession,
        user_id: int,
        current_context: Dict[str, Any],
        user_behavior: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Decide if inline help should be shown.

        Returns:
            (should_show, help_message)
        """
        # Check daily limit
        stmt = select(AmbientPresenceState).where(
            AmbientPresenceState.user_id == user_id
        )
        result = await db.execute(stmt)
        state = result.scalar_one_or_none()

        if state and state.inline_help_count_today >= self.DAILY_INLINE_LIMIT:
            return False, None

        # Extract behavior signals
        time_on_section = user_behavior.get('time_on_section', 0)
        scroll_count = user_behavior.get('scroll_count', 0)

        # Check if user is stuck (time-based)
        if time_on_section > self.TIME_THRESHOLD_SECONDS and scroll_count > self.SCROLL_THRESHOLD:
            return True, "Stuck? I can help break this down."

        # Check historical difficulty with this topic
        topic = current_context.get('topic')
        if topic:
            difficulty_level = await self._get_topic_difficulty(user_id, topic, db)

            if difficulty_level > self.DIFFICULTY_THRESHOLD:
                return True, "This topic is tricky. Want me to explain it?"

        return False, None

    async def _get_topic_difficulty(
        self,
        user_id: int,
        topic: str,
        db: AsyncSession
    ) -> float:
        """
        Get user's difficulty level with this topic based on past performance.
        Returns 0.0 (easy) to 1.0 (very difficult).
        """
        # Check mastery for this skill/topic
        stmt = select(LearnerMastery).where(
            and_(
                LearnerMastery.user_id == user_id,
                LearnerMastery.skill_id == topic
            )
        )
        result = await db.execute(stmt)
        mastery = result.scalar_one_or_none()

        if not mastery:
            return 0.5  # Unknown = medium difficulty

        # Lower mastery = higher difficulty
        difficulty = 1.0 - mastery.mastery_level
        return difficulty

    async def log_inline_help(
        self,
        db: AsyncSession,
        user_id: int,
        help_type: str,
        help_text: str,
        page: str,
        topic: Optional[str] = None,
        content_id: Optional[str] = None,
        organization_id: Optional[int] = None
    ) -> InlineHelpLog:
        """
        Log when inline help is shown.
        """
        log = InlineHelpLog(
            user_id=user_id,
            organization_id=organization_id,
            help_type=help_type,
            help_text=help_text,
            page=page,
            topic=topic,
            content_id=content_id
        )
        db.add(log)

        # Increment daily counter
        stmt = select(AmbientPresenceState).where(
            AmbientPresenceState.user_id == user_id
        )
        result = await db.execute(stmt)
        state = result.scalar_one_or_none()

        if state:
            state.inline_help_count_today += 1

        await db.commit()
        await db.refresh(log)

        return log

    async def record_help_response(
        self,
        db: AsyncSession,
        help_log_id: int,
        user_response: str  # 'accepted', 'dismissed', 'ignored'
    ):
        """
        Record user's response to inline help.
        """
        stmt = select(InlineHelpLog).where(InlineHelpLog.id == help_log_id)
        result = await db.execute(stmt)
        log = result.scalar_one_or_none()

        if log:
            log.user_response = user_response
            log.response_at = datetime.utcnow()
            await db.commit()

    async def get_contextual_quick_actions(
        self,
        db: AsyncSession,
        user_id: int,
        current_page: str,
        current_content: Dict[str, Any]
    ) -> List[QuickAction]:
        """
        Generate context-aware quick actions for Cmd+K palette or widget.
        """
        actions = []

        # Always available: General chat
        actions.append(QuickAction(
            id="ask_anything",
            label="Ask Lyo anything...",
            action_type=QuickActionType.ASK_ANYTHING,
            icon="💬"
        ))

        # Context-specific actions based on current page
        if current_page == "lesson":
            concept = current_content.get('current_concept', 'this concept')
            actions.append(QuickAction(
                id="explain_concept",
                label=f"Explain: {concept}",
                action_type=QuickActionType.EXPLAIN_CONCEPT,
                icon="🧠",
                context={'concept': concept}
            ))
            actions.append(QuickAction(
                id="practice_questions",
                label="Generate practice questions",
                action_type=QuickActionType.PRACTICE_QUESTIONS,
                icon="📝"
            ))
            actions.append(QuickAction(
                id="summarize",
                label="Summarize this lesson",
                action_type=QuickActionType.SUMMARIZE,
                icon="📋"
            ))

        elif current_page == "problem_set":
            actions.append(QuickAction(
                id="hint",
                label="Give me a hint",
                action_type=QuickActionType.HINT,
                icon="💡"
            ))
            actions.append(QuickAction(
                id="similar_example",
                label="Show a similar example",
                action_type=QuickActionType.SIMILAR_EXAMPLE,
                icon="📚"
            ))

        elif current_page == "course":
            actions.append(QuickAction(
                id="create_note",
                label="Create study note",
                action_type=QuickActionType.CREATE_NOTE,
                icon="📓"
            ))

        # Personalized: Recent struggles
        recent_struggles = await self._get_recent_struggles(user_id, db)
        if recent_struggles:
            struggle_topic = recent_struggles[0]['topic']
            actions.append(QuickAction(
                id=f"review_struggle_{struggle_topic}",
                label=f"Review: {struggle_topic}",
                action_type=QuickActionType.REVIEW_STRUGGLE,
                icon="🔄",
                context={'topic': struggle_topic}
            ))

        return actions

    async def _get_recent_struggles(
        self,
        user_id: int,
        db: AsyncSession,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get topics user struggled with recently.
        """
        # Get low-mastery topics from past week
        since_date = datetime.utcnow() - timedelta(days=days)

        stmt = select(LearnerMastery).where(
            and_(
                LearnerMastery.user_id == user_id,
                LearnerMastery.mastery_level < 0.5,  # Struggling
                LearnerMastery.last_seen >= since_date
            )
        ).order_by(LearnerMastery.last_seen.desc()).limit(3)

        result = await db.execute(stmt)
        masteries = result.scalars().all()

        return [
            {
                'topic': m.skill_id,
                'mastery': m.mastery_level,
                'last_seen': m.last_seen
            }
            for m in masteries
        ]

    async def reset_daily_counters(self, db: AsyncSession):
        """
        Reset daily inline help counters (call this in a daily cron job).
        """
        stmt = select(AmbientPresenceState)
        result = await db.execute(stmt)
        states = result.scalars().all()

        for state in states:
            state.inline_help_count_today = 0
            state.quick_access_count_today = 0

        await db.commit()
        logger.info(f"Reset daily counters for {len(states)} users")


# Global singleton instance
presence_manager = AmbientPresenceManager()
