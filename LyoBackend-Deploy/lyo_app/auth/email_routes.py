"""
Email verification and password reset routes for LyoApp.
Provides endpoints for user email verification and password reset flows.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from lyo_app.core.database import get_async_session
from lyo_app.auth.models import User
from lyo_app.auth.email_service import EmailService
from lyo_app.auth.security import hash_password, verify_password
from lyo_app.auth.schemas import (
    EmailVerificationRequest,
    EmailVerificationResponse,
    PasswordResetRequest,
    PasswordResetConfirm,
    MessageResponse
)
from lyo_app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["Email Verification"])
email_service = EmailService()


@router.post("/verify-email/send", response_model=MessageResponse)
async def send_verification_email(
    request: EmailVerificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_session)
):
    """Send email verification token to user."""
    try:
        # Find user by email
        stmt = select(User).where(User.email == request.email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already verified"
            )
        
        # Create verification token
        token = await email_service.create_verification_token(db, user.id)
        
        # Send email in background
        background_tasks.add_task(
            send_verification_email_background,
            user.email,
            user.full_name or user.username,
            token
        )
        
        logger.info(f"Verification email sent to user {user.id}")
        
        return MessageResponse(
            message="Verification email sent. Please check your inbox."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email"
        )


@router.post("/verify-email/confirm", response_model=EmailVerificationResponse)
async def verify_email_token(
    token: str,
    db: AsyncSession = Depends(get_async_session)
):
    """Verify email token and activate user account."""
    try:
        user = await email_service.verify_email_token(db, token)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )
        
        logger.info(f"Email verified for user {user.id}")
        
        return EmailVerificationResponse(
            message="Email verified successfully",
            user_id=user.id,
            is_verified=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email verification failed"
        )


@router.post("/password-reset/request", response_model=MessageResponse)
async def request_password_reset(
    request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_session)
):
    """Request password reset token."""
    try:
        # Find user by email
        stmt = select(User).where(User.email == request.email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            # Don't reveal if email exists for security
            return MessageResponse(
                message="If the email exists, a password reset link has been sent."
            )
        
        # Create password reset token
        token = await email_service.create_password_reset_token(db, user.id)
        
        # Send email in background
        background_tasks.add_task(
            send_password_reset_email_background,
            user.email,
            user.full_name or user.username,
            token
        )
        
        logger.info(f"Password reset requested for user {user.id}")
        
        return MessageResponse(
            message="If the email exists, a password reset link has been sent."
        )
        
    except Exception as e:
        logger.error(f"Password reset request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset request failed"
        )


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_async_session)
):
    """Confirm password reset with token and new password."""
    try:
        # Verify reset token
        user = await email_service.verify_reset_token(db, reset_data.token)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        # Update user password
        user.hashed_password = hash_password(reset_data.new_password)
        user.updated_at = datetime.utcnow()
        
        # Mark token as used
        await email_service.use_reset_token(db, reset_data.token)
        
        await db.commit()
        
        logger.info(f"Password reset completed for user {user.id}")
        
        return MessageResponse(
            message="Password reset successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset confirmation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )


@router.get("/verify-email/status/{user_id}")
async def get_verification_status(
    user_id: int,
    db: AsyncSession = Depends(get_async_session)
):
    """Get user email verification status."""
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {
            "user_id": user.id,
            "email": user.email,
            "is_verified": user.is_verified,
            "created_at": user.created_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get verification status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get verification status"
        )


# Background task functions
async def send_verification_email_background(
    email: str, 
    name: str, 
    token: str
):
    """Send verification email in background."""
    try:
        # In production, use proper email service (SendGrid, SES, etc.)
        verification_url = f"http://localhost:8000/api/v1/auth/verify-email/confirm?token={token}"
        
        # For now, log the verification URL (in production, send actual email)
        logger.info(f"Verification email for {email}: {verification_url}")
        
        # TODO: Replace with actual email sending
        # await send_email(
        #     to=email,
        #     subject="Verify your LyoApp account",
        #     template="verification_email.html",
        #     context={"name": name, "verification_url": verification_url}
        # )
        
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {e}")


async def send_password_reset_email_background(
    email: str, 
    name: str, 
    token: str
):
    """Send password reset email in background."""
    try:
        # In production, use proper email service
        reset_url = f"http://localhost:8000/reset-password?token={token}"
        
        # For now, log the reset URL (in production, send actual email)
        logger.info(f"Password reset email for {email}: {reset_url}")
        
        # TODO: Replace with actual email sending
        # await send_email(
        #     to=email,
        #     subject="Reset your LyoApp password",
        #     template="password_reset_email.html",
        #     context={"name": name, "reset_url": reset_url}
        # )
        
    except Exception as e:
        logger.error(f"Failed to send reset email to {email}: {e}")
