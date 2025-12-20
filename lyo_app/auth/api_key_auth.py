"""
API Key Authentication for SaaS multi-tenant architecture.
Provides API key generation, validation, and dependency injection.
"""

import secrets
import hashlib
import logging
from typing import Optional
from datetime import datetime

from fastapi import Security, HTTPException, Depends, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.core.database import get_db
from lyo_app.tenants.models import APIKey, Organization

logger = logging.getLogger(__name__)

# Header name for API key
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    
    Returns:
        Tuple of (full_key, key_prefix, key_hash)
        - full_key: The complete key to show to the user ONCE
        - key_prefix: First 16 chars for display (lyo_sk_live_xxxx)
        - key_hash: SHA256 hash for storage and lookup
    """
    # Generate 32 bytes of random data
    raw_bytes = secrets.token_bytes(32)
    raw_key = secrets.token_urlsafe(32)
    
    # Create full key with prefix
    full_key = f"lyo_sk_live_{raw_key}"
    
    # Create prefix for display (first 20 chars)
    key_prefix = full_key[:20]
    
    # Create hash for storage
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    
    return full_key, key_prefix, key_hash


def hash_api_key(api_key: str) -> str:
    """Hash an API key for lookup."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def validate_api_key(
    api_key: str,
    db: AsyncSession
) -> Optional[APIKey]:
    """
    Validate an API key and return the key object if valid.
    
    Args:
        api_key: The full API key string
        db: Database session
        
    Returns:
        APIKey object if valid, None otherwise
    """
    if not api_key or not api_key.startswith("lyo_sk_"):
        return None
    
    key_hash = hash_api_key(api_key)
    
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_hash == key_hash)
        .options(selectinload(APIKey.organization))
    )
    api_key_obj = result.scalar_one_or_none()
    
    if not api_key_obj:
        return None
    
    # Check if key is valid
    if not api_key_obj.is_valid:
        return None
    
    # Check if organization is active
    if not api_key_obj.organization.is_active:
        return None
    
    return api_key_obj


async def get_api_key_org(
    api_key: str = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db)
) -> Optional[Organization]:
    """
    FastAPI dependency to get the organization from an API key.
    
    Usage:
        @router.get("/endpoint")
        async def endpoint(org: Organization = Depends(get_api_key_org)):
            ...
    
    Returns:
        Organization if valid API key, None if no key provided
        
    Raises:
        HTTPException(401) if invalid key format or key not found
    """
    if not api_key:
        return None
    
    if not api_key.startswith("lyo_sk_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Keys must start with 'lyo_sk_'"
        )
    
    api_key_obj = await validate_api_key(api_key, db)
    
    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key"
        )
    
    # Update last_used timestamp (fire-and-forget)
    try:
        await db.execute(
            update(APIKey)
            .where(APIKey.id == api_key_obj.id)
            .values(
                last_used_at=datetime.utcnow(),
                total_requests=APIKey.total_requests + 1
            )
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to update API key last_used: {e}")
        await db.rollback()
    
    logger.info(f"API key authenticated for org: {api_key_obj.organization.name}")
    return api_key_obj.organization


async def require_api_key(
    api_key: str = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db)
) -> Organization:
    """
    FastAPI dependency that REQUIRES a valid API key.
    
    Same as get_api_key_org but raises 401 if no key provided.
    
    Raises:
        HTTPException(401) if no key, invalid key, or inactive org
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header."
        )
    
    org = await get_api_key_org(api_key, db)
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid API key required"
        )
    
    return org


async def create_api_key(
    db: AsyncSession,
    organization_id: int,
    name: str,
    description: Optional[str] = None,
    expires_at: Optional[datetime] = None
) -> tuple[str, APIKey]:
    """
    Create a new API key for an organization.
    
    Args:
        db: Database session
        organization_id: ID of the organization
        name: Human-readable name for the key
        description: Optional description
        expires_at: Optional expiration datetime
        
    Returns:
        Tuple of (plaintext_key, api_key_object)
        
    NOTE: The plaintext key is returned ONLY ONCE and cannot be retrieved later.
    """
    full_key, key_prefix, key_hash = generate_api_key()
    
    api_key = APIKey(
        organization_id=organization_id,
        key_prefix=key_prefix,
        key_hash=key_hash,
        name=name,
        description=description,
        expires_at=expires_at
    )
    
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    
    logger.info(f"Created API key '{name}' for organization {organization_id}")
    
    return full_key, api_key
