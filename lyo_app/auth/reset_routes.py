"""Password recovery: a password-bound, short-lived single-use reset token.

The legacy email_routes.py is not mounted and its referenced sender does not
exist. This route does not claim recovery has happened until a real mail
provider is configured and independently tested.
"""
import asyncio
import base64
from datetime import datetime, timezone
from email.message import EmailMessage
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import ssl
import time

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.models import User, RefreshToken
from lyo_app.auth.security import hash_password
from lyo_app.core.redis_client import redis_client
from lyo_app.core.database import get_async_session

router = APIRouter(prefix="/api/v1/auth/password-reset", tags=["password recovery"])
RESET_TTL_SECONDS = 3600
DEFAULT_RESET_URL = "https://www.lyoai.app/auth/reset-password"

_RATE_LIMIT_LUA = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1])) end
return n
"""

async def _enforce_reset_limit(peer: str, *, limit: int = 5) -> None:
    # A reset rate limit must be shared across every worker; never fall back locally.
    client = redis_client.client
    if client is None:
        raise HTTPException(503, 'Password recovery is temporarily unavailable')
    try:
        count = await client.eval(_RATE_LIMIT_LUA, 1, 'pwd-reset:' + peer, 3600)
        if type(count) is not int:
            raise ValueError('Redis did not return a counter')
    except Exception:
        raise HTTPException(503, 'Password recovery is temporarily unavailable')
    if count > limit:
        raise HTTPException(429, 'Too many reset attempts. Try again later.')



class ResetRequest(BaseModel):
    email: EmailStr


class ResetConfirm(BaseModel):
    token: str = Field(min_length=40, max_length=1024)
    new_password: str = Field(min_length=8, max_length=72)
    confirm_password: str = Field(min_length=8, max_length=72)

    @model_validator(mode="after")
    def matches(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


def _key() -> bytes:
    raw = os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY") or ""
    if len(raw) < 32:
        raise RuntimeError("Password recovery requires a production-grade secret key")
    return raw.encode("utf-8")


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _signature(body: str, password_hash: str) -> str:
    key = hmac.new(_key(), b"lyo-pwd-reset-v1:" + password_hash.encode(), hashlib.sha256).digest()
    return _encode(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())


def create_reset_token(user: User, now: int | None = None) -> str:
    timestamp = int(time.time()) if now is None else int(now)
    payload = {"uid": user.id, "iat": timestamp, "nonce": secrets.token_urlsafe(16)}
    body = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return body + "." + _signature(body, user.hashed_password)


def verify_reset_token(user: User, token: str, now: int | None = None) -> bool:
    try:
        body, signature = token.split(".", 1)
        if len(body) > 600 or len(signature) > 100:
            return False
        payload = json.loads(_decode(body))
        current = int(time.time()) if now is None else int(now)
        age = current - int(payload["iat"])
        return (
            type(payload["uid"]) is int
            and payload["uid"] == user.id
            and 0 <= age <= RESET_TTL_SECONDS
            and hmac.compare_digest(_signature(body, user.hashed_password), signature)
        )
    except (KeyError, ValueError, TypeError, UnicodeError, RuntimeError):
        return False


def _smtp_send(to_email: str, url: str) -> None:
    host = os.environ["SMTP_SERVER"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    sender = os.environ["SMTP_FROM_EMAIL"]
    message = EmailMessage()
    message["Subject"] = "Reset your LYO password"
    message["From"] = sender
    message["To"] = to_email
    message.set_content(
        "Use this link to set a new LYO password within one hour:\n"
        + url + "\nIf you did not request this, you can ignore the email.\n"
    )
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as client:
            client.login(username, password)
            client.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as client:
            client.starttls(context=context)
            client.login(username, password)
            client.send_message(message)


def _provider_configured() -> bool:
    if os.getenv("RESEND_API_KEY") and os.getenv("SMTP_FROM_EMAIL"):
        return True
    return all(os.getenv(v) for v in ("SMTP_SERVER", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"))


async def _send_reset_email(to_email: str, token: str) -> None:
    from urllib.parse import quote
    from urllib.parse import urlsplit
    base_url = os.getenv("LYO_PASSWORD_RESET_URL", DEFAULT_RESET_URL)
    parts = urlsplit(base_url)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path != "/auth/reset-password"):
        raise RuntimeError("Password recovery public URL must be an HTTPS reset-password page")
    url = base_url + "?token=" + quote(token, safe="")
    if os.getenv("RESEND_API_KEY"):
        async with httpx.AsyncClient(timeout=15.0) as client:
            reply = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"]},
                json={
                    "from": os.environ["SMTP_FROM_EMAIL"],
                    "to": [to_email],
                    "subject": "Reset your LYO password",
                    "text": "Set a new LYO password within one hour: " + url,
                },
            )
            reply.raise_for_status()
    else:
        await asyncio.to_thread(_smtp_send, to_email, url)


@router.post("/request", status_code=status.HTTP_200_OK)
async def request_reset(payload: ResetRequest, request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_async_session)):
    # Disabled setups must fail for every request (including unknown emails),
    # not leak which account exists.
    if not _provider_configured():
        raise HTTPException(503, "Password recovery is temporarily unavailable")
    # Railway's ingress peer can be shared by many learners. Use a generous
    # ingress-wide safety ceiling plus a strict per-target email limit. Never
    # trust user-supplied X-Forwarded-For/X-Real-IP for bypassable counters.
    peer = request.client.host if request.client else "unknown"
    await _enforce_reset_limit("ingress:" + peer, limit=10000)
    normalized_email = str(payload.email).strip().lower()
    address_hash = hmac.new(_key(), normalized_email.encode("utf-8"), hashlib.sha256).hexdigest()
    await _enforce_reset_limit("account:" + address_hash)
    # Deliberately indistinguishable response for known and unknown addresses.
    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()
    if user and user.is_active:
        token = create_reset_token(user)
        # Do not log the token, password, email address or tokenized reset URL.
        background_tasks.add_task(_send_reset_email, user.email, token)
    return {"message": "If the account exists, a password reset email will be sent."}


@router.post("/confirm", status_code=status.HTTP_200_OK)
async def confirm_reset(payload: ResetConfirm, db: AsyncSession = Depends(get_async_session)):
    try:
        body, _ = payload.token.split(".", 1)
        token_data = json.loads(_decode(body))
        user_id = token_data.get("uid")
        if type(user_id) is not int:
            raise ValueError("Invalid user identifier")
    except (ValueError, TypeError, UnicodeError, KeyError):
        raise HTTPException(400, "Invalid or expired reset link")
    row = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = row.scalar_one_or_none()
    if not user or not user.is_active or not verify_reset_token(user, payload.token):
        raise HTTPException(400, "Invalid or expired reset link")
    user.hashed_password = hash_password(payload.new_password)
    user.auth_version = (user.auth_version or 0) + 1
    user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    # In the same user-row-locked transaction, disable every prior refresh token.
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.is_revoked.is_(False))
        .values(is_revoked=True)
    )
    await db.commit()
    return {"message": "Password updated. Sign in with your new password."}
