"""
Authentication API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError
from typing import List, Optional
from pydantic import BaseModel, EmailStr

from lyo_app.core.database import get_db
from lyo_app.core.database import engine
from lyo_app.auth.models import User
from lyo_app.auth.security import create_access_token, verify_password, hash_password

router = APIRouter()


async def _ensure_user_table_if_missing(exc: Exception) -> None:
    """Best-effort lazy table creation for lightweight/test SQLite runs."""
    if not isinstance(exc, OperationalError):
        return
    if "no such table: users" not in str(exc).lower():
        return
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: User.__table__.create(bind=sync_conn, checkfirst=True))


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class LoginPayload(BaseModel):
    email: EmailStr
    password: str

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@router.post("/register")
async def register_user(
    payload: RegisterPayload,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user"""
    # Check if user exists
    try:
        existing_user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    except Exception as e:
        await _ensure_user_table_if_missing(e)
        existing_user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = hash_password(payload.password)
    derived_username = payload.email.split("@", 1)[0][:50]
    user = User(
        email=payload.email,
        username=derived_username,
        hashed_password=hashed_password,
        first_name=payload.full_name,
        is_active=True
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return {"message": "User created successfully", "user_id": user.id}


@router.post("/login")
async def login_json(
    payload: LoginPayload,
    db: AsyncSession = Depends(get_db)
):
    """JSON login endpoint compatibility alias."""
    try:
        user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    except Exception as e:
        await _ensure_user_table_if_missing(e)
        user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return access token"""
    user = (await db.execute(select(User).where(User.email == form_data.username))).scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me")
async def read_users_me(
    current_user: User = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    """Get current user information"""
    return current_user

@router.get("/users")
async def list_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all users (admin only)"""
    result = await db.execute(select(User).offset(skip).limit(limit))
    users = result.scalars().all()
    return users
