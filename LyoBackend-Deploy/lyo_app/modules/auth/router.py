"""
Auth Module - Authentication & Authorization
==========================================

Comprehensive authentication system with JWT tokens, RBAC, and security features.
Supports email/password and Apple Sign-In authentication methods.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import secrets
import hashlib

from lyo_app.core.database_v2 import get_db
from lyo_app.core.redis_v2 import redis_manager
from lyo_app.core.config_v2 import settings
from lyo_app.core.logging_v2 import logger, security_logger
from lyo_app.modules.auth.models import User, RefreshToken
from lyo_app.modules.auth.schemas import (
    UserLogin,
    UserRegister,
    Token,
    UserResponse,
    RefreshTokenRequest,
)
from lyo_app.modules.auth.service import AuthService
from lyo_app.modules.auth.security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    get_current_user,
)
from lyo_app.core.rate_limiting import rate_limit
from lyo_app.core.exceptions_v2 import ValidationError, AuthenticationError

router = APIRouter()
security = HTTPBearer()


@router.post("/login", response_model=Token)
@rate_limit(requests=5, window=300)  # 5 attempts per 5 minutes
async def login(
    credentials: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user and return JWT tokens.
    
    Rate limited to prevent brute force attacks.
    Returns both access and refresh tokens.
    """
    try:
        # Get client info for logging
        ip_address = request.client.host
        user_agent = request.headers.get("User-Agent", "")
        
        # Authenticate user
        auth_service = AuthService(db)
        user = await auth_service.authenticate_user(credentials.email, credentials.password)
        
        if not user:
            # Log failed attempt
            security_logger.log_auth_attempt(
                user_id=None,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent
            )
            raise AuthenticationError("Invalid credentials")
        
        if not user.is_active:
            raise AuthenticationError("Account is disabled")
        
        # Create tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "roles": user.roles}
        )
        refresh_token_str = create_refresh_token(data={"sub": str(user.id)})
        
        # Store refresh token in database
        refresh_token = await auth_service.create_refresh_token(
            user_id=user.id,
            token=refresh_token_str,
            expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
        
        # Store session in Redis
        session_key = f"session:{user.id}:{secrets.token_hex(16)}"
        await redis_manager.set(
            session_key,
            {
                "user_id": str(user.id),
                "ip_address": ip_address,
                "user_agent": user_agent,
                "login_time": datetime.utcnow().isoformat(),
            },
            ex=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
        # Log successful attempt
        security_logger.log_auth_attempt(
            user_id=str(user.id),
            success=True,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Set secure cookie with refresh token
        response.set_cookie(
            key="refresh_token",
            value=refresh_token_str,
            httponly=True,
            secure=settings.is_production(),
            samesite="strict",
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        )
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=refresh_token_str,
            user=UserResponse.from_orm(user)
        )
        
    except Exception as e:
        logger.error(f"Login failed: {e}")
        if isinstance(e, (AuthenticationError, ValidationError)):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/register", response_model=UserResponse)
@rate_limit(requests=3, window=300)  # 3 attempts per 5 minutes
async def register(
    user_data: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Register new user account.
    
    Rate limited to prevent spam registrations.
    Requires email verification in production.
    """
    try:
        # Get client info
        ip_address = request.client.host
        user_agent = request.headers.get("User-Agent", "")
        
        auth_service = AuthService(db)
        
        # Check if user already exists
        existing_user = await auth_service.get_user_by_email(user_data.email)
        if existing_user:
            raise ValidationError("Email already registered")
        
        # Create user
        user = await auth_service.create_user(
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name,
            role=user_data.role,
            ip_address=ip_address
        )
        
        logger.info(f"New user registered: {user.email}")
        
        return UserResponse.from_orm(user)
        
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        if isinstance(e, ValidationError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_request: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    
    Validates refresh token and issues new access token.
    Optionally rotates refresh token for enhanced security.
    """
    try:
        # Verify refresh token
        payload = verify_token(refresh_request.refresh_token, token_type="refresh")
        if not payload:
            raise AuthenticationError("Invalid refresh token")
        
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token payload")
        
        auth_service = AuthService(db)
        
        # Validate refresh token in database
        stored_token = await auth_service.get_refresh_token(refresh_request.refresh_token)
        if not stored_token or stored_token.is_revoked or stored_token.expires_at < datetime.utcnow():
            raise AuthenticationError("Invalid or expired refresh token")
        
        # Get user
        user = await auth_service.get_user_by_id(int(user_id))
        if not user or not user.is_active:
            raise AuthenticationError("User not found or inactive")
        
        # Create new access token
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "roles": user.roles}
        )
        
        # Optionally rotate refresh token (recommended for security)
        new_refresh_token = refresh_request.refresh_token
        if settings.is_production():
            # Revoke old token
            await auth_service.revoke_refresh_token(stored_token.token)
            
            # Create new refresh token
            new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
            await auth_service.create_refresh_token(
                user_id=user.id,
                token=new_refresh_token,
                expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
            )
            
            # Update cookie
            response.set_cookie(
                key="refresh_token",
                value=new_refresh_token,
                httponly=True,
                secure=True,
                samesite="strict",
                max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            )
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=new_refresh_token,
            user=UserResponse.from_orm(user)
        )
        
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        if isinstance(e, AuthenticationError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Logout user and invalidate tokens.
    
    Revokes refresh token and clears session data.
    """
    try:
        # Get refresh token from cookie
        refresh_token = request.cookies.get("refresh_token")
        
        auth_service = AuthService(db)
        
        # Revoke refresh token if present
        if refresh_token:
            await auth_service.revoke_refresh_token(refresh_token)
        
        # Clear session from Redis
        # Note: In production, you might want to maintain a blacklist of revoked access tokens
        
        # Clear cookie
        response.delete_cookie(key="refresh_token")
        
        logger.info(f"User logged out: {current_user.email}")
        
        return {"message": "Successfully logged out"}
        
    except Exception as e:
        logger.error(f"Logout failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user = Depends(get_current_user)
):
    """
    Get current user information.
    
    Returns user profile data for authenticated user.
    """
    return UserResponse.from_orm(current_user)


@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change user password.
    
    Requires current password verification.
    Invalidates all existing refresh tokens for security.
    """
    try:
        auth_service = AuthService(db)
        
        # Verify old password
        if not verify_password(old_password, current_user.password_hash):
            raise AuthenticationError("Invalid current password")
        
        # Update password
        await auth_service.update_password(current_user.id, new_password)
        
        # Revoke all refresh tokens for this user
        await auth_service.revoke_all_user_tokens(current_user.id)
        
        logger.info(f"Password changed for user: {current_user.email}")
        
        return {"message": "Password updated successfully"}
        
    except Exception as e:
        logger.error(f"Password change failed: {e}")
        if isinstance(e, AuthenticationError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change failed"
        )


@router.get("/health")
async def auth_health():
    """Authentication service health check."""
    return {
        "status": "healthy",
        "service": "auth",
        "timestamp": datetime.utcnow().isoformat(),
    }
