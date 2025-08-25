"""
Role-Based Access Control (RBAC) system for LyoApp.
Provides fine-grained permissions and role management.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Set, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from lyo_app.auth.models import User

from lyo_app.core.database import Base


class PermissionType(str, Enum):
    """System-wide permission types."""
    # Auth permissions
    CREATE_USER = "create_user"
    UPDATE_USER = "update_user"
    DELETE_USER = "delete_user"
    VIEW_USER = "view_user"
    MANAGE_ROLES = "manage_roles"
    
    # Learning permissions
    CREATE_COURSE = "create_course"
    UPDATE_COURSE = "update_course"
    DELETE_COURSE = "delete_course"
    VIEW_COURSE = "view_course"
    ENROLL_COURSE = "enroll_course"
    COMPLETE_LESSON = "complete_lesson"
    
    # Community permissions
    CREATE_GROUP = "create_group"
    UPDATE_GROUP = "update_group"
    DELETE_GROUP = "delete_group"
    JOIN_GROUP = "join_group"
    MANAGE_GROUP = "manage_group"
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    ATTEND_EVENT = "attend_event"
    
    # Feeds permissions
    CREATE_POST = "create_post"
    UPDATE_POST = "update_post"
    DELETE_POST = "delete_post"
    COMMENT_POST = "comment_post"
    REACT_POST = "react_post"
    FOLLOW_USER = "follow_user"
    
    # Gamification permissions
    VIEW_BADGES = "view_badges"
    AWARD_BADGE = "award_badge"
    VIEW_LEADERBOARD = "view_leaderboard"
    MANAGE_POINTS = "manage_points"
    
    # System permissions
    ADMIN_ACCESS = "admin_access"
    MODERATE_CONTENT = "moderate_content"
    VIEW_ANALYTICS = "view_analytics"
    MANAGE_SYSTEM = "manage_system"


class RoleType(str, Enum):
    """Predefined system roles."""
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"
    INSTRUCTOR = "instructor"
    STUDENT = "student"
    GUEST = "guest"


# Association table for many-to-many relationship between roles and permissions
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)

# Association table for many-to-many relationship between users and roles
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


class Permission(Base):
    """Permission model for fine-grained access control."""
    
    __tablename__ = "permissions"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    # Relationships
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")
    
    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, name='{self.name}')>"


class Role(Base):
    """Role model for grouping permissions."""
    
    __tablename__ = "roles"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
    users = relationship("User", secondary=user_roles, back_populates="roles")
    
    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name='{self.name}')>"
    
    def has_permission(self, permission_name: str) -> bool:
        """Check if this role has a specific permission."""
        return any(perm.name == permission_name for perm in self.permissions)
    
    def get_permission_names(self) -> Set[str]:
        """Get all permission names for this role."""
        return {perm.name for perm in self.permissions}


# Default role configurations
DEFAULT_ROLE_PERMISSIONS = {
    RoleType.SUPER_ADMIN: [perm.value for perm in PermissionType],
    
    RoleType.ADMIN: [
        PermissionType.CREATE_USER.value,
        PermissionType.UPDATE_USER.value,
        PermissionType.VIEW_USER.value,
        PermissionType.MANAGE_ROLES.value,
        PermissionType.CREATE_COURSE.value,
        PermissionType.UPDATE_COURSE.value,
        PermissionType.DELETE_COURSE.value,
        PermissionType.VIEW_COURSE.value,
        PermissionType.CREATE_GROUP.value,
        PermissionType.UPDATE_GROUP.value,
        PermissionType.DELETE_GROUP.value,
        PermissionType.MANAGE_GROUP.value,
        PermissionType.CREATE_EVENT.value,
        PermissionType.UPDATE_EVENT.value,
        PermissionType.DELETE_EVENT.value,
        PermissionType.MODERATE_CONTENT.value,
        PermissionType.VIEW_ANALYTICS.value,
        PermissionType.AWARD_BADGE.value,
        PermissionType.MANAGE_POINTS.value,
    ],
    
    RoleType.MODERATOR: [
        PermissionType.VIEW_USER.value,
        PermissionType.VIEW_COURSE.value,
        PermissionType.UPDATE_GROUP.value,
        PermissionType.MANAGE_GROUP.value,
        PermissionType.UPDATE_EVENT.value,
        PermissionType.MODERATE_CONTENT.value,
        PermissionType.DELETE_POST.value,
        PermissionType.VIEW_ANALYTICS.value,
    ],
    
    RoleType.INSTRUCTOR: [
        PermissionType.VIEW_USER.value,
        PermissionType.CREATE_COURSE.value,
        PermissionType.UPDATE_COURSE.value,
        PermissionType.VIEW_COURSE.value,
        PermissionType.CREATE_GROUP.value,
        PermissionType.UPDATE_GROUP.value,
        PermissionType.MANAGE_GROUP.value,
        PermissionType.CREATE_EVENT.value,
        PermissionType.UPDATE_EVENT.value,
        PermissionType.CREATE_POST.value,
        PermissionType.UPDATE_POST.value,
        PermissionType.DELETE_POST.value,
        PermissionType.COMMENT_POST.value,
        PermissionType.REACT_POST.value,
        PermissionType.FOLLOW_USER.value,
        PermissionType.AWARD_BADGE.value,
        PermissionType.VIEW_LEADERBOARD.value,
    ],
    
    RoleType.STUDENT: [
        PermissionType.VIEW_USER.value,
        PermissionType.UPDATE_USER.value,  # Own profile only
        PermissionType.VIEW_COURSE.value,
        PermissionType.ENROLL_COURSE.value,
        PermissionType.COMPLETE_LESSON.value,
        PermissionType.JOIN_GROUP.value,
        PermissionType.ATTEND_EVENT.value,
        PermissionType.CREATE_POST.value,
        PermissionType.UPDATE_POST.value,  # Own posts only
        PermissionType.COMMENT_POST.value,
        PermissionType.REACT_POST.value,
        PermissionType.FOLLOW_USER.value,
        PermissionType.VIEW_BADGES.value,
        PermissionType.VIEW_LEADERBOARD.value,
    ],
    
    RoleType.GUEST: [
        PermissionType.VIEW_COURSE.value,
        PermissionType.VIEW_USER.value,  # Limited view
        PermissionType.VIEW_BADGES.value,
        PermissionType.VIEW_LEADERBOARD.value,
    ],
}
