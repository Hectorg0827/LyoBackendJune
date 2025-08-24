"""
Pydantic schemas for authentication endpoints.
Defines request/response models for user registration, login, and profile management.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserBase(BaseModel):
    """Base user schema with common fields."""
    
    email: EmailStr = Field(..., description="User's email address")
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    first_name: Optional[str] = Field(None, max_length=100, description="User's first name")
    last_name: Optional[str] = Field(None, max_length=100, description="User's last name")
    bio: Optional[str] = Field(None, max_length=1000, description="User's bio")
    avatar_url: Optional[str] = Field(None, description="URL to user's avatar image")


class UserCreate(UserBase):
    """Schema for user registration."""
    
    password: str = Field(
        ..., 
        min_length=8, 
        max_length=100,
        description="Password (minimum 8 characters)"
    )
    confirm_password: str = Field(..., description="Password confirmation")

    def validate_passwords_match(self) -> 'UserCreate':
        """Validate that password and confirm_password match."""
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class UserLogin(BaseModel):
    """Schema for user login."""
    
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")


class UserRead(UserBase):
    """Schema for reading user data (response)."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="User's unique ID")
    is_active: bool = Field(..., description="Whether the user account is active")
    is_verified: bool = Field(..., description="Whether the user's email is verified")
    created_at: datetime = Field(..., description="User registration timestamp")
    updated_at: datetime = Field(..., description="Last profile update timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")


class UserUpdate(BaseModel):
    """Schema for updating user profile."""
    
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
    avatar_url: Optional[str] = None


class Token(BaseModel):
    """Schema for JWT token response."""
    
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")


class TokenData(BaseModel):
    """Schema for token payload data."""
    
    user_id: Optional[int] = None
    username: Optional[str] = None


class EmailVerificationRequest(BaseModel):
    """Schema for email verification request."""
    
    email: EmailStr = Field(..., description="Email address to verify")


class EmailVerificationResponse(BaseModel):
    """Schema for email verification response."""
    
    message: str = Field(..., description="Verification result message")
    user_id: int = Field(..., description="User ID")
    is_verified: bool = Field(..., description="Email verification status")


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""
    
    email: EmailStr = Field(..., description="Email address for password reset")


class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation."""
    
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(
        ..., 
        min_length=8, 
        max_length=100,
        description="New password (minimum 8 characters)"
    )
    confirm_password: str = Field(..., description="Password confirmation")

    def validate_passwords_match(self) -> 'PasswordResetConfirm':
        """Validate that password and confirm_password match."""
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class MessageResponse(BaseModel):
    """Schema for simple message responses."""
    
    message: str = Field(..., description="Response message")
