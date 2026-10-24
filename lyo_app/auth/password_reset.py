"""Reset a forgotten password by email.

POST /auth/password-reset/request takes an email address. When it belongs to
an active account, a one-time link to the website's reset page is emailed to
the account's address: {WEB_APP_URL}/auth/reset-password?token=... The answer
is the same either way, so the endpoint does not reveal who has an account,
and the email goes out in the background so its timing does not either.

POST /auth/password-reset/confirm takes that token and a new password. A
token works once, for an hour. Using it ends every other open link for the
account and signs out its other sessions (their refresh tokens are revoked).

Emails are sent with Resend's HTTP API (Railway blocks outbound SMTP on most
plans). Settings:

- RESEND_API_KEY: required; without it no email is sent and an error is logged.
- EMAIL_FROM: the sender, such as "Lyo <no-reply@lyoai.app>" once lyoai.app is
  verified in Resend. Until then the default, Resend's onboarding@resend.dev,
  can only send to the email address the Resend account was made with.
- WEB_APP_URL: the website the link opens, https://www.lyoai.app by default.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from lyo_app.auth.jwt_auth import get_password_hash
from lyo_app.auth.models import RefreshToken
from lyo_app.auth.security_middleware import InputValidator, SecurityConfig
from lyo_app.core.database import Base, get_db
from lyo_app.core.rate_limiter import RedisRateLimiter
from lyo_app.models.enhanced import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])
limiter = RedisRateLimiter(max_requests=5, window_seconds=60, block_duration=300)

LINK_LIFETIME = timedelta(hours=1)
# Links one account can be sent per hour, so nobody can flood an inbox.
LINKS_PER_HOUR = 3
RESEND_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "Lyo <onboarding@resend.dev>"
DEFAULT_WEB_APP_URL = "https://www.lyoai.app"
SENT = "If an account exists for that email, we've sent it a link to reset the password. The link works for one hour."
INVALID_LINK = "This reset link is invalid, used or expired. Ask for a new one."


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResetRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


class ResetConfirm(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)
    new_password: str = Field(..., max_length=128)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _web_app_url() -> str:
    return (os.getenv("WEB_APP_URL") or DEFAULT_WEB_APP_URL).strip().rstrip("/")


def _rate_limit(request: Request, action: str) -> None:
    allowed, _ = limiter.is_allowed(limiter.get_secure_client_id(request), action)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many attempts. Please wait a few minutes and try again.")


async def _find_user(db: AsyncSession, email: str):
    """The account with this email: an exact match, else the only one ignoring case.

    Sign-up lowercases emails but some accounts were stored as typed, so two
    accounts can differ only in case; then only an exact match is trusted.
    """
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None:
        return user
    matches = (await db.execute(
        select(User).where(func.lower(User.email) == email.lower()).limit(2)
    )).scalars().all()
    return matches[0] if len(matches) == 1 else None


async def _lock_account(db: AsyncSession, user_id: int):
    """Lock the account's row until commit.

    Every request and confirmation takes it first, so for one account they
    take turns: the hourly limit cannot be outrun by simultaneous requests,
    and two links used at once cannot deadlock on each other's rows.
    """
    return (await db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()


async def send_reset_email(to: str, link: str) -> bool:
    key = os.getenv("RESEND_API_KEY", "").strip()
    if not key:
        logger.error("Password reset email not sent: RESEND_API_KEY is not set")
        return False
    text = (
        "Someone asked to reset the password of your Lyo account.\n\n"
        f"Choose a new password here (the link works once, for one hour):\n{link}\n\n"
        "If it wasn't you, ignore this email: your password stays the same."
    )
    html = (
        "<p>Someone asked to reset the password of your Lyo account.</p>"
        f'<p><a href="{link}">Choose a new password</a>. The link works once, for one hour.</p>'
        "<p>If it wasn't you, ignore this email: your password stays the same.</p>"
    )
    body = {
        "from": os.getenv("EMAIL_FROM", "").strip() or DEFAULT_FROM,
        "to": [to],
        "subject": "Reset your Lyo password",
        "text": text,
        "html": html,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(RESEND_URL, json=body, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError:
        logger.exception("Password reset email could not reach Resend")
        return False
    if response.status_code >= 300:
        # Resend says why, such as a sender domain that is not verified yet.
        logger.error("Resend refused a password reset email: %s %s", response.status_code, response.text[:300])
        return False
    logger.info("Password reset email sent")
    return True


@router.post("/password-reset/request")
async def request_password_reset(
    payload: ResetRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Email a one-time reset link to the account, if there is one."""
    _rate_limit(request, "auth:password-reset")
    user = await _find_user(db, payload.email.strip())
    if user is None or not user.is_active:
        return {"message": SENT}

    await _lock_account(db, user.id)
    now = datetime.now(timezone.utc)
    recent = await db.scalar(
        select(func.count()).select_from(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.created_at > now - timedelta(hours=1))
    )
    if (recent or 0) >= LINKS_PER_HOUR:
        logger.warning("Password reset for user %s refused: %s links in the last hour", user.id, recent)
        return {"message": SENT}

    token = secrets.token_urlsafe(32)
    db.add(PasswordReset(user_id=user.id, token_hash=_token_hash(token), expires_at=now + LINK_LIFETIME))
    await db.commit()
    logger.info("Password reset link created for user %s", user.id)
    background_tasks.add_task(send_reset_email, user.email, f"{_web_app_url()}/auth/reset-password?token={token}")
    return {"message": SENT}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    payload: ResetConfirm,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Set a new password with a reset link's token."""
    _rate_limit(request, "auth:password-reset-confirm")
    try:
        password = InputValidator.validate_password(payload.new_password)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if len(password.encode()) > SecurityConfig.MAX_PASSWORD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Password must be at most {SecurityConfig.MAX_PASSWORD_BYTES} bytes")

    token_hash = _token_hash(payload.token)
    owner = await db.scalar(select(PasswordReset.user_id).where(PasswordReset.token_hash == token_hash))
    user = await _lock_account(db, owner) if owner is not None else None
    # Read after the lock, so a link a turn before us used or ended is seen as such.
    now = datetime.now(timezone.utc)
    reset = (await db.execute(
        select(PasswordReset)
        .where(PasswordReset.token_hash == token_hash,
               PasswordReset.used_at.is_(None), PasswordReset.expires_at > now)
    )).scalar_one_or_none()
    if reset is None or user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)

    user.hashed_password = get_password_hash(password)
    await db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .values(used_at=now)
    )
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.is_revoked.is_(False))
        .values(is_revoked=True)
    )
    await db.commit()
    logger.info("Password reset completed for user %s", user.id)
    return {"message": "Your password has been changed. You can log in with it now."}
