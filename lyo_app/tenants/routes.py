"""
Tenant management API routes.
Provides endpoints for organization management, API key generation, and usage stats.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.core.database import get_db
from lyo_app.auth.jwt_auth import get_current_user, get_optional_current_user
from lyo_app.auth.models import User
from lyo_app.tenants.migrations import run_tenant_migrations
from lyo_app.auth.api_key_auth import create_api_key, get_api_key_org, generate_api_key, hash_api_key


class BootstrapResponse(BaseModel):
    """Response for the bootstrap endpoint."""
    message: str
    tables_created: bool
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    api_key: Optional[str] = None  # Full key shown only once!


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_lyo_inc(
    db: AsyncSession = Depends(get_db),
    secret: str = "lyo-bootstrap-2024"  # Simple secret to prevent abuse
):
    """
    Bootstrap endpoint to create multi-tenant tables and Lyo Inc organization.
    
    This is a one-time setup endpoint that:
    1. Runs database migrations to create tenant tables
    2. Creates the "Lyo Inc" organization  
    3. Generates the first API key
    
    Call this ONCE after deploying the multi-tenant update.
    
    Query param: secret=lyo-bootstrap-2024
    """
    from sqlalchemy import text
    
    # Simple secret check
    if secret != "lyo-bootstrap-2024":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bootstrap secret"
        )
    
    try:
        # Step 1: Run migrations
        tables_created = await run_tenant_migrations(db)
        logger.info(f"Migration result: tables_created={tables_created}")
        
        # Step 2: Check if Lyo Inc already exists
        result = await db.execute(
            text("SELECT id, name FROM organizations WHERE slug = 'lyo-inc'")
        )
        existing = result.fetchone()
        
        if existing:
            logger.info(f"Lyo Inc already exists (id={existing[0]})")
            return BootstrapResponse(
                message="Lyo Inc organization already exists. Use /api/v1/tenants/api-keys to generate new keys.",
                tables_created=tables_created,
                organization_id=existing[0],
                organization_name=existing[1],
                api_key=None
            )
        
        # Step 3: Create Lyo Inc organization
        result = await db.execute(
            text("""
                INSERT INTO organizations (name, slug, plan_tier, contact_email, is_active)
                VALUES ('Lyo Inc', 'lyo-inc', 'enterprise', 'hector.garcia0827@gmail.com', TRUE)
                RETURNING id
            """)
        )
        org_id = result.fetchone()[0]
        await db.commit()
        logger.info(f"Created Lyo Inc organization (id={org_id})")
        
        # Step 4: Generate API key
        full_key, key_prefix, key_hash = generate_api_key()
        
        await db.execute(
            text("""
                INSERT INTO api_keys (organization_id, key_prefix, key_hash, name, description, is_active)
                VALUES (:org_id, :key_prefix, :key_hash, 'Lyo iOS App Key', 'Auto-generated for Lyo iOS app', TRUE)
            """),
            {"org_id": org_id, "key_prefix": key_prefix, "key_hash": key_hash}
        )
        await db.commit()
        
        logger.info(f"Created API key for Lyo Inc: {key_prefix}...")
        
        return BootstrapResponse(
            message="🎉 Lyo Inc organization created successfully! Save the API key - it will not be shown again!",
            tables_created=tables_created,
            organization_id=org_id,
            organization_name="Lyo Inc",
            api_key=full_key
        )
        
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bootstrap failed: {str(e)}"
        )
from lyo_app.tenants.models import Organization, APIKey, PlanTier
from lyo_app.tenants.usage import UsageLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["Tenants"])


# =============================================================================
# SCHEMAS
# =============================================================================

class OrganizationCreate(BaseModel):
    """Schema for creating a new organization."""
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    contact_email: Optional[str] = None
    plan_tier: str = Field(default="free")


class OrganizationResponse(BaseModel):
    """Schema for organization response."""
    id: int
    name: str
    slug: str
    plan_tier: str
    is_active: bool
    contact_email: Optional[str]
    monthly_api_calls: int
    monthly_ai_tokens: int
    rate_limit_per_minute: int
    ai_calls_per_day: int
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreate(BaseModel):
    """Schema for creating a new API key."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    expires_at: Optional[datetime] = None


class APIKeyResponse(BaseModel):
    """Schema for API key response (without the actual key)."""
    id: int
    key_prefix: str
    name: str
    description: Optional[str]
    is_active: bool
    last_used_at: Optional[datetime]
    total_requests: int
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreatedResponse(BaseModel):
    """Schema for newly created API key (includes the full key ONCE)."""
    api_key: str  # The full key - shown only once!
    key_info: APIKeyResponse


class SetupResponse(BaseModel):
    """Response for the initial setup endpoint."""
    organization: OrganizationResponse
    api_key: str  # Full key shown only once
    message: str


