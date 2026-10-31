"""Privileged maintenance dependencies using the canonical JWT/Firebase login.

The public user response intentionally has no privilege fields. Recheck the
privilege in the database so a client cannot grant itself admin status.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.models import User
from lyo_app.auth.schemas import UserRead


async def require_superuser_for_circuit_reset(
    current_user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    """Allow circuit-breaker resets only for active database superusers."""
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    is_superuser = await db.scalar(
        select(User.is_superuser).where(User.id == current_user.id)
    )
    if is_superuser is not True:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    return current_user
