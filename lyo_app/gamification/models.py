"""
Gamification models for user engagement and progress tracking.
Defines XP, achievements, streaks, and reward systems.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text, ForeignKey,
    Enum as SQLEnum, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base


class XPActionType(str, Enum):
    """Types of actions that can earn XP."""
    LESSON_COMPLETED = "lesson_completed"
    COURSE_COMPLETED = "course_completed"
    POST_CREATED = "post_created"
    COMMENT_CREATED = "comment_created"
    DAILY_LOGIN = "daily_login"
    STREAK_MILESTONE = "streak_milestone"
    STUDY_GROUP_JOINED = "study_group_joined"
    EVENT_ATTENDED = "event_attended"
    PROFILE_COMPLETED = "profile_completed"
    FIRST_ACHIEVEMENT = "first_achievement"


class AchievementType(str, Enum):
    """Types of achievements."""
    LEARNING = "learning"        # Course/lesson related
    SOCIAL = "social"           # Community engagement
    STREAK = "streak"           # Consistency rewards
    MILESTONE = "milestone"     # Progress milestones
    SPECIAL = "special"         # Special events/holidays


class AchievementRarity(str, Enum):
    """Achievement rarity levels."""
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class StreakType(str, Enum):
    """Types of learning streaks."""
    DAILY_LOGIN = "daily_login"
    LESSON_COMPLETION = "lesson_completion"
    STUDY_SESSION = "study_session"
    COMMUNITY_ENGAGEMENT = "community_engagement"


class UserXP(Base):
    """
    User experience points tracking.
    Records XP earned from various activities.
    """
    
    __tablename__ = "user_xp"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(SQLEnum(XPActionType), nullable=False, index=True)
    xp_earned = Column(Integer, nullable=False)
    
    # Optional context for the XP action
    context_type = Column(String(50), nullable=True)  # "course", "lesson", "post", etc.
    context_id = Column(Integer, nullable=True)       # ID of the related entity
    context_data = Column(JSON, nullable=True)        # Additional context data
    
    # Metadata
    earned_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships - commented out due to missing back_populates in User model
    # user = relationship("User", back_populates="xp_records")


class Achievement(Base):
    """
    Achievement definitions.
    Defines available achievements and their requirements.
    """
    
    __tablename__ = "achievements"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False)
    icon_url = Column(String(500), nullable=True)
    
    # Achievement properties
    type = Column(SQLEnum(AchievementType), nullable=False, index=True)
    rarity = Column(SQLEnum(AchievementRarity), nullable=False, default=AchievementRarity.COMMON)
    xp_reward = Column(Integer, nullable=False, default=0)
    
    # Achievement criteria (stored as JSON)
    criteria = Column(JSON, nullable=False)  # Flexible criteria definition
    
    # Metadata
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    user_achievements = relationship("UserAchievement", back_populates="achievement")


class UserAchievement(Base):
    """
    User's earned achievements.
    Tracks which achievements users have unlocked.
    """
    
    __tablename__ = "user_achievements"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False, index=True)
    
    # Achievement progress and completion
    progress_data = Column(JSON, nullable=True)  # Current progress toward achievement
    is_completed = Column(Boolean, nullable=False, default=False)
    
    # Metadata
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True, index=True)
    
    # Relationships
    # user = relationship("User", back_populates="user_achievements")
    achievement = relationship("Achievement", back_populates="user_achievements")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),
    )


class Streak(Base):
    """
    User learning streaks.
    Tracks consecutive daily activities.
    """
    
    __tablename__ = "streaks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    streak_type = Column(SQLEnum(StreakType), nullable=False, index=True)
    
    # Streak data
    current_count = Column(Integer, nullable=False, default=0)
    longest_count = Column(Integer, nullable=False, default=0)
    last_activity_date = Column(DateTime, nullable=True, index=True)
    
    # Streak status
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Metadata
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    # user = relationship("User", back_populates="streaks")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'streak_type', name='uq_user_streak_type'),
    )


class UserLevel(Base):
    """
    User level and progress tracking.
    Manages user levels based on total XP.
    """
    
    __tablename__ = "user_levels"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    
    # Level data
    current_level = Column(Integer, nullable=False, default=1)
    total_xp = Column(Integer, nullable=False, default=0)
    xp_to_next_level = Column(Integer, nullable=False, default=100)
    
    # Level history
    last_level_up = Column(DateTime, nullable=True)
    levels_gained_today = Column(Integer, nullable=False, default=0)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    # user = relationship("User", back_populates="user_level")


class LeaderboardEntry(Base):
    """
    Leaderboard entries for competitive elements.
    Tracks user rankings in various categories.
    """
    
    __tablename__ = "leaderboard_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Leaderboard type and scope
    leaderboard_type = Column(String(50), nullable=False, index=True)  # "xp", "streaks", "achievements"
    scope = Column(String(50), nullable=False, default="global")       # "global", "course", "group"
    scope_id = Column(Integer, nullable=True)                          # ID for scoped leaderboards
    
    # Ranking data
    score = Column(Integer, nullable=False, default=0)
    rank = Column(Integer, nullable=False, default=0)
    
    # Time period
    period = Column(String(20), nullable=False, default="all_time")    # "daily", "weekly", "monthly", "all_time"
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    
    # Metadata
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    # user = relationship("User", back_populates="leaderboard_entries")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'leaderboard_type', 'scope', 'scope_id', 'period', 
                        name='uq_leaderboard_entry'),
    )


class Badge(Base):
    """
    Special badges for recognition.
    Visual rewards for achievements and milestones.
    """
    
    __tablename__ = "badges"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False)
    icon_url = Column(String(500), nullable=True)
    color = Column(String(20), nullable=True)  # Hex color code
    
    # Badge properties
    category = Column(String(50), nullable=False, index=True)
    is_limited_time = Column(Boolean, nullable=False, default=False)
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    
    # Requirements
    requirements = Column(JSON, nullable=True)  # Criteria for earning the badge
    
    # Metadata
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    user_badges = relationship("UserBadge", back_populates="badge")


class UserBadge(Base):
    """
    User's earned badges.
    """
    
    __tablename__ = "user_badges"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    badge_id = Column(Integer, ForeignKey("badges.id"), nullable=False, index=True)
    
    # Badge details
    is_equipped = Column(Boolean, nullable=False, default=False)  # Whether badge is displayed
    
    # Metadata
    earned_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    # user = relationship("User", back_populates="user_badges")
    badge = relationship("Badge", back_populates="user_badges")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'badge_id', name='uq_user_badge'),
    )
