"""
Authentication models and database schemas.
Defines the User model and related database tables.
"""

from datetime import datetime
from typing import Optional, Set, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance
    from lyo_app.learning.models import CourseEnrollment, LessonCompletion
    from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow
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
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships - defined with string names to avoid circular imports
    # Community relationships
    created_study_groups = relationship("StudyGroup", back_populates="creator", lazy="select")
    group_memberships = relationship("GroupMembership", foreign_keys="GroupMembership.user_id", back_populates="user", lazy="select")
    organized_events = relationship("CommunityEvent", back_populates="organizer", lazy="select")
    event_attendances = relationship("EventAttendance", back_populates="user", lazy="select")
    
    # Learning relationships  
    course_enrollments = relationship("CourseEnrollment", back_populates="user", lazy="select")
    lesson_completions = relationship("LessonCompletion", back_populates="user", lazy="select")
    
    # Feeds relationships
    posts = relationship("Post", back_populates="author", lazy="select")
    comments = relationship("Comment", back_populates="author", lazy="select")
    post_reactions = relationship("PostReaction", back_populates="user", lazy="select")
    comment_reactions = relationship("CommentReaction", back_populates="user", lazy="select")
    followers = relationship("UserFollow", foreign_keys="UserFollow.followed_id", back_populates="followed", lazy="select")
    following = relationship("UserFollow", foreign_keys="UserFollow.follower_id", back_populates="follower", lazy="select")
    
    # RBAC relationships
    roles = relationship("Role", secondary="user_roles", back_populates="users", lazy="select")
    
    # AI Agents relationships
    engagement_state = relationship("UserEngagementState", back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="select")
    mentor_interactions = relationship("MentorInteraction", back_populates="user", cascade="all, delete-orphan", lazy="select")
    
    # AI Study Mode relationships
    study_sessions = relationship("StudySession", back_populates="user", cascade="all, delete-orphan", lazy="select")
    generated_quizzes = relationship("GeneratedQuiz", back_populates="user", cascade="all, delete-orphan", lazy="select")
    quiz_attempts = relationship("QuizAttempt", back_populates="user", cascade="all, delete-orphan", lazy="select")
    study_analytics = relationship("StudySessionAnalytics", back_populates="user", cascade="all, delete-orphan", lazy="select")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
    
    def has_permission(self, permission_name: str) -> bool:
        """Check if user has a specific permission through their roles."""
        for role in self.roles:
            if role.has_permission(permission_name):
                return True
        return False
    
    def get_permissions(self) -> Set[str]:
        """Get all permissions for this user through their roles."""
        permissions = set()
        for role in self.roles:
            permissions.update(role.get_permission_names())
        return permissions
    
    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role."""
        return any(role.name == role_name for role in self.roles)
    
    def get_role_names(self) -> Set[str]:
        """Get all role names for this user."""
        return {role.name for role in self.roles}
