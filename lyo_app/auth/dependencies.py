"""
Authentication dependencies for FastAPI

Re-exports the proper get_current_user from routes.py which handles:
- JWT token verification
- Firebase ID token verification
- Auto-creation of users from Firebase

Also provides get_current_user_or_guest for endpoints that should
work for both authenticated and unauthenticated (API-key-only) users.
"""
import logging
from typing import Optional
from datetime import datetime

from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.routes import get_current_user
from lyo_app.auth.schemas import UserRead

logger = logging.getLogger(__name__)

# Optional bearer – does NOT raise 403 when header is missing
_optional_bearer = HTTPBearer(auto_error=False)


class _GuestUser(UserRead):
    """Lightweight guest placeholder so downstream code sees a User-like object."""

    model_config = {"arbitrary_types_allowed": True}


_GUEST = _GuestUser(
    id=0,
    email="guest@lyo.app",
    username="guest",
    first_name="Guest",
    last_name="",
    is_active=True,
    is_verified=False,
    created_at=datetime.utcnow(),
)


async def get_current_user_or_guest(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    """
    Returns the authenticated user when a valid Bearer token is present,
    otherwise falls back to a guest placeholder.
    Requires a valid X-API-Key header (enforced by middleware).
    """
    if credentials and credentials.credentials:
        try:
            return await get_current_user(credentials, db)
        except Exception as e:
            logger.info(f"Bearer auth failed, falling back to guest: {e}")
    
    # Validate API key is present (belt-and-suspenders; middleware should catch)
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")

    return _GUEST


# Re-export for easy imports
__all__ = ["get_current_user", "get_current_user_or_guest", "get_db"]

