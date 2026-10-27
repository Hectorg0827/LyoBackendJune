"""
Authentication routes for user registration, login, and profile management.
Provides FastAPI endpoints for the authentication module.
"""

import logging
from typing import Annotated, Union

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.models.enhanced import User
from lyo_app.auth.schemas import UserCreate, UserLogin, UserRead, PublicUserRead, Token, LoginResponse, RefreshTokenRequest
from lyo_app.auth.service import AuthService
from lyo_app.auth.security import verify_token
from lyo_app.core.database import get_db
from lyo_app.core.rate_limiter import RedisRateLimiter

router = APIRouter()
auth_service = AuthService()
security = HTTPBearer()

# Initialize rate limiter for auth endpoints
auth_rate_limiter = RedisRateLimiter(
    max_requests=5,  # 5 attempts
    window_seconds=60,  # per minute
    block_duration=300  # 5 minute block after limit
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserRead:
    """
    Get current user from JWT token or Firebase ID token.
    
    Args:
        credentials: HTTP Bearer token credentials
        db: Database session
        
    Returns:
        Current authenticated user
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials
    
    # First try to verify as backend JWT token using jwt_auth
    try:
        from lyo_app.auth.jwt_auth import verify_token_async
        token_data = await verify_token_async(token, expected_type="access")
        user_id = token_data.user_id
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing user_id",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Get user from database
        try:
            user_id = int(user_id)
            user = await auth_service.get_user_by_id(db, user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return UserRead.model_validate(user)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID in token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except Exception as e:
        # If it's an HTTPException from above, re-raise it
        if isinstance(e, HTTPException):
            raise e
        # Otherwise log and continue to Firebase check
        import logging
        logging.getLogger(__name__).warning(f"Backend JWT verification failed: {str(e)}")
    
    # If JWT verification fails, try Firebase token
    try:
        from lyo_app.auth.firebase_auth import firebase_auth_service
        
        if firebase_auth_service.is_available():
            # Try to verify as Firebase ID token; same account rules as POST /auth/firebase
            firebase_data = await firebase_auth_service.verify_firebase_token(token)
            user, _is_new = await firebase_auth_service.find_or_create_user(db, firebase_data)
            return UserRead.model_validate(user)
            
    except ValueError as e:
        # Firebase token verification failed
        import logging
        logging.getLogger(__name__).warning(f"Firebase token verification failed (ValueError): {e}")
    except Exception as e:
        # Log but don't expose internal errors
        import logging
        import traceback
        logging.getLogger(__name__).warning(f"Firebase token check failed: {e}")
        logging.getLogger(__name__).warning(f"Traceback: {traceback.format_exc()}")
    
    # Both JWT and Firebase verification failed
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> LoginResponse:
    """
    Register a new user and return JWT token with user data.
    
    Rate limited to 5 registrations per minute per IP to prevent abuse.
    
    Args:
        user_data: User registration data
        request: FastAPI request for rate limiting
        db: Database session
        
    Returns:
        JWT token response with user data (iOS compatible)
        
    Raises:
        HTTPException: If registration fails or rate limit exceeded
    """
    # Apply rate limiting
    client_id = auth_rate_limiter.get_secure_client_id(request)
    is_allowed, rate_info = auth_rate_limiter.is_allowed(client_id, "auth:register")
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    
    try:
        user = await auth_service.register_user(db, user_data)
        
        # Generate tokens for the new user
        from lyo_app.auth.jwt_auth import create_access_token, create_refresh_token
        from lyo_app.core.settings import settings as jwt_settings
        
        access_token = create_access_token(user_id=str(user.id))
        refresh_token = create_refresh_token(user_id=str(user.id))
        
        return LoginResponse(
            user=UserRead.model_validate(user),
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=jwt_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            is_new_user=True,
            tenant_id=str(user.id)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Log the actual error for debugging
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login", response_model=LoginResponse)
async def login_user(
    login_data: UserLogin,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> LoginResponse:
    """
    Authenticate user and return JWT token with user data.
    
    Rate limited to 5 login attempts per minute per IP to prevent brute force attacks.
    
    Args:
        login_data: User login credentials
        request: FastAPI request for rate limiting
        db: Database session
        
    Returns:
        JWT token response with user data (iOS compatible)
        
    Raises:
        HTTPException: If authentication fails or rate limit exceeded
    """
    # Apply rate limiting
    client_id = auth_rate_limiter.get_secure_client_id(request)
    is_allowed, rate_info = auth_rate_limiter.is_allowed(client_id, "auth:login")
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    
    try:
        user, token = await auth_service.login_with_user(db, login_data)
        return LoginResponse(
            user=UserRead.model_validate(user),
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            token_type=token.token_type,
            expires_in=token.expires_in,
            is_new_user=False,
            tenant_id=str(user.id)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> Token:
    """
    Refresh access token.
    
    Args:
        refresh_data: Refresh token request
        db: Database session
        
    Returns:
        New JWT token response
        
    Raises:
        HTTPException: If token is invalid
    """
    try:
        return await auth_service.refresh_token(db, refresh_data.refresh_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/me", response_model=UserRead)
async def read_users_me(
    current_user: Annotated[UserRead, Depends(get_current_user)]
) -> UserRead:
    """
    Get current authenticated user.
    
    Args:
        current_user: Current user dependency
        
    Returns:
        Current user data
    """
    return current_user


@router.delete("/me")
async def delete_my_account(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Permanently delete the signed-in account.

    Deletes the user and their personal data (profile, posts, messages,
    clips, push devices, refresh tokens, uploaded files...), signs out every
    device and deletes their Firebase account. It cannot be undone.
    """
    from lyo_app.auth.account_deletion import delete_account

    try:
        await delete_account(db, current_user.id)
    except Exception:
        logger.exception("Account deletion failed for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed. Nothing was deleted; please try again."
        )
    return {"deleted": True}


@router.get("/users/{user_id}", response_model=Union[UserRead, PublicUserRead])
async def get_user(
    user_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> Union[UserRead, PublicUserRead]:
    """
    Get a user's profile by ID. Requires sign-in.

    Learners see their own full record; anyone else's comes back as the
    public profile, without email, verification state or login times.

    Raises:
        HTTPException: If user not found
    """
    user = await auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    if str(user.id) == str(current_user.id):
        return UserRead.model_validate(user)
    return PublicUserRead.model_validate(user)


# ============================================================================
# ADDITIONAL AUTH ENDPOINTS (100% Feature Complete)
# ============================================================================

from pydantic import BaseModel, Field
from lyo_app.auth.security import verify_password, hash_password


class ChangePasswordRequest(BaseModel):
    """Request model for changing password."""
    current_password: str = Field(..., min_length=8, description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")
    confirm_password: str = Field(..., min_length=8, description="Confirm new password")


class DeleteAccountRequest(BaseModel):
    """Request model for account deletion."""
    password: str = Field(..., description="Current password to confirm deletion")
    reason: str = Field(None, description="Optional reason for leaving")


class UpdateProfileRequest(BaseModel):
    """Request model for profile updates."""
    full_name: str = Field(None, max_length=100, description="Full name")
    bio: str = Field(None, max_length=500, description="User bio")
    avatar_url: str = Field(None, description="Avatar URL")


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Change the current user's password.
    
    Requires:
    - Current password for verification
    - New password (min 8 characters)
    - Password confirmation
    """
    # Verify passwords match
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match"
        )
    
    # Get user from database
    user = await auth_service.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify current password
    if not verify_password(request.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    # Update password
    user.hashed_password = hash_password(request.new_password)
    await db.commit()
    
    return {"message": "Password changed successfully"}


@router.delete("/delete-account")
async def delete_account(
    request: DeleteAccountRequest,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Delete the current user's account permanently.
    
    Requires password confirmation for security.
    This action is irreversible.
    """
    # Get user from database
    user = await auth_service.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify password
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect"
        )
    
    # Send deletion confirmation email
    try:
        from lyo_app.auth.email_sender import email_sender
        await email_sender.send_account_deletion_confirmation(
            user.email,
            user.full_name or user.username
        )
    except Exception as e:
        pass  # Don't fail deletion if email fails
    
    from lyo_app.auth.account_deletion import delete_account as delete_account_data

    await delete_account_data(db, user.id)
    return {"message": "Account deleted successfully"}


@router.put("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Update the current user's profile information.
    """
    user = await auth_service.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update fields if provided
    if request.full_name is not None:
        # User model stores first_name/last_name; assigning a non-mapped
        # full_name attribute was a silent no-op that never persisted.
        parts = request.full_name.strip().split(None, 1)
        if parts:
            user.first_name = parts[0]
            # A single-word full_name updates only the first name — don't
            # silently wipe an existing last name.
            if len(parts) > 1:
                user.last_name = parts[1]
    if request.bio is not None:
        user.bio = request.bio
    if request.avatar_url is not None:
        user.avatar_url = request.avatar_url
    
    await db.commit()
    await db.refresh(user)
    
    return UserRead.model_validate(user)


@router.post("/logout")
async def logout(
    current_user: Annotated[UserRead, Depends(get_current_user)]
):
    """
    Log out the current user.
    
    Note: Since we use JWT tokens, logout is primarily client-side.
    This endpoint can be used to invalidate refresh tokens in the future.
    """
    # In a production system, you would:
    # 1. Add the token to a blacklist
    # 2. Invalidate refresh tokens
    # For now, return success (client should delete tokens)
    return {"message": "Logged out successfully"}


# ============================================================================
# Firebase Authentication Endpoints
# ============================================================================

from lyo_app.auth.schemas import (
    FirebaseAuthRequest, 
    FirebaseAuthResponse, 
    FirebaseLinkRequest, 
    FirebaseLinkResponse
)


@router.post("/firebase", response_model=FirebaseAuthResponse)
async def authenticate_with_firebase(
    firebase_data: FirebaseAuthRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> FirebaseAuthResponse:
    """
    Authenticate user with Firebase ID token.
    
    This endpoint accepts a Firebase ID token from the client (obtained after
    Firebase authentication with Google, Apple, Email, Phone, etc.) and returns
    a backend JWT token.
    
    If the user doesn't exist, a new account is automatically created.
    If the user exists by email but isn't linked to Firebase, accounts are linked.
    
    Args:
        firebase_data: Firebase ID token
        request: FastAPI request for rate limiting
        db: Database session
        
    Returns:
        Backend JWT token and user data
        
    Raises:
        HTTPException: If Firebase token is invalid or service unavailable
    """
    from lyo_app.auth.firebase_auth import firebase_auth_service
    
    # Check if Firebase is available
    if not firebase_auth_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication is not available. Please use email/password login."
        )
    
    # Apply rate limiting
    client_id = auth_rate_limiter.get_secure_client_id(request)
    is_allowed, rate_info = auth_rate_limiter.is_allowed(client_id, "auth:firebase")
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    
    try:
        # Google, Apple (including hidden / private-relay emails), email...
        firebase_token_data = await firebase_auth_service.verify_firebase_token(firebase_data.id_token)
        user, is_new_user = await firebase_auth_service.find_or_create_user(db, firebase_token_data)
        token = await firebase_auth_service.issue_tokens(db, user)

        return FirebaseAuthResponse(
            user=UserRead.model_validate(user),
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            token_type=token.token_type,
            expires_in=token.expires_in,
            is_new_user=is_new_user,
            tenant_id=str(user.id)  # User's tenant for SaaS isolation
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Firebase authentication failed: {str(e)}"
        )


@router.post("/firebase/link", response_model=FirebaseLinkResponse)
async def link_firebase_account(
    link_data: FirebaseLinkRequest,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> FirebaseLinkResponse:
    """
    Link a Firebase account to the current user's account.
    
    This allows existing users (who signed up with email/password) to link
    their account with Firebase authentication (Google, Apple, etc.) for
    easier future logins.
    
    Args:
        link_data: Firebase ID token to link
        current_user: Currently authenticated user
        db: Database session
        
    Returns:
        Link confirmation with Firebase UID
        
    Raises:
        HTTPException: If Firebase token is invalid or already linked
    """
    from lyo_app.auth.firebase_auth import firebase_auth_service
    
    if not firebase_auth_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication is not available."
        )
    
    try:
        # Verify the Firebase token
        firebase_data = await firebase_auth_service.verify_firebase_token(link_data.id_token)
        firebase_uid = firebase_data.get("uid")
        provider = firebase_data.get("firebase", {}).get("sign_in_provider", "firebase")
        
        # Check if this Firebase UID is already linked to another account
        existing_user = await firebase_auth_service.get_user_by_firebase_uid(db, firebase_uid)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This Firebase account is already linked to another user."
            )
        
        # Get the actual user object from DB
        result = await db.execute(
            select(User).where(User.id == current_user.id)
        )
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Link the Firebase account
        await firebase_auth_service.link_firebase_to_user(db, user, firebase_uid, provider)
        
        return FirebaseLinkResponse(
            message="Firebase account linked successfully",
            firebase_uid=firebase_uid,
            auth_provider=provider
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to link Firebase account: {str(e)}"
        )


@router.get("/firebase/status")
async def get_firebase_status():
    """
    Check if Firebase authentication is available.
    
    Returns:
        Firebase availability status
    """
    from lyo_app.auth.firebase_auth import firebase_auth_service
    
    return {
        "firebase_available": firebase_auth_service.is_available(),
        "supported_providers": ["google.com", "apple.com", "password", "phone"] if firebase_auth_service.is_available() else []
    }

# Forgotten passwords: /auth/password-reset/request and /auth/password-reset/confirm.
from lyo_app.auth.password_reset import router as password_reset_router  # noqa: E402

router.include_router(password_reset_router)
