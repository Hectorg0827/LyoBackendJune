"""
Authentication routes for user registration, login, and profile management.
Provides FastAPI endpoints for the authentication module.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.schemas import UserCreate, UserLogin, UserRead, Token
from lyo_app.auth.service import AuthService
from lyo_app.auth.security import verify_token
from lyo_app.core.database import get_db


router = APIRouter()
auth_service = AuthService()
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserRead:
    """
    Get current user from JWT token.
    
    Args:
        credentials: HTTP Bearer token credentials
        db: Database session
        
    Returns:
        Current authenticated user
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    # Verify the JWT token
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract user ID from token
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


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserRead:
    """
    Register a new user.
    
    Args:
        user_data: User registration data
        db: Database session
        
    Returns:
        Created user data
        
    Raises:
        HTTPException: If registration fails
    """
    try:
        user = await auth_service.register_user(db, user_data)
        return UserRead.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=Token)
async def login_user(
    login_data: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> Token:
    """
    Authenticate user and return JWT token.
    
    Args:
        login_data: User login credentials
        db: Database session
        
    Returns:
        JWT token response
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        return await auth_service.login(db, login_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


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
