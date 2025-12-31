"""
Behavioral Hooks Service - Habit-Forming Engagement System

Implements Nir Eyal's Hook Model to create positive habit loops:
1. TRIGGER - External or internal cue that initiates behavior
2. ACTION - The behavior done in anticipation of reward
3. VARIABLE REWARD - Unpredictable positive reinforcement
4. INVESTMENT - User puts something into the product

The goal is to make learning a habit, not a chore. Every loop should
feel rewarding and make the next engagement more likely.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from lyo_app.auth.models import User
from lyo_app.ai_agents.models import MentorInteraction
from lyo_app.gamification.models import UserXP, Streak, Achievement, UserAchievement
from lyo_app.personalization.models import LearnerState, LearnerMastery

logger = logging.getLogger(__name__)


class TriggerType(str, Enum):
    """Types of triggers that can initiate engagement."""
    # External Triggers (platform-initiated)
    PUSH_NOTIFICATION = "push_notification"
    EMAIL = "email"
    IN_APP_PROMPT = "in_app_prompt"
    STREAK_WARNING = "streak_warning"
    SOCIAL_PROOF = "social_proof"  # "5 friends learned today"
    CALENDAR_EVENT = "calendar_event"

    # Internal Triggers (user-initiated from emotion)
    BOREDOM = "boredom"
    CURIOSITY = "curiosity"
    ANXIETY = "anxiety"  # Pre-exam stress
    FOMO = "fomo"  # Fear of missing out
    HABIT = "habit"  # Automatic behavior


class ActionType(str, Enum):
    """Types of actions users can take."""
    OPEN_APP = "open_app"
    START_SESSION = "start_session"
    COMPLETE_LESSON = "complete_lesson"
    TAKE_QUIZ = "take_quiz"
    ASK_QUESTION = "ask_question"
    REVIEW_ITEM = "review_item"
    SHARE_PROGRESS = "share_progress"
    HELP_PEER = "help_peer"


class RewardType(str, Enum):
    """Types of variable rewards."""
    # Rewards of the Tribe (social)
    SOCIAL_VALIDATION = "social_validation"  # Likes, comments
    LEADERBOARD_RANK = "leaderboard_rank"
    PEER_RECOGNITION = "peer_recognition"
    COMMUNITY_BADGE = "community_badge"

    # Rewards of the Hunt (resources)
    XP_BONUS = "xp_bonus"
    STREAK_BONUS = "streak_bonus"
    UNLOCKED_CONTENT = "unlocked_content"
    ACHIEVEMENT_UNLOCK = "achievement_unlock"

    # Rewards of the Self (mastery)
    MASTERY_MILESTONE = "mastery_milestone"
    SKILL_LEVEL_UP = "skill_level_up"
    PERSONAL_BEST = "personal_best"
    INSIGHT_GAINED = "insight_gained"


class InvestmentType(str, Enum):
    """Types of investments users make."""
    TIME = "time"
    DATA = "data"  # Profile info, preferences
    CONTENT = "content"  # Notes, answers
    REPUTATION = "reputation"  # Streaks, XP
    SOCIAL_CAPITAL = "social_capital"  # Followers, connections
    CUSTOMIZATION = "customization"  # Personalized settings


@dataclass
class Trigger:
    """A trigger event that can initiate user engagement."""
    type: TriggerType
    user_id: int
    message: str
    action_url: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    clicked: bool = False
    converted: bool = False  # Led to meaningful action


@dataclass
class HookLoop:
    """A complete hook loop tracking trigger → action → reward → investment."""
    user_id: int
    trigger: TriggerType
    action: ActionType
    rewards: List[RewardType]
    investments: List[InvestmentType]
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_xp_earned: int = 0
    satisfaction_score: Optional[float] = None  # User feedback


@dataclass
class VariableReward:
    """A reward with variable magnitude to maintain engagement."""
    type: RewardType
    title: str
    message: str
    value: Any  # XP amount, badge name, rank, etc.
    rarity: str  # common, uncommon, rare, epic, legendary
    celebration_level: int  # 1-5, affects animation/sound


class BehavioralHooksService:
    """
    Orchestrates the Hook Model for habit formation.

    Key principles:
    1. Variable rewards are more engaging than predictable ones
    2. Investments increase switching costs and commitment
    3. Internal triggers are more powerful than external ones
    4. The loop should feel natural, not manipulative
    """

    # Reward multipliers by rarity
    RARITY_MULTIPLIERS = {
        "common": 1.0,
        "uncommon": 1.5,
        "rare": 2.0,
        "epic": 3.0,
        "legendary": 5.0
    }

    # Probability of each rarity
    RARITY_PROBABILITIES = {
        "common": 0.60,
        "uncommon": 0.25,
        "rare": 0.10,
        "epic": 0.04,
        "legendary": 0.01
    }

    def __init__(self):
        self.reward_pool = self._initialize_reward_pool()

    # ==================== Trigger Generation ====================

    async def generate_trigger(
        self,
        user_id: int,
        trigger_type: TriggerType,
        context: Dict[str, Any],
        db: AsyncSession
    ) -> Trigger:
        """
        Generate a personalized trigger for a user.
        """
        # Get user context
        user = await db.get(User, user_id)
        memory = user.user_context_summary if user else None

        # Generate message based on trigger type
        message = self._generate_trigger_message(trigger_type, context, memory)

        return Trigger(
            type=trigger_type,
            user_id=user_id,
            message=message,
            action_url=context.get("action_url", "/learn"),
            context=context
        )

    def _generate_trigger_message(
        self,
        trigger_type: TriggerType,
        context: Dict[str, Any],
        memory: Optional[str]
    ) -> str:
        """Generate personalized trigger message."""
        messages = {
            TriggerType.STREAK_WARNING: [
                "Your {streak_count}-day streak is about to end! 🔥",
                "Just 5 minutes keeps your streak alive!",
                "Don't let {streak_count} days of progress slip away!"
            ],
            TriggerType.SOCIAL_PROOF: [
                "{friend_count} friends learned something new today",
                "You're in the top {percentile}% of learners this week!",
                "Join {active_count} learners online right now"
            ],
            TriggerType.CALENDAR_EVENT: [
                "Your {event_type} is in {days} days. Ready to prep?",
                "Smart learners prepare early. Start now?",
                "Let's get you ready for {event_title}"
            ],
            TriggerType.IN_APP_PROMPT: [
                "You were curious about {topic}. Want to continue?",
                "Left off mid-lesson. Pick up where you stopped?",
                "Your spaced repetition items are due!"
            ]
        }

        templates = messages.get(trigger_type, ["Ready to learn?"])
        template = random.choice(templates)

        # Fill in context variables
        try:
            return template.format(**context)
        except KeyError:
            return template

    # ==================== Action Tracking ====================

    async def track_action(
        self,
        user_id: int,
        action_type: ActionType,
        trigger: Optional[Trigger],
        db: AsyncSession
    ) -> HookLoop:
        """
        Track a user action and initiate the reward phase.
        """
        loop = HookLoop(
            user_id=user_id,
            trigger=trigger.type if trigger else TriggerType.HABIT,
            action=action_type,
            rewards=[],
            investments=[],
            started_at=datetime.utcnow()
        )

        # Update trigger conversion if applicable
        if trigger:
            trigger.clicked = True
            trigger.converted = True

        return loop

    # ==================== Variable Rewards ====================

    async def generate_variable_reward(
        self,
        user_id: int,
        action_type: ActionType,
        context: Dict[str, Any],
        db: AsyncSession
    ) -> VariableReward:
        """
        Generate a variable reward for an action.

        The variability is key - unpredictable rewards trigger
        dopamine release and reinforce the behavior.
        """
        # Determine rarity (with slight boost for streaks)
        streak_bonus = min(context.get("streak_count", 0) * 0.01, 0.1)
        rarity = self._roll_rarity(bonus=streak_bonus)

        # Select reward type based on action
        reward_type = self._select_reward_type(action_type, rarity)

        # Generate reward details
        reward = self._create_reward(reward_type, rarity, context)

        return reward

    def _roll_rarity(self, bonus: float = 0) -> str:
        """Roll for reward rarity with optional luck bonus."""
        roll = random.random() - bonus

        cumulative = 0
        for rarity, prob in self.RARITY_PROBABILITIES.items():
            cumulative += prob
            if roll <= cumulative:
                return rarity

        return "common"

    def _select_reward_type(
        self,
        action_type: ActionType,
        rarity: str
    ) -> RewardType:
        """Select appropriate reward type for action."""
        # Map actions to reward categories
        action_rewards = {
            ActionType.COMPLETE_LESSON: [
                RewardType.XP_BONUS,
                RewardType.MASTERY_MILESTONE,
                RewardType.SKILL_LEVEL_UP
            ],
            ActionType.TAKE_QUIZ: [
                RewardType.XP_BONUS,
                RewardType.PERSONAL_BEST,
                RewardType.ACHIEVEMENT_UNLOCK
            ],
            ActionType.START_SESSION: [
                RewardType.STREAK_BONUS,
                RewardType.XP_BONUS
            ],
            ActionType.HELP_PEER: [
                RewardType.SOCIAL_VALIDATION,
                RewardType.PEER_RECOGNITION,
                RewardType.COMMUNITY_BADGE
            ],
            ActionType.SHARE_PROGRESS: [
                RewardType.SOCIAL_VALIDATION,
                RewardType.LEADERBOARD_RANK
            ],
            ActionType.REVIEW_ITEM: [
                RewardType.MASTERY_MILESTONE,
                RewardType.INSIGHT_GAINED
            ]
        }

        possible_rewards = action_rewards.get(
            action_type,
            [RewardType.XP_BONUS, RewardType.INSIGHT_GAINED]
        )

        # Rarer rewards for rarer rolls
        if rarity in ["epic", "legendary"]:
            # Prefer mastery/achievement rewards for rare rolls
            mastery_rewards = [
                r for r in possible_rewards
                if r in [RewardType.ACHIEVEMENT_UNLOCK, RewardType.SKILL_LEVEL_UP,
                        RewardType.MASTERY_MILESTONE, RewardType.PERSONAL_BEST]
            ]
            if mastery_rewards:
                return random.choice(mastery_rewards)

        return random.choice(possible_rewards)

    def _create_reward(
        self,
        reward_type: RewardType,
        rarity: str,
        context: Dict[str, Any]
    ) -> VariableReward:
        """Create the actual reward with appropriate messaging."""
        multiplier = self.RARITY_MULTIPLIERS[rarity]
        base_xp = context.get("base_xp", 10)

        reward_configs = {
            RewardType.XP_BONUS: {
                "title": f"{rarity.title()} XP Bonus!",
                "message": f"You earned {int(base_xp * multiplier)} XP!",
                "value": int(base_xp * multiplier),
                "celebration": 2 if rarity == "common" else 3 if rarity in ["uncommon", "rare"] else 4
            },
            RewardType.STREAK_BONUS: {
                "title": "Streak Bonus! 🔥",
                "message": f"Day {context.get('streak_count', 1)} bonus: +{int(10 * multiplier)} XP",
                "value": int(10 * multiplier),
                "celebration": 3
            },
            RewardType.MASTERY_MILESTONE: {
                "title": "Mastery Milestone!",
                "message": f"You've mastered {context.get('skill', 'a new skill')}!",
                "value": context.get("skill", "skill"),
                "celebration": 4
            },
            RewardType.SKILL_LEVEL_UP: {
                "title": "Level Up! ⭐",
                "message": f"Your {context.get('skill', 'skill')} is now level {context.get('level', 2)}!",
                "value": context.get("level", 2),
                "celebration": 4
            },
            RewardType.ACHIEVEMENT_UNLOCK: {
                "title": f"{rarity.title()} Achievement!",
                "message": self._get_achievement_message(rarity),
                "value": f"{rarity}_achievement",
                "celebration": 5 if rarity in ["epic", "legendary"] else 4
            },
            RewardType.PERSONAL_BEST: {
                "title": "New Personal Best! 🏆",
                "message": f"You beat your previous record!",
                "value": "personal_best",
                "celebration": 4
            },
            RewardType.INSIGHT_GAINED: {
                "title": "Insight Unlocked! 💡",
                "message": "You've deepened your understanding",
                "value": "insight",
                "celebration": 3
            },
            RewardType.SOCIAL_VALIDATION: {
                "title": "Recognition!",
                "message": f"+{int(5 * multiplier)} reputation points",
                "value": int(5 * multiplier),
                "celebration": 2
            }
        }

        config = reward_configs.get(reward_type, {
            "title": "Reward!",
            "message": "You earned a reward!",
            "value": base_xp,
            "celebration": 2
        })

        return VariableReward(
            type=reward_type,
            title=config["title"],
            message=config["message"],
            value=config["value"],
            rarity=rarity,
            celebration_level=config["celebration"]
        )

    def _get_achievement_message(self, rarity: str) -> str:
        """Get achievement message based on rarity."""
        messages = {
            "common": "You've unlocked a new achievement!",
            "uncommon": "Nice! An uncommon achievement!",
            "rare": "Wow! A rare achievement!",
            "epic": "EPIC achievement unlocked!",
            "legendary": "🌟 LEGENDARY ACHIEVEMENT! 🌟"
        }
        return messages.get(rarity, "Achievement unlocked!")

    # ==================== Investment Tracking ====================

    async def track_investment(
        self,
        user_id: int,
        investment_type: InvestmentType,
        value: Any,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Track a user investment.

        Investments increase switching costs and make users more
        likely to return. They're things users put INTO the product.
        """
        investment_descriptions = {
            InvestmentType.TIME: f"Invested {value} minutes of learning time",
            InvestmentType.DATA: f"Personalized your learning profile",
            InvestmentType.CONTENT: f"Created {value} notes/answers",
            InvestmentType.REPUTATION: f"Built {value} reputation points",
            InvestmentType.SOCIAL_CAPITAL: f"Connected with {value} learners",
            InvestmentType.CUSTOMIZATION: f"Customized your experience"
        }

        return {
            "investment_type": investment_type.value,
            "value": value,
            "description": investment_descriptions.get(investment_type, "Made an investment"),
            "timestamp": datetime.utcnow().isoformat(),
            "next_benefit": self._get_investment_benefit(investment_type)
        }

    def _get_investment_benefit(self, investment_type: InvestmentType) -> str:
        """Explain how this investment benefits the user."""
        benefits = {
            InvestmentType.TIME: "More time = better AI personalization",
            InvestmentType.DATA: "Better recommendations tailored to you",
            InvestmentType.CONTENT: "Your notes sync across all devices",
            InvestmentType.REPUTATION: "Higher rank in leaderboards",
            InvestmentType.SOCIAL_CAPITAL: "Study groups and peer help",
            InvestmentType.CUSTOMIZATION: "Lyo learns your preferences"
        }
        return benefits.get(investment_type, "Improves your experience")

    # ==================== Complete Hook Loop ====================

    async def complete_hook_loop(
        self,
        loop: HookLoop,
        rewards: List[VariableReward],
        investments: List[Tuple[InvestmentType, Any]],
        db: AsyncSession
    ) -> HookLoop:
        """
        Complete a hook loop with rewards and investments.
        """
        loop.completed_at = datetime.utcnow()
        loop.rewards = [r.type for r in rewards]
        loop.total_xp_earned = sum(
            r.value for r in rewards
            if r.type in [RewardType.XP_BONUS, RewardType.STREAK_BONUS]
            and isinstance(r.value, (int, float))
        )
        loop.investments = [inv[0] for inv in investments]

        # Log for analytics
        logger.info(
            f"Hook loop completed: user={loop.user_id}, "
            f"trigger={loop.trigger}, action={loop.action}, "
            f"rewards={len(rewards)}, xp={loop.total_xp_earned}"
        )

        return loop

    # ==================== Analytics ====================

    async def get_hook_analytics(
        self,
        user_id: int,
        db: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get analytics on hook loop effectiveness for a user.
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Get interaction stats
        result = await db.execute(
            select(func.count(MentorInteraction.id))
            .where(
                and_(
                    MentorInteraction.user_id == user_id,
                    MentorInteraction.timestamp >= since
                )
            )
        )
        interaction_count = result.scalar() or 0

        # Get XP earned
        xp_result = await db.execute(
            select(func.sum(UserXP.xp_amount))
            .where(
                and_(
                    UserXP.user_id == user_id,
                    UserXP.earned_at >= since
                )
            )
        )
        xp_earned = xp_result.scalar() or 0

        # Estimate engagement quality
        engagement_score = min((interaction_count / days) / 3, 1.0)  # 3 per day = max

        return {
            "period_days": days,
            "total_sessions": interaction_count,
            "total_xp": int(xp_earned),
            "avg_sessions_per_day": round(interaction_count / days, 1),
            "engagement_score": round(engagement_score, 2),
            "hook_health": "strong" if engagement_score > 0.7 else "moderate" if engagement_score > 0.4 else "needs_attention"
        }

    def _initialize_reward_pool(self) -> Dict[str, List[str]]:
        """Initialize the pool of possible rewards."""
        return {
            "achievements": [
                "First Steps", "Quick Learner", "Persistent",
                "Curious Mind", "Helping Hand", "Night Owl",
                "Early Bird", "Streak Master", "Quiz Whiz"
            ],
            "badges": [
                "Newcomer", "Regular", "Dedicated", "Expert",
                "Master", "Legend", "Pioneer", "Mentor"
            ],
            "titles": [
                "Apprentice", "Scholar", "Sage", "Virtuoso"
            ]
        }


# Global service instance
behavioral_hooks_service = BehavioralHooksService()
