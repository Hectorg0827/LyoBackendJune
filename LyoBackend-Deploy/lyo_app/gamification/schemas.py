"""
Pydantic schemas for gamification module endpoints.
Defines request/response models for XP, achievements, streaks, and leaderboards.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, ConfigDict

from lyo_app.gamification.models import (
    XPActionType, AchievementType, AchievementRarity, StreakType
)


# XP Schemas
class XPRecordBase(BaseModel):
    """Base XP record schema."""
    
    action_type: XPActionType = Field(..., description="Type of action that earned XP")
    xp_earned: int = Field(..., ge=0, description="Amount of XP earned")
    context_type: Optional[str] = Field(None, max_length=50, description="Context type")
    context_id: Optional[int] = Field(None, description="Context entity ID")
    context_data: Optional[Dict[str, Any]] = Field(None, description="Additional context data")


class XPRecordCreate(XPRecordBase):
    """Schema for creating XP records."""
    pass


class XPRecordRead(XPRecordBase):
    """Schema for reading XP records."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="XP record ID")
    user_id: int = Field(..., description="User ID")
    earned_at: datetime = Field(..., description="When XP was earned")


# Achievement Schemas
class AchievementBase(BaseModel):
    """Base achievement schema."""
    
    name: str = Field(..., min_length=1, max_length=200, description="Achievement name")
    description: str = Field(..., min_length=1, description="Achievement description")
    icon_url: Optional[str] = Field(None, max_length=500, description="Achievement icon URL")
    type: AchievementType = Field(..., description="Achievement type")
    rarity: AchievementRarity = Field(default=AchievementRarity.COMMON, description="Achievement rarity")
    xp_reward: int = Field(default=0, ge=0, description="XP reward for completion")
    criteria: Dict[str, Any] = Field(..., description="Achievement criteria")


class AchievementCreate(AchievementBase):
    """Schema for creating achievements."""
    pass


class AchievementUpdate(BaseModel):
    """Schema for updating achievements."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)
    icon_url: Optional[str] = Field(None, max_length=500)
    type: Optional[AchievementType] = None
    rarity: Optional[AchievementRarity] = None
    xp_reward: Optional[int] = Field(None, ge=0)
    criteria: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class AchievementRead(AchievementBase):
    """Schema for reading achievements."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Achievement ID")
    is_active: bool = Field(..., description="Whether achievement is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Computed fields
    total_earned: Optional[int] = Field(None, description="Total users who earned this")
    user_progress: Optional[Dict[str, Any]] = Field(None, description="Current user's progress")


# User Achievement Schemas
class UserAchievementCreate(BaseModel):
    """Schema for starting user achievement progress."""
    
    achievement_id: int = Field(..., description="Achievement ID")
    progress_data: Optional[Dict[str, Any]] = Field(None, description="Initial progress data")


class UserAchievementUpdate(BaseModel):
    """Schema for updating user achievement progress."""
    
    progress_data: Optional[Dict[str, Any]] = Field(None, description="Updated progress data")
    is_completed: Optional[bool] = Field(None, description="Completion status")


class UserAchievementRead(BaseModel):
    """Schema for reading user achievements."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="User achievement ID")
    user_id: int = Field(..., description="User ID")
    achievement_id: int = Field(..., description="Achievement ID")
    progress_data: Optional[Dict[str, Any]] = Field(None, description="Progress data")
    is_completed: bool = Field(..., description="Completion status")
    started_at: datetime = Field(..., description="Started timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    
    # Achievement details
    achievement: Optional[AchievementRead] = Field(None, description="Achievement details")
    progress_percentage: Optional[float] = Field(None, description="Progress percentage")


# Streak Schemas
class StreakBase(BaseModel):
    """Base streak schema."""
    
    streak_type: StreakType = Field(..., description="Type of streak")


class StreakUpdate(BaseModel):
    """Schema for updating streaks."""
    
    current_count: Optional[int] = Field(None, ge=0, description="Current streak count")
    is_active: Optional[bool] = Field(None, description="Whether streak is active")


class StreakRead(StreakBase):
    """Schema for reading streaks."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Streak ID")
    user_id: int = Field(..., description="User ID")
    current_count: int = Field(..., description="Current streak count")
    longest_count: int = Field(..., description="Longest streak count")
    last_activity_date: Optional[datetime] = Field(None, description="Last activity date")
    is_active: bool = Field(..., description="Whether streak is active")
    started_at: datetime = Field(..., description="Streak start timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# User Level Schemas
class UserLevelRead(BaseModel):
    """Schema for reading user levels."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="User level ID")
    user_id: int = Field(..., description="User ID")
    current_level: int = Field(..., description="Current level")
    total_xp: int = Field(..., description="Total XP earned")
    xp_to_next_level: int = Field(..., description="XP needed for next level")
    last_level_up: Optional[datetime] = Field(None, description="Last level up timestamp")
    levels_gained_today: int = Field(..., description="Levels gained today")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Computed fields
    level_progress_percentage: Optional[float] = Field(None, description="Progress to next level")
    xp_for_current_level: Optional[int] = Field(None, description="XP earned at current level")


# Leaderboard Schemas
class LeaderboardEntryRead(BaseModel):
    """Schema for reading leaderboard entries."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Leaderboard entry ID")
    user_id: int = Field(..., description="User ID")
    leaderboard_type: str = Field(..., description="Leaderboard type")
    scope: str = Field(..., description="Leaderboard scope")
    scope_id: Optional[int] = Field(None, description="Scope ID")
    score: int = Field(..., description="User's score")
    rank: int = Field(..., description="User's rank")
    period: str = Field(..., description="Time period")
    period_start: Optional[datetime] = Field(None, description="Period start")
    period_end: Optional[datetime] = Field(None, description="Period end")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # User details (populated from relationship)
    username: Optional[str] = Field(None, description="User's username")
    first_name: Optional[str] = Field(None, description="User's first name")
    last_name: Optional[str] = Field(None, description="User's last name")
    avatar_url: Optional[str] = Field(None, description="User's avatar URL")


