"""Authentication API endpoints with JWT and refresh token support."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from lyo_app.core.database import get_db
from lyo_app.core.problems import (
    ValidationProblem, AuthenticationProblem, ConflictProblem, RateLimitProblem
)
from lyo_app.models.enhanced import User, GamificationProfile
from lyo_app.schemas import (
    LoginRequest, LoginResponse, RefreshRequest, RefreshResponse,
    RegisterRequest, UserProfile
)
from lyo_app.auth.jwt_auth import (
    authenticate_user, create_access_token, create_refresh_token,
    verify_token, get_password_hash, rate_limiter, check_account_locked
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def get_client_ip(request: Request) -> str:
    """Extract client IP for rate limiting."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticate user and return JWT access and refresh tokens.
    
    Returns:
        LoginResponse with access_token, refresh_token, and user profile
        
    Raises:
        AuthenticationProblem: Invalid credentials or account locked
        RateLimitProblem: Too many login attempts
    """
    client_ip = get_client_ip(request)
    
    # Check rate limit (5 attempts per 15 minutes per IP)
    if not rate_limiter.check_rate_limit(client_ip, max_attempts=5, window_minutes=15):
        raise RateLimitProblem(retry_after=900)  # 15 minutes
    
    # Authenticate user
    user = authenticate_user(db, login_data.email, login_data.password)
    
    if not user:
        raise AuthenticationProblem("Invalid email or password")
    
    if check_account_locked(user):
        raise AuthenticationProblem("Account temporarily locked due to failed login attempts")
    
    # Generate tokens
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    
    # Reset rate limit on successful login
    rate_limiter.reset_attempts(client_ip)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=1800,  # 30 minutes
        tenant_id=str(user.id),  # User's tenant for SaaS isolation
        user=UserProfile.from_orm(user)
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    refresh_data: RefreshRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    
    Returns:
        RefreshResponse with new access_token
        
    Raises:
        AuthenticationProblem: Invalid or expired refresh token
    """
    # Verify refresh token
    token_data = verify_token(refresh_data.refresh_token, "refresh")
    
    # Check if user still exists and is active
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user or not user.is_active:
        raise AuthenticationProblem("User not found or inactive")
    
    # Generate new access token
    access_token = create_access_token(str(user.id))
    
    return RefreshResponse(
        access_token=access_token,
        expires_in=1800  # 30 minutes
    )


@router.post("/register", response_model=LoginResponse, status_code=201)
async def register(
    request: Request,
    register_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new user account.
    
    Returns:
        LoginResponse with access_token, refresh_token, and user profile
        
    Raises:
        ConflictProblem: Email or username already exists
        ValidationProblem: Invalid registration data
        RateLimitProblem: Too many registration attempts
    """
    client_ip = get_client_ip(request)
    
    # Check rate limit (3 registrations per hour per IP)
    if not rate_limiter.check_rate_limit(client_ip, max_attempts=3, window_minutes=60):
        raise RateLimitProblem(retry_after=3600)  # 1 hour
    
    # Validate password strength
    if len(register_data.password) < 8:
        raise ValidationProblem("Password must be at least 8 characters long")
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == register_data.email).first()
    if existing_email:
        raise ConflictProblem("Email address is already registered")
    
    # Check if username already exists (if provided)
    if register_data.username:
        existing_username = db.query(User).filter(User.username == register_data.username).first()
        if existing_username:
            raise ConflictProblem("Username is already taken")
    
    try:
        # Create new user
        user = User(
            email=register_data.email,
            username=register_data.username,
            password_hash=get_password_hash(register_data.password),
            full_name=register_data.full_name,
            is_active=True,
            is_verified=False  # Require email verification
        )
        
        db.add(user)
        db.flush()  # Get user.id before creating gamification profile
        
        # Create gamification profile
        gamification_profile = GamificationProfile(
            user_id=user.id,
            total_xp=0,
            level=1,
            current_streak_days=0,
            longest_streak_days=0
        )
        
        db.add(gamification_profile)
        db.commit()
        
        # Generate tokens for immediate login
        access_token = create_access_token(str(user.id))
        refresh_token = create_refresh_token(str(user.id))
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=1800,
            tenant_id=str(user.id),  # User's tenant for SaaS isolation
            user=UserProfile.from_orm(user)
        )
        
    except IntegrityError as e:
        db.rollback()
        # Handle race conditions for email/username uniqueness
        if "email" in str(e):
            raise ConflictProblem("Email address is already registered")
        elif "username" in str(e):
            raise ConflictProblem("Username is already taken")
        else:
            raise ValidationProblem("Registration failed due to data conflict")


@router.post("/logout", status_code=204)
async def logout():
    """
    Logout user (client should discard tokens).
    
    Note: Since we're using stateless JWT tokens, logout is handled
    client-side by discarding the tokens. For enhanced security,
    consider implementing a token blacklist.
    """
    # In a production system, you might want to:
    # 1. Add tokens to a blacklist
    # 2. Revoke refresh tokens in database
    # 3. Log the logout event
    
    return None


@router.post("/forgot-password", status_code=204)
async def forgot_password(
    request: Request,
    email: str,
    db: Session = Depends(get_db)
):
    """
    Initiate password reset process.
    
    Sends password reset email if user exists.
    Always returns 204 to prevent email enumeration.
    """
    client_ip = get_client_ip(request)
    
    # Rate limit password reset requests
    if not rate_limiter.check_rate_limit(f"pwd_reset:{client_ip}", max_attempts=3, window_minutes=60):
        raise RateLimitProblem(retry_after=3600)
    
    user = db.query(User).filter(User.email == email).first()
    
    if user and user.is_active:
        # TODO: Implement password reset email
        # 1. Generate secure reset token
        # 2. Store token with expiration
        # 3. Send email with reset link
        pass
    
    # Always return success to prevent email enumeration
    return None


@router.post("/verify-email", status_code=204)
async def verify_email(
    verification_token: str,
    db: Session = Depends(get_db)
):
    """
    Verify user email address with verification token.
    
    Args:
        verification_token: Email verification token
    """
    # TODO: Implement email verification
    # 1. Verify token signature and expiration
    # 2. Update user.is_verified = True
    # 3. Update user.email_verified_at
    
    return None
