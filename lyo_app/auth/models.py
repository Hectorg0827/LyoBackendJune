"""
Authentication models and database schemas.
Defines the User model and related database tables.
"""

from datetime import datetime
from typing import Optional, Set, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text, JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    # NOTE: These imports are commented out to avoid circular import issues
    # The relationships that reference these models are also commented out in the User class
    # from lyo_app.ai_study.models import StudySession
    # from lyo_app.ai_study.quiz_models import GeneratedQuiz
    #     from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance
    #     from lyo_app.learning.models import CourseEnrollment, LessonCompletion
    #     from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow
    from lyo_app.auth.rbac import Role

from lyo_app.core.database import Base


class User(Base):
    """User model for authentication and profile management."""
    
    __tablename__ = "users"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Authentication fields
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Profile fields
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Status fields
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Profile & Preferences - DISABLED: columns don't exist in production DB
    # locale: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    # timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    
    # Firebase Auth fields
    firebase_uid: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)
    auth_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # google, apple, email, phone
    
    # Authentication tracking
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    # locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # AI Personalization - DISABLED: columns don't exist in production DB
    # learning_profile: Mapped[Optional[dict]] = mapped_column(JSON)  # Inferred traits e.g. {"visual_score": 8}
    # user_context_summary: Mapped[Optional[str]] = mapped_column(Text)  # AI summary of user context
    
    # Multi-Tenant SaaS support
    # organization_id: Mapped[Optional[int]] = mapped_column(
    #     Integer, ForeignKey("organizations.id"), nullable=True, index=True
    # )
    # CRITICAL: Commented out because Organization.users is commented out in tenants/models.py
    # This causes mapper error: "Mapper 'Mapper[Organization(organizations)]' has no property 'users'"
    # organization = relationship("lyo_app.tenants.models.Organization", back_populates="users", lazy="select")
    
    # RBAC relationships
    roles = relationship("lyo_app.auth.rbac.Role", secondary="user_roles", back_populates="users", lazy="noload", viewonly=True)
    
    # Relationships - defined with string names to avoid circular imports
    created_study_groups = relationship("lyo_app.community.models.StudyGroup", back_populates="creator", lazy="noload", viewonly=True)
    group_memberships = relationship("lyo_app.community.models.GroupMembership", foreign_keys="[lyo_app.community.models.GroupMembership.user_id]", back_populates="user", lazy="noload", viewonly=True)
    organized_events = relationship("lyo_app.community.models.CommunityEvent", back_populates="organizer", lazy="noload", viewonly=True)
    event_attendances = relationship("lyo_app.community.models.EventAttendance", back_populates="user", lazy="noload", viewonly=True)
    
    # Learning relationships  
    course_enrollments = relationship("lyo_app.learning.models.CourseEnrollment", back_populates="user", lazy="noload", viewonly=True)
    lesson_completions = relationship("lyo_app.learning.models.LessonCompletion", back_populates="user", lazy="noload", viewonly=True)
    
    # Feeds relationships
    posts = relationship("lyo_app.feeds.models.Post", back_populates="author", lazy="noload", viewonly=True)
    comments = relationship("lyo_app.feeds.models.Comment", back_populates="author", lazy="noload", viewonly=True)
    post_reactions = relationship("lyo_app.feeds.models.PostReaction", back_populates="user", lazy="noload", viewonly=True)
    comment_reactions = relationship("lyo_app.feeds.models.CommentReaction", back_populates="user", lazy="noload", viewonly=True)
    followers = relationship("lyo_app.feeds.models.UserFollow", foreign_keys="[lyo_app.feeds.models.UserFollow.following_id]", back_populates="following", lazy="noload", viewonly=True)
    following = relationship("lyo_app.feeds.models.UserFollow", foreign_keys="[lyo_app.feeds.models.UserFollow.follower_id]", back_populates="follower", lazy="noload", viewonly=True)
    
    # AI Agents relationships
    engagement_state = relationship("lyo_app.ai_agents.models.UserEngagementState", back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="noload", viewonly=True)
    mentor_interactions = relationship("lyo_app.ai_agents.models.MentorInteraction", back_populates="user", cascade="all, delete-orphan", lazy="noload", viewonly=True)
    
    # AI Study relationships
    study_sessions = relationship("lyo_app.ai_study.models.StudySession", back_populates="user", lazy="noload", viewonly=True)
    generated_quizzes = relationship("lyo_app.ai_study.models.GeneratedQuiz", back_populates="user", lazy="noload", viewonly=True)
    quiz_attempts = relationship("lyo_app.ai_study.models.QuizAttempt", back_populates="user", lazy="noload", viewonly=True)
    study_analytics = relationship("lyo_app.ai_study.models.StudySessionAnalytics", back_populates="user", lazy="noload", viewonly=True)
    
    # Enhanced models relationships
    courses = relationship("lyo_app.learning.models.Course", back_populates="instructor", cascade="all, delete-orphan")
    tasks = relationship("lyo_app.models.enhanced.Task", back_populates="user", cascade="all, delete-orphan")
    push_devices = relationship("lyo_app.models.enhanced.PushDevice", back_populates="user", cascade="all, delete-orphan")
    gamification_profile = relationship("lyo_app.models.enhanced.GamificationProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    # Refresh Tokens
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"


class RefreshToken(Base):
    """Refresh token for JWT authentication."""
    
    __tablename__ = "refresh_tokens"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Device/session information
    device_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # User agent, IP, etc.
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    
    # Relationship to user
    user = relationship("User", back_populates="refresh_tokens")
    
    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id})>"