class UsageStatsResponse(BaseModel):
    """Schema for usage statistics."""
    organization_id: int
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_tokens: int
    estimated_cost_usd: float


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/setup", response_model=SetupResponse, status_code=status.HTTP_201_CREATED)
async def initial_setup(
    request: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Initial setup endpoint for creating an organization and first API key.
    
    This is typically used by the Lyo team to create the "Lyo Inc" organization
    or by new SaaS customers to set up their tenant.
    
    Requires authentication (admin or superuser recommended).
    """
    # Check if user is superuser
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can create organizations"
        )
    
    # Check if slug already exists
    existing = await db.execute(
        select(Organization).where(Organization.slug == request.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organization with slug '{request.slug}' already exists"
        )
    
    # Create organization
    org = Organization(
        name=request.name,
        slug=request.slug,
        contact_email=request.contact_email or current_user.email,
        plan_tier=request.plan_tier
    )
    db.add(org)
    await db.flush()
    
    # Create first API key
    full_key, api_key = await create_api_key(
        db=db,
        organization_id=org.id,
        name="Default API Key",
        description="Auto-generated during organization setup"
    )
    
    # Assign current user to this organization
    current_user.organization_id = org.id
    await db.commit()
    await db.refresh(org)
    
    logger.info(f"Created organization '{org.name}' (id={org.id}) by user {current_user.email}")
    
    return SetupResponse(
        organization=OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            plan_tier=org.plan_tier,
            is_active=org.is_active,
            contact_email=org.contact_email,
            monthly_api_calls=org.monthly_api_calls,
            monthly_ai_tokens=org.monthly_ai_tokens,
            rate_limit_per_minute=org.rate_limit_per_minute,
            ai_calls_per_day=org.ai_calls_per_day,
            created_at=org.created_at
        ),
        api_key=full_key,
        message="Organization created successfully. Save your API key - it will not be shown again!"
    )


@router.get("/me", response_model=OrganizationResponse)
async def get_my_organization(
    org: Organization = Depends(get_api_key_org),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current organization based on API key.
    
    Use this to verify your API key is working and see your org's details.
    """
    if not org:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid API key required"
        )
    
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        plan_tier=org.plan_tier,
        is_active=org.is_active,
        contact_email=org.contact_email,
        monthly_api_calls=org.monthly_api_calls,
        monthly_ai_tokens=org.monthly_ai_tokens,
        rate_limit_per_minute=org.rate_limit_per_minute,
        ai_calls_per_day=org.ai_calls_per_day,
        created_at=org.created_at
    )


@router.post("/api-keys", response_model=APIKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_new_api_key(
    request: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new API key for the user's organization.
    
    The full API key is returned ONLY in this response.
    Store it securely - it cannot be retrieved again.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not assigned to an organization"
        )
    
    full_key, api_key = await create_api_key(
        db=db,
        organization_id=current_user.organization_id,
        name=request.name,
        description=request.description,
        expires_at=request.expires_at
    )
    
    return APIKeyCreatedResponse(
        api_key=full_key,
        key_info=APIKeyResponse(
            id=api_key.id,
            key_prefix=api_key.key_prefix,
            name=api_key.name,
            description=api_key.description,
            is_active=api_key.is_active,
            last_used_at=api_key.last_used_at,
            total_requests=api_key.total_requests,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at
        )
    )


@router.get("/api-keys", response_model=List[APIKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all API keys for the user's organization.
    
    Note: The actual key values are not returned (they're hashed in storage).
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not assigned to an organization"
        )
    
    result = await db.execute(
        select(APIKey)
        .where(APIKey.organization_id == current_user.organization_id)
        .order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()
    
    return [
        APIKeyResponse(
            id=key.id,
            key_prefix=key.key_prefix,
            name=key.name,
            description=key.description,
            is_active=key.is_active,
            last_used_at=key.last_used_at,
            total_requests=key.total_requests,
            expires_at=key.expires_at,
            created_at=key.created_at
        )
        for key in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Revoke (deactivate) an API key.
    
    The key will immediately stop working for all requests.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not assigned to an organization"
        )
    
    result = await db.execute(
        select(APIKey)
        .where(
            APIKey.id == key_id,
            APIKey.organization_id == current_user.organization_id
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    api_key.is_active = False
    await db.commit()
    
    logger.info(f"API key {key_id} revoked by user {current_user.email}")


@router.get("/usage", response_model=UsageStatsResponse)
async def get_usage_stats(
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_api_key_org)
):
    """
    Get usage statistics for the current billing period.
    """
    if not org:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid API key required"
        )
    
    # Calculate current month period
    now = datetime.utcnow()
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Query usage stats
    result = await db.execute(
        select(
            func.count(UsageLog.id).label("total_requests"),
            func.sum(UsageLog.tokens_used).label("total_tokens"),
            func.sum(UsageLog.cost_usd).label("total_cost")
        )
        .where(
            UsageLog.organization_id == org.id,
            UsageLog.created_at >= period_start
        )
    )
    row = result.one()
    
    return UsageStatsResponse(
        organization_id=org.id,
        period_start=period_start,
        period_end=now,
        total_requests=row.total_requests or 0,
        total_tokens=row.total_tokens or 0,
        estimated_cost_usd=float(row.total_cost or 0)
    )
