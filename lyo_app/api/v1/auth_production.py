"""
Production authentication API routes.
JWT-based authentication with refresh tokens and proper error handling.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.production import (
    AuthService, get_auth_service, 
    get_current_user, require_user
)
from lyo_app.auth.models import User
from lyo_app.core.errors import AuthenticationError, ValidationError

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_id: str = None  # For SaaS multi-tenant isolation
    user: Dict[str, Any]


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1, max_length=255)
    username: str = Field(None, min_length=3, max_length=50)


class UserResponse(BaseModel):
    id: str
    email: str
    username: str = None
    full_name: str = None
    is_active: bool
    is_verified: bool
    
    model_config = {
        "from_attributes": True
    }


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Login with email and password.
    Returns JWT access token and refresh token.
    """
    try:
        result = await auth_service.login_user(request.email, request.password)
        
        logger.info(f"User logged in successfully: {request.email}")
        return LoginResponse(**result)
        
    except AuthenticationError as e:
        logger.warning(f"Login failed for {request.email}: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Login error for {request.email}: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    request: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Refresh access token using refresh token.
    """
    try:
        result = await auth_service.refresh_tokens(request.refresh_token)
        
        logger.info("Tokens refreshed successfully")
        return RefreshResponse(**result)
        
    except AuthenticationError as e:
        logger.warning(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(status_code=500, detail="Token refresh failed")


@router.post("/register", response_model=UserResponse)
async def register(
    request: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Register new user account.
    """
    try:
        user = await auth_service.create_user(
            email=request.email,
            password=request.password,
            full_name=request.full_name,
            username=request.username
        )
        
        logger.info(f"New user registered: {user.email}")
        
        return UserResponse(
            id=str(user.id),
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            is_active=user.is_active,
            is_verified=user.is_verified
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error for {request.email}: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user information.
    """
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified
    )


@router.post("/logout")
async def logout(
    current_user: User = Depends(require_user)
):
    """
    Logout user (client should discard tokens).
    """
    logger.info(f"User logged out: {current_user.email}")
    return {"message": "Successfully logged out"}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(require_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Change user password.
    """
    try:
        await auth_service.change_password(
            user=current_user,
            old_password=request.old_password,
            new_password=request.new_password
        )
        
        logger.info(f"Password changed for user: {current_user.email}")
        return {"message": "Password changed successfully"}
        
    except AuthenticationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Password change error for {current_user.email}: {e}")
        raise HTTPException(status_code=500, detail="Password change failed")
