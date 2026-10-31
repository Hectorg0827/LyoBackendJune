"""Authenticate Voice Lab tickets against the *existing staging* LYO identity service.

The Voice Lab has a separate, ledger-only database: it must never attempt to
load users from that database or copy the canonical user schema into it.
This module is used only by the isolated Voice Lab FastAPI application.
"""
from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from lyo_app.auth.schemas import UserRead

# Fixed trusted staging service; no user-controlled URL or production fallback.
_STAGING_WHOAMI_URL = "https://lyojourneystagingbackend-staging.up.railway.app/auth/me"
_bearer = HTTPBearer(auto_error=False)


async def get_staging_trial_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> UserRead:
    """Fail closed if the existing staging API cannot validate the learner."""
    if credentials is None or not credentials.credentials or len(credentials.credentials) > 8192:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staging sign-in required",
        )
    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=False) as client:
            response = await client.get(
                _STAGING_WHOAMI_URL,
                headers={"Authorization": f"Bearer {credentials.credentials}"},
            )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Staging identity verification unavailable",
        )

    # Never accept a redirect, another environment's identity, or a partial
    # response. Do not log the token or the learner's profile.
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staging sign-in not verified",
        )
    try:
        user = UserRead.model_validate(response.json())
        if not isinstance(user.id, int) or isinstance(user.id, bool) or user.id <= 0 or not user.is_active:
            raise ValueError("Staging user must be an active integer-ID account")
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staging sign-in not verified",
        )
    return user
