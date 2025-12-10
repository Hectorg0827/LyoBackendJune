"""
AdMob Integration Service for Interactive Cinema

Hybrid approach:
- Server determines WHEN to show ads (based on mastery, session, latency)
- Client handles DISPLAY via Google SDKs (AdMob)
- Server tracks analytics for optimization

This service integrates ad placements into the learning experience
while maintaining engagement and avoiding disruption.
"""

import asyncio
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func

from lyo_app.ai_classroom.models import (
    AdPlacementConfig,
    MasteryState,
    CourseProgress,
    InteractionAttempt
)

logger = logging.getLogger(__name__)


class AdPlacementType(str, Enum):
    """Types of ad placements in the learning flow"""
    LOADING = "loading"              # During content loading/generation
    BETWEEN_MODULES = "between_modules"  # Natural break between modules
    REMEDIATION_WAIT = "remediation_wait"  # While generating remediation
    SESSION_END = "session_end"      # When ending a session
    REVIEW_COMPLETE = "review_complete"  # After completing daily review


class AdFormat(str, Enum):
    """Supported ad formats"""
    INTERSTITIAL = "interstitial"  # Full-screen between content
    REWARDED = "rewarded"          # Optional for bonus content
    BANNER = "banner"              # Subtle during loading


@dataclass
class AdDecision:
    """Result of ad placement decision"""
    should_show: bool
    ad_unit_id: Optional[str] = None
    ad_format: Optional[str] = None
    placement_type: Optional[str] = None
    skip_reason: Optional[str] = None
    estimated_latency_ms: int = 0
    user_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdAnalyticsEvent:
    """Analytics event for ad tracking"""
    event_type: str  # impression, click, skip, error
    user_id: str
    course_id: Optional[str]
    placement_type: str
    ad_unit_id: str
    timestamp: datetime
    session_id: str
    mastery_at_time: Optional[float] = None
    latency_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionAdState:
    """Tracks ad state within a user session"""
    session_id: str
    ads_shown: int = 0
    last_ad_timestamp: Optional[datetime] = None
    total_latency_filled_ms: int = 0
    skipped_count: int = 0
    placement_history: List[str] = field(default_factory=list)


