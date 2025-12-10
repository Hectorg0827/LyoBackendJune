"""
Auth Models - Database Models for Authentication
==============================================

SQLAlchemy models for user management, authentication, and RBAC.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from datetime import datetime
from typing import List, Optional
from enum import Enum

from lyo_app.core.database_v2 import Base


class UserRole(str, Enum):
    """User roles for RBAC."""
    STUDENT = "student"
    TEACHER = "teacher"
    GUARDIAN = "guardian"
    ADMIN = "admin"


class User(Base):
    """User account model with RBAC support."""
    
    __tablename__ = "users"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Authentication fields
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Profile information
    full_name = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    
    # RBAC - stored as array for multiple roles
    roles = Column(ARRAY(String), default=["student"], nullable=False)
    
    # Privacy settings
    is_private = Column(Boolean, default=True)  # Default private for students
    
    # Authentication metadata
    last_login = Column(DateTime(timezone=True), nullable=True)
    login_count = Column(Integer, default=0)
    failed_login_attempts = Column(Integer, default=0)
    last_failed_login = Column(DateTime(timezone=True), nullable=True)
    
    # Account security
    password_changed_at = Column(DateTime(timezone=True), default=func.now())
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String, nullable=True)  # TOTP secret
    backup_codes = Column(JSON, nullable=True)  # Encrypted backup codes
    
    # Apple Sign-In support
    apple_user_id = Column(String, unique=True, nullable=True, index=True)
    
    # Geographic and device info
    registration_ip = Column(String, nullable=True)
    last_ip = Column(String, nullable=True)
    timezone = Column(String, default="UTC")
    preferred_language = Column(String, default="en")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    profiles = relationship("Profile", back_populates="user", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_users_email_active", "email", "is_active"),
        Index("idx_users_roles", "roles"),
        Index("idx_users_created_at", "created_at"),
    )
    
    def has_role(self, role: UserRole) -> bool:
        """Check if user has specific role."""
        return role.value in (self.roles or [])
    
    def add_role(self, role: UserRole) -> None:
        """Add role to user."""
        if not self.roles:
            self.roles = []
        if role.value not in self.roles:
            self.roles = self.roles + [role.value]
    
    def remove_role(self, role: UserRole) -> None:
        """Remove role from user."""
        if self.roles and role.value in self.roles:
            self.roles = [r for r in self.roles if r != role.value]
    
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.has_role(UserRole.ADMIN)
    
    def is_teacher(self) -> bool:
        """Check if user is teacher."""
        return self.has_role(UserRole.TEACHER)
    
    def is_student(self) -> bool:
        """Check if user is student."""
        return self.has_role(UserRole.STUDENT)
    
    def can_dm(self, other_user: "User") -> bool:
        """Check if user can direct message another user."""
        # Students can only DM teachers, guardians, and admins
        if self.is_student():
            return other_user.is_teacher() or other_user.is_admin()
        
        # Teachers and admins can DM anyone
        if self.is_teacher() or self.is_admin():
            return True
        
        # Guardians can DM their students and teachers
        return True
    
    def __repr__(self):
        return f"<User {self.email}>"


class RefreshToken(Base):
    """Refresh token for JWT authentication."""
    
    __tablename__ = "refresh_tokens"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Token data
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Token status
    is_revoked = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Device/session information
    device_info = Column(JSON, nullable=True)  # User agent, IP, etc.
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="refresh_tokens")
    
    # Indexes
    __table_args__ = (
        Index("idx_refresh_tokens_user_active", "user_id", "is_revoked"),
        Index("idx_refresh_tokens_expires", "expires_at"),
    )
    
    def is_valid(self) -> bool:
        """Check if token is valid (not revoked and not expired)."""
        return not self.is_revoked and self.expires_at > datetime.utcnow()
    
    def __repr__(self):
        return f"<RefreshToken {self.token[:8]}... for user {self.user_id}>"


class LoginAttempt(Base):
    """Track login attempts for security monitoring."""
    
    __tablename__ = "login_attempts"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Attempt details
    email = Column(String, index=True, nullable=False)
    ip_address = Column(String, nullable=False)
    user_agent = Column(Text, nullable=True)
    success = Column(Boolean, nullable=False)
    
    # Failure details
    failure_reason = Column(String, nullable=True)  # invalid_password, account_disabled, etc.
    
    # Geographic info (optional)
    country_code = Column(String(2), nullable=True)
    city = Column(String, nullable=True)
    
    # Timestamp
    attempted_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_login_attempts_email_time", "email", "attempted_at"),
        Index("idx_login_attempts_ip_time", "ip_address", "attempted_at"),
        Index("idx_login_attempts_success", "success", "attempted_at"),
    )
    
    def __repr__(self):
        return f"<LoginAttempt {self.email} from {self.ip_address} - {'Success' if self.success else 'Failed'}>"


class SecurityEvent(Base):
    """Track security events for monitoring and alerting."""
    
    __tablename__ = "security_events"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Event details
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_type = Column(String, nullable=False)  # password_change, 2fa_enabled, suspicious_login, etc.
    description = Column(Text, nullable=False)
    
    # Context
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    event_metadata = Column(JSON, nullable=True)  # Additional event-specific data
    
    # Risk assessment
    risk_level = Column(String, default="low")  # low, medium, high, critical
    
    # Timestamp
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_security_events_user_type", "user_id", "event_type"),
        Index("idx_security_events_risk_time", "risk_level", "occurred_at"),
        Index("idx_security_events_ip", "ip_address", "occurred_at"),
    )
    
    def __repr__(self):
        return f"<SecurityEvent {self.event_type} - {self.risk_level}>"
