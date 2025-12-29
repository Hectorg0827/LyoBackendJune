"""
Email verification system for LyoApp.
Handles email verification tokens and confirmation flow.
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, ForeignKey, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import select

from lyo_app.core.database import Base
from lyo_app.models.enhanced import User


class EmailVerificationToken(Base):
    """Email verification token model."""
    
    __tablename__ = "email_verification_tokens"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", backref="verification_tokens")


class PasswordResetToken(Base):
    """Password reset token model."""
    
    __tablename__ = "password_reset_tokens"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", backref="reset_tokens")


class EmailService:
    """Email verification and password reset service."""
    
    @staticmethod
    def generate_verification_token() -> str:
        """Generate a secure verification token."""
        return secrets.token_urlsafe(32)
    
    async def create_verification_token(self, db: AsyncSession, user_id: int) -> str:
        """Create email verification token for user."""
        token = self.generate_verification_token()
        expires_at = datetime.utcnow() + timedelta(hours=24)  # 24 hour expiry
        
        verification_token = EmailVerificationToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at
        )
        
        db.add(verification_token)
        await db.commit()
        
        return token
    
    async def verify_email_token(self, db: AsyncSession, token: str) -> Optional[User]:
        """Verify email token and activate user."""
        # Get token
        stmt = select(EmailVerificationToken).where(
            EmailVerificationToken.token == token,
            EmailVerificationToken.is_used == False,
            EmailVerificationToken.expires_at > datetime.utcnow()
        )
        result = await db.execute(stmt)
        verification_token = result.scalar_one_or_none()
        
        if not verification_token:
            return None
        
        # Get user
        stmt = select(User).where(User.id == verification_token.user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        # Mark user as verified and token as used
        user.is_verified = True
        verification_token.is_used = True
        
        await db.commit()
        return user
    
    async def create_password_reset_token(self, db: AsyncSession, user_id: int) -> str:
        """Create password reset token for user."""
        token = self.generate_verification_token()
        expires_at = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry
        
        reset_token = PasswordResetToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at
        )
        
        db.add(reset_token)
        await db.commit()
        
        return token
    
    async def verify_reset_token(self, db: AsyncSession, token: str) -> Optional[User]:
        """Verify password reset token."""
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token == token,
            PasswordResetToken.is_used == False,
            PasswordResetToken.expires_at > datetime.utcnow()
        )
        result = await db.execute(stmt)
        reset_token = result.scalar_one_or_none()
        
        if not reset_token:
            return None
        
        # Get user
        stmt = select(User).where(User.id == reset_token.user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        return user
    
    async def use_reset_token(self, db: AsyncSession, token: str) -> bool:
        """Mark reset token as used."""
        stmt = select(PasswordResetToken).where(PasswordResetToken.token == token)
        result = await db.execute(stmt)
        reset_token = result.scalar_one_or_none()
        
        if reset_token:
            reset_token.is_used = True
            await db.commit()
            return True
        
        return False
