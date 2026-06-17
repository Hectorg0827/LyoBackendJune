"""Instructor-only access gate for teacher-in-the-loop routes.

Grants access when the user is a superuser OR carries the INSTRUCTOR role
(read via the RBAC service — the read path is safe even though the
``User.roles`` relationship is view-only). Fails closed with 403.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user
from lyo_app.core.database import get_db
from lyo_app.models.enhanced import User


async def require_instructor(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Allow superusers and INSTRUCTOR-role users through; 403 otherwise."""
    if getattr(current_user, "is_superuser", False):
        return current_user
    try:
        from lyo_app.auth.rbac_service import RBACService
        from lyo_app.auth.rbac import RoleType
        is_instructor = await RBACService(db).user_has_role(
            current_user.id, RoleType.INSTRUCTOR.value
        )
    except Exception:  # noqa: BLE001 — RBAC unavailable -> deny, don't 500
        is_instructor = False
    if not is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor role required",
        )
    return current_user
