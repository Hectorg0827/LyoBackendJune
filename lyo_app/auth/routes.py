"""
Authentication routes for user registration, login, and profile management.
Provides FastAPI endpoints for the authentication module.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.models.enhanced import User
from lyo_app.auth.schemas import UserCreate, UserLogin, UserRead, Token, LoginResponse, RefreshTokenRequest
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
    
    # First try to verify as backend JWT token
    payload = verify_token(token)
    if payload:
        # Extract user ID from JWT token
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
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
    
    # If JWT verification fails, try Firebase token
    try:
        from lyo_app.auth.firebase_auth import firebase_auth_service
        
        if firebase_auth_service.is_available():
            # Try to verify as Firebase ID token
            firebase_data = await firebase_auth_service.verify_firebase_token(token)
            firebase_uid = firebase_data.get("uid")
            email = firebase_data.get("email")
            
            # Try to find user by Firebase UID
            user = await firebase_auth_service.get_user_by_firebase_uid(db, firebase_uid)
            
            # If not found by UID, try by email
            if not user and email:
                user = await firebase_auth_service.get_user_by_email(db, email)
            
            # If user found, return it
            if user:
                return UserRead.model_validate(user)
            
            # User not found - auto-create from Firebase data
            from lyo_app.models.enhanced import User
            from lyo_app.auth.security import hash_password
            import secrets
            import logging
            logger = logging.getLogger(__name__)
            
            # Generate unique username from email or firebase_uid
            base_username = (email.split('@')[0] if email else firebase_uid)[:40]
            username = base_username
            # Make username unique by appending random suffix
            username = f"{base_username}_{secrets.token_hex(4)}"
            
            # Parse name if available
            name = firebase_data.get("name", "")
            first_name = ""
            last_name = ""
            if name:
                parts = name.split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""
            
            logger.info(f"Auto-creating user from Firebase: email={email}, uid={firebase_uid}, username={username}")
            
            new_user = User(
                email=email or f"{firebase_uid}@firebase.local",
                username=username,
                hashed_password=hash_password(secrets.token_urlsafe(32)),
                first_name=first_name,
                last_name=last_name,
                firebase_uid=firebase_uid,
                auth_provider="firebase",
                is_active=True,
                is_verified=firebase_data.get("email_verified", False)
            )
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            logger.info(f"Created user id={new_user.id} for Firebase uid={firebase_uid}")
            return UserRead.model_validate(new_user)
            
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


@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserRead:
    """
    Get user by ID.
    
    Args:
        user_id: User ID to retrieve
        db: Database session
        
    Returns:
        User data
        
    Raises:
        HTTPException: If user not found
    """
    user = await auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserRead.model_validate(user)


@router.get("/me", response_model=UserRead)
async def get_current_user_endpoint(
    current_user: Annotated[UserRead, Depends(get_current_user)]
) -> UserRead:
    """
    Get current authenticated user.
    
    Args:
        current_user: Current authenticated user from JWT token
        
    Returns:
        Current user data
    """
    return current_user


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
    
    # Delete user (cascade will handle related data)
    await db.delete(user)
    await db.commit()
    
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
        user.full_name = request.full_name
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
        # Check if user exists before auth to determine if new
        firebase_token_data = await firebase_auth_service.verify_firebase_token(firebase_data.id_token)
        existing_user = await firebase_auth_service.get_user_by_firebase_uid(
            db, firebase_token_data.get("uid", "")
        )
        if not existing_user and firebase_token_data.get("email"):
            existing_user = await firebase_auth_service.get_user_by_email(
                db, firebase_token_data.get("email")
            )
        
        is_new_user = existing_user is None
        
        # Authenticate with Firebase
        user, token = await firebase_auth_service.authenticate_with_firebase(
            db, firebase_data.id_token
        )
        
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

