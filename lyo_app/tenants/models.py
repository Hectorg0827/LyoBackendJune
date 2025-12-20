"""
Multi-tenant database models for SaaS architecture.
Defines Organization and APIKey models for tenant management.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import Boolean, DateTime, String, Integer, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lyo_app.core.database import Base


class PlanTier(str, Enum):
    """Available subscription plan tiers."""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class Organization(Base):
    """
    Organization (Tenant) model for multi-tenant SaaS.
    Each organization can have multiple users and API keys.
    """
    
    __tablename__ = "organizations"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Organization identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)  # lyo-inc, acme-corp
    
    # Plan & Billing
    plan_tier: Mapped[str] = mapped_column(String(50), default=PlanTier.FREE.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Contact info
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Usage Tracking (reset monthly)
    monthly_api_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    monthly_ai_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Rate limit overrides (null = use plan defaults)
    custom_rate_limit: Mapped[Optional[int]] = mapped_column(Integer)  # requests per minute
    custom_ai_limit: Mapped[Optional[int]] = mapped_column(Integer)    # AI calls per day
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    users = relationship("lyo_app.auth.models.User", back_populates="organization", lazy="select")
    api_keys = relationship("lyo_app.tenants.models.APIKey", back_populates="organization", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}', plan='{self.plan_tier}')>"
    
    @property
    def rate_limit_per_minute(self) -> int:
        """Get the effective rate limit for this organization."""
        if self.custom_rate_limit:
            return self.custom_rate_limit
        
        # Plan-based defaults
        limits = {
            PlanTier.FREE.value: 60,
            PlanTier.PRO.value: 600,
            PlanTier.ENTERPRISE.value: 6000,
        }
        return limits.get(self.plan_tier, 60)
    
    @property
    def ai_calls_per_day(self) -> int:
        """Get the effective AI call limit for this organization."""
        if self.custom_ai_limit:
            return self.custom_ai_limit
        
        limits = {
            PlanTier.FREE.value: 100,
            PlanTier.PRO.value: 10000,
            PlanTier.ENTERPRISE.value: 100000,
        }
        return limits.get(self.plan_tier, 100)


class APIKey(Base):
    """
    API Key model for authenticating external applications.
    Each key is tied to an organization for tenant isolation.
    """
    
    __tablename__ = "api_keys"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Foreign key to organization
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # Key identification (prefix shown to user, hash for lookup)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)  # lyo_sk_live_abc...
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)  # SHA256
    
    # Human-readable name
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Production Key", "Test Key"
    description: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Per-key rate limit override (null = use org defaults)
    rate_limit_override: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Expiration (null = never expires)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    # Relationships
    organization = relationship("lyo_app.tenants.models.Organization", back_populates="api_keys")
    
    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name='{self.name}', org_id={self.organization_id})>"
    
    @property
    def is_expired(self) -> bool:
        """Check if the API key has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Check if the API key is valid (active and not expired)."""
        return self.is_active and not self.is_expired