class AdIntegrationService:
    """
    Manages ad integration for the Interactive Cinema experience.
    
    Design Philosophy:
    1. Ads should fill natural latency, not create it
    2. Never interrupt flow for engaged learners
    3. Premium users never see ads
    4. Frequency caps protect user experience
    5. Analytics drive optimization
    
    The service makes server-side decisions about ad placement
    and returns ad unit IDs for client-side rendering via AdMob SDK.
    """
    
    def __init__(self):
        # In-memory session state (could use Redis in production)
        self._session_states: Dict[str, SessionAdState] = {}
        
        # Analytics buffer (batched to analytics pipeline)
        self._analytics_buffer: List[AdAnalyticsEvent] = []
        self._buffer_flush_size = 100
        
        # Config cache (refresh periodically)
        self._config_cache: Dict[str, AdPlacementConfig] = {}
        self._config_cache_time: Optional[datetime] = None
        self._config_cache_ttl = timedelta(minutes=5)
        
    async def refresh_config_cache(self, db: AsyncSession):
        """Refresh ad placement configurations from database"""
        now = datetime.utcnow()
        
        if (self._config_cache_time and 
            now - self._config_cache_time < self._config_cache_ttl):
            return  # Cache still fresh
        
        result = await db.execute(
            select(AdPlacementConfig)
            .where(AdPlacementConfig.is_active == True)
        )
        configs = result.scalars().all()
        
        self._config_cache = {
            config.placement_type: config
            for config in configs
        }
        self._config_cache_time = now
        
        logger.debug(f"Refreshed ad config cache: {len(self._config_cache)} active placements")
    
    def _get_or_create_session_state(self, session_id: str) -> SessionAdState:
        """Get or create session state for tracking"""
        if session_id not in self._session_states:
            self._session_states[session_id] = SessionAdState(session_id=session_id)
        return self._session_states[session_id]
    
    async def should_show_ad(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        placement_type: AdPlacementType,
        estimated_latency_ms: int = 0,
        course_id: Optional[str] = None,
        is_premium: bool = False,
        current_mastery: Optional[float] = None
    ) -> AdDecision:
        """
        Determine whether to show an ad at this placement point.
        
        Args:
            db: Database session
            user_id: User identifier
            session_id: Current session identifier
            placement_type: Type of placement opportunity
            estimated_latency_ms: Expected latency at this point
            course_id: Optional course context
            is_premium: Whether user has premium subscription
            current_mastery: User's current mastery level (0-1)
            
        Returns:
            AdDecision with ad details or skip reason
        """
        # Refresh config if needed
        await self.refresh_config_cache(db)
        
        # Premium users never see ads
        if is_premium:
            return AdDecision(
                should_show=False,
                skip_reason="premium_user"
            )
        
        # Check if we have config for this placement type
        config = self._config_cache.get(placement_type.value)
        if not config:
            return AdDecision(
                should_show=False,
                skip_reason="no_placement_config"
            )
        
        # Check latency threshold
        if estimated_latency_ms < config.min_latency_ms:
            return AdDecision(
                should_show=False,
                skip_reason="latency_too_low",
                estimated_latency_ms=estimated_latency_ms,
                user_context={"threshold": config.min_latency_ms}
            )
        
        # Check session frequency cap
        session_state = self._get_or_create_session_state(session_id)
        if session_state.ads_shown >= config.max_frequency_per_session:
            return AdDecision(
                should_show=False,
                skip_reason="session_frequency_cap",
                user_context={"ads_shown": session_state.ads_shown}
            )
        
        # Check cooldown
        if session_state.last_ad_timestamp:
            time_since_last = (datetime.utcnow() - session_state.last_ad_timestamp).total_seconds()
            if time_since_last < config.cooldown_seconds:
                return AdDecision(
                    should_show=False,
                    skip_reason="cooldown_active",
                    user_context={
                        "seconds_remaining": int(config.cooldown_seconds - time_since_last)
                    }
                )
        
        # Check subject targeting if applicable
        if config.target_subjects and course_id:
            # Would need to fetch course subject and compare
            # For now, allow if targeting is set (simplified)
            pass
        
        # Check mastery-based skip
        # High mastery users might be in flow state - don't interrupt
        if current_mastery and current_mastery > 0.9:
            return AdDecision(
                should_show=False,
                skip_reason="high_mastery_flow_state",
                user_context={"mastery": current_mastery}
            )
        
        # All checks passed - show ad
        return AdDecision(
            should_show=True,
            ad_unit_id=config.ad_unit_id,
            ad_format=config.ad_format,
            placement_type=placement_type.value,
            estimated_latency_ms=estimated_latency_ms,
            user_context={
                "session_ads_shown": session_state.ads_shown,
                "mastery": current_mastery
            }
        )
    
    async def record_ad_impression(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        ad_unit_id: str,
        placement_type: str,
        course_id: Optional[str] = None,
        latency_filled_ms: int = 0
    ):
        """
        Record that an ad was shown (impression).
        
        Called by client after successfully displaying ad.
        """
        session_state = self._get_or_create_session_state(session_id)
        session_state.ads_shown += 1
        session_state.last_ad_timestamp = datetime.utcnow()
        session_state.total_latency_filled_ms += latency_filled_ms
        session_state.placement_history.append(placement_type)
        
        # Create analytics event
        event = AdAnalyticsEvent(
            event_type="impression",
            user_id=user_id,
            course_id=course_id,
            placement_type=placement_type,
            ad_unit_id=ad_unit_id,
            timestamp=datetime.utcnow(),
            session_id=session_id,
            latency_ms=latency_filled_ms,
            metadata={"session_total": session_state.ads_shown}
        )
        
        await self._buffer_analytics_event(event)
        
        logger.info(
            f"Ad impression recorded: user={user_id} "
            f"placement={placement_type} latency={latency_filled_ms}ms"
        )
    
    async def record_ad_click(
        self,
        user_id: str,
        session_id: str,
        ad_unit_id: str,
        placement_type: str,
        course_id: Optional[str] = None
    ):
        """Record ad click event for analytics"""
        event = AdAnalyticsEvent(
            event_type="click",
            user_id=user_id,
            course_id=course_id,
            placement_type=placement_type,
            ad_unit_id=ad_unit_id,
            timestamp=datetime.utcnow(),
            session_id=session_id
        )
        
        await self._buffer_analytics_event(event)
        logger.info(f"Ad click recorded: user={user_id} ad={ad_unit_id}")
    
    async def record_ad_skip(
        self,
        user_id: str,
        session_id: str,
        ad_unit_id: str,
        placement_type: str,
        skip_after_seconds: float = 0
    ):
        """Record when user skips an ad"""
        session_state = self._get_or_create_session_state(session_id)
        session_state.skipped_count += 1
        
        event = AdAnalyticsEvent(
            event_type="skip",
            user_id=user_id,
            course_id=None,
            placement_type=placement_type,
            ad_unit_id=ad_unit_id,
            timestamp=datetime.utcnow(),
            session_id=session_id,
            metadata={"skip_after_seconds": skip_after_seconds}
        )
        
        await self._buffer_analytics_event(event)
    
    async def record_ad_error(
        self,
        user_id: str,
        session_id: str,
        ad_unit_id: str,
        placement_type: str,
        error_code: str,
        error_message: str
    ):
        """Record ad loading/display error"""
        event = AdAnalyticsEvent(
            event_type="error",
            user_id=user_id,
            course_id=None,
            placement_type=placement_type,
            ad_unit_id=ad_unit_id,
            timestamp=datetime.utcnow(),
            session_id=session_id,
            metadata={
                "error_code": error_code,
                "error_message": error_message
            }
        )
        
        await self._buffer_analytics_event(event)
        logger.warning(f"Ad error: user={user_id} error={error_code}")
    
    async def _buffer_analytics_event(self, event: AdAnalyticsEvent):
        """Buffer analytics events for batch processing"""
        self._analytics_buffer.append(event)
        
        if len(self._analytics_buffer) >= self._buffer_flush_size:
            await self._flush_analytics_buffer()
    
    async def _flush_analytics_buffer(self):
        """Flush analytics buffer to storage/pipeline"""
        if not self._analytics_buffer:
            return
        
        events = self._analytics_buffer
        self._analytics_buffer = []
        
        # In production, send to analytics pipeline (BigQuery, Amplitude, etc.)
        # For now, just log summary
        logger.info(f"Flushing {len(events)} ad analytics events")
        
        # TODO: Implement actual analytics storage
        # await analytics_client.batch_insert(events)
    
    async def get_rewarded_ad_for_bonus(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        bonus_type: str,
        is_premium: bool = False
    ) -> Optional[AdDecision]:
        """
        Get a rewarded ad that user can watch for bonus content.
        
        Rewarded ads are opt-in and give users something in return:
        - Extra hints
        - Bonus lessons
        - Extended session time
        - Achievement boosts
        """
        if is_premium:
            # Premium users get bonuses for free
            return None
        
        await self.refresh_config_cache(db)
        
        # Look for rewarded ad config
        for placement_type, config in self._config_cache.items():
            if config.ad_format == "rewarded":
                session_state = self._get_or_create_session_state(session_id)
                
                # Rewarded ads have more lenient limits
                if session_state.ads_shown < config.max_frequency_per_session * 2:
                    return AdDecision(
                        should_show=True,
                        ad_unit_id=config.ad_unit_id,
                        ad_format="rewarded",
                        placement_type="rewarded_bonus",
                        user_context={"bonus_type": bonus_type}
                    )
        
        return None
    
    async def get_session_analytics(self, session_id: str) -> Dict[str, Any]:
        """Get ad analytics for current session"""
        state = self._session_states.get(session_id)
        if not state:
            return {"no_data": True}
        
        return {
            "ads_shown": state.ads_shown,
            "ads_skipped": state.skipped_count,
            "latency_filled_ms": state.total_latency_filled_ms,
            "placements": state.placement_history,
            "last_ad": state.last_ad_timestamp.isoformat() if state.last_ad_timestamp else None
        }
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Clean up old session states to prevent memory growth"""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        to_remove = [
            sid for sid, state in self._session_states.items()
            if state.last_ad_timestamp and state.last_ad_timestamp < cutoff
        ]
        
        for sid in to_remove:
            del self._session_states[sid]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old ad session states")


class CelebrationService:
    """
    Handles celebration moments in the learning experience.
    
    Celebrations trigger on:
    - Mastery milestones (first quiz passed, concept mastered)
    - Streak achievements (3 days, 7 days, 30 days)
    - Course completion
    - Perfect scores
    - Recovery from struggle
    """
    
    # Celebration types with their configurations
    CELEBRATION_CONFIGS = {
        "first_correct": {
            "animation": "confetti_burst",
            "sound": "success_chime",
            "message_template": "Great start! You got it right!",
            "duration_ms": 2000,
            "priority": 1
        },
        "concept_mastered": {
            "animation": "star_explosion",
            "sound": "level_up",
            "message_template": "🌟 Concept Mastered: {concept_name}!",
            "duration_ms": 3000,
            "priority": 3
        },
        "streak_milestone": {
            "animation": "flame_burst",
            "sound": "achievement",
            "message_template": "🔥 {streak_count} Day Streak!",
            "duration_ms": 3000,
            "priority": 4
        },
        "perfect_score": {
            "animation": "gold_shower",
            "sound": "fanfare",
            "message_template": "⭐ Perfect Score!",
            "duration_ms": 4000,
            "priority": 5
        },
        "course_complete": {
            "animation": "graduation",
            "sound": "graduation_fanfare",
            "message_template": "🎓 Course Complete: {course_name}!",
            "duration_ms": 5000,
            "priority": 6
        },
        "struggle_overcome": {
            "animation": "phoenix_rise",
            "sound": "triumph",
            "message_template": "💪 You did it! Never give up!",
            "duration_ms": 3000,
            "priority": 3
        },
        "speed_bonus": {
            "animation": "lightning_flash",
            "sound": "speed_chime",
            "message_template": "⚡ Speed Bonus!",
            "duration_ms": 1500,
            "priority": 2
        }
    }
    
    def __init__(self):
        # Track recent celebrations to avoid spam
        self._recent_celebrations: Dict[str, List[datetime]] = {}
        self._celebration_cooldown = timedelta(seconds=30)
    
    async def check_celebration_trigger(
        self,
        db: AsyncSession,
        user_id: str,
        course_id: str,
        trigger_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a celebration should be triggered based on context.
        
        Args:
            db: Database session
            user_id: User identifier
            course_id: Course being studied
            trigger_context: Context about what just happened
                - interaction_correct: bool
                - new_mastery: float
                - previous_mastery: float
                - concept_id: str
                - is_perfect_session: bool
                - current_streak: int
                - struggles_before_success: int
            
        Returns:
            Celebration config or None
        """
        celebrations = []
        
        # Check for first correct answer in session
        if trigger_context.get("interaction_correct") and trigger_context.get("first_in_session"):
            celebrations.append(("first_correct", {}))
        
        # Check for concept mastery
        new_mastery = trigger_context.get("new_mastery", 0)
        prev_mastery = trigger_context.get("previous_mastery", 0)
        if prev_mastery < 0.8 <= new_mastery:
            concept_name = trigger_context.get("concept_name", "this concept")
            celebrations.append(("concept_mastered", {"concept_name": concept_name}))
        
        # Check for streak milestone
        streak = trigger_context.get("current_streak", 0)
        if streak in [3, 7, 14, 30, 60, 100, 365]:
            celebrations.append(("streak_milestone", {"streak_count": streak}))
        
        # Check for perfect score
        if trigger_context.get("is_perfect_session"):
            celebrations.append(("perfect_score", {}))
        
        # Check for overcoming struggle
        struggles = trigger_context.get("struggles_before_success", 0)
        if struggles >= 3 and trigger_context.get("interaction_correct"):
            celebrations.append(("struggle_overcome", {}))
        
        # Check for course completion
        if trigger_context.get("course_complete"):
            course_name = trigger_context.get("course_name", "the course")
            celebrations.append(("course_complete", {"course_name": course_name}))
        
        # Check for speed bonus
        response_time_ms = trigger_context.get("response_time_ms", float("inf"))
        if response_time_ms < 3000 and trigger_context.get("interaction_correct"):
            celebrations.append(("speed_bonus", {}))
        
        if not celebrations:
            return None
        
        # Pick highest priority celebration
        celebrations.sort(key=lambda x: -self.CELEBRATION_CONFIGS[x[0]]["priority"])
        celebration_type, params = celebrations[0]
        
        # Check cooldown
        user_key = f"{user_id}:{celebration_type}"
        recent = self._recent_celebrations.get(user_key, [])
        recent = [t for t in recent if datetime.utcnow() - t < self._celebration_cooldown]
        
        if recent:
            # Recently celebrated this type, skip
            return None
        
        # Record this celebration
        self._recent_celebrations[user_key] = recent + [datetime.utcnow()]
        
        # Build celebration response
        config = self.CELEBRATION_CONFIGS[celebration_type].copy()
        message = config["message_template"].format(**params)
        
        return {
            "type": celebration_type,
            "animation": config["animation"],
            "sound": config["sound"],
            "message": message,
            "duration_ms": config["duration_ms"],
            "priority": config["priority"],
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def get_celebration_config(
        self,
        db: AsyncSession,
        course_id: str
    ) -> Dict[str, Any]:
        """
        Get celebration configuration for a course.
        
        Some courses might have custom celebration styles.
        """
        # Default config
        default_config = {
            "enabled": True,
            "animations_enabled": True,
            "sounds_enabled": True,
            "celebration_types": list(self.CELEBRATION_CONFIGS.keys()),
            "custom_messages": {}
        }
        
        # Could load course-specific overrides from CelebrationConfig table
        # For now, return defaults
        return default_config
    
    def cleanup_old_celebrations(self, max_age_minutes: int = 60):
        """Clean up old celebration tracking data"""
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        
        for key in list(self._recent_celebrations.keys()):
            self._recent_celebrations[key] = [
                t for t in self._recent_celebrations[key]
                if t > cutoff
            ]
            if not self._recent_celebrations[key]:
                del self._recent_celebrations[key]


# Singleton instances
_ad_service: Optional[AdIntegrationService] = None
_celebration_service: Optional[CelebrationService] = None


async def get_ad_service() -> AdIntegrationService:
    """Get or create ad integration service singleton"""
    global _ad_service
    if _ad_service is None:
        _ad_service = AdIntegrationService()
    return _ad_service


def get_celebration_service() -> CelebrationService:
    """Get or create celebration service singleton"""
    global _celebration_service
    if _celebration_service is None:
        _celebration_service = CelebrationService()
    return _celebration_service