# Badge Schemas
class BadgeBase(BaseModel):
    """Base badge schema."""
    
    name: str = Field(..., min_length=1, max_length=200, description="Badge name")
    description: str = Field(..., min_length=1, description="Badge description")
    icon_url: Optional[str] = Field(None, max_length=500, description="Badge icon URL")
    color: Optional[str] = Field(None, max_length=20, description="Badge color")
    category: str = Field(..., max_length=50, description="Badge category")
    is_limited_time: bool = Field(default=False, description="Whether badge is limited time")
    valid_from: Optional[datetime] = Field(None, description="Valid from date")
    valid_until: Optional[datetime] = Field(None, description="Valid until date")
    requirements: Optional[Dict[str, Any]] = Field(None, description="Badge requirements")


class BadgeCreate(BadgeBase):
    """Schema for creating badges."""
    pass


class BadgeUpdate(BaseModel):
    """Schema for updating badges."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)
    icon_url: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, max_length=20)
    category: Optional[str] = Field(None, max_length=50)
    is_limited_time: Optional[bool] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    requirements: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class BadgeRead(BadgeBase):
    """Schema for reading badges."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Badge ID")
    is_active: bool = Field(..., description="Whether badge is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    # Computed fields
    total_earned: Optional[int] = Field(None, description="Total users who earned this")
    is_available: Optional[bool] = Field(None, description="Whether badge is currently available")


# User Badge Schemas
class UserBadgeCreate(BaseModel):
    """Schema for awarding badges to users."""
    
    badge_id: int = Field(..., description="Badge ID")


class UserBadgeUpdate(BaseModel):
    """Schema for updating user badges."""
    
    is_equipped: Optional[bool] = Field(None, description="Whether badge is equipped")


class UserBadgeRead(BaseModel):
    """Schema for reading user badges."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="User badge ID")
    user_id: int = Field(..., description="User ID")
    badge_id: int = Field(..., description="Badge ID")
    is_equipped: bool = Field(..., description="Whether badge is equipped")
    earned_at: datetime = Field(..., description="Earned timestamp")
    
    # Badge details
    badge: Optional[BadgeRead] = Field(None, description="Badge details")


# Statistics and Summary Schemas
class UserStatsRead(BaseModel):
    """Schema for reading user gamification statistics."""
    
    total_xp: int = Field(..., description="Total XP earned")
    current_level: int = Field(..., description="Current level")
    achievements_completed: int = Field(..., description="Total achievements completed")
    badges_earned: int = Field(..., description="Total badges earned")
    longest_streak: int = Field(..., description="Longest learning streak")
    current_streak: int = Field(..., description="Current learning streak")
    
    # Rankings
    xp_rank: Optional[int] = Field(None, description="XP leaderboard rank")
    achievement_rank: Optional[int] = Field(None, description="Achievement leaderboard rank")
    
    # Recent activity
    recent_achievements: List[UserAchievementRead] = Field(default=[], description="Recent achievements")
    recent_xp_gains: List[XPRecordRead] = Field(default=[], description="Recent XP gains")


class LeaderboardRead(BaseModel):
    """Schema for reading leaderboard data."""
    
    leaderboard_type: str = Field(..., description="Leaderboard type")
    scope: str = Field(..., description="Leaderboard scope")
    period: str = Field(..., description="Time period")
    total_entries: int = Field(..., description="Total entries")
    last_updated: datetime = Field(..., description="Last update timestamp")
    
    entries: List[LeaderboardEntryRead] = Field(..., description="Leaderboard entries")


class XPSummaryRead(BaseModel):
    """Schema for XP summary statistics."""
    
    total_xp: int = Field(..., description="Total XP earned")
    xp_today: int = Field(..., description="XP earned today")
    xp_this_week: int = Field(..., description="XP earned this week")
    xp_this_month: int = Field(..., description="XP earned this month")
    
    # XP by action type
    xp_by_action: Dict[str, int] = Field(..., description="XP breakdown by action type")
    
    # Recent XP records
    recent_records: List[XPRecordRead] = Field(default=[], description="Recent XP records")
