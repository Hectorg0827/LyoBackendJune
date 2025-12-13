"""Pydantic schemas for Stack-related payloads used across the app."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from lyo_app.stack.models import StackItemType


class StackCardPayload(BaseModel):
    """Lightweight card payload for suggesting a stack action in responses."""

    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: StackItemType = Field(..., description="Type of stack item")
    ref_id: str = Field(..., description="Reference id for the suggested item")
    action_label: str = Field(..., min_length=1, max_length=64)
    context_data: Optional[Dict[str, Any]] = None


class StackItemCreate(BaseModel):
    """Schema for creating a new stack item."""
    
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: StackItemType = Field(..., description="Type of stack item")
    ref_id: Optional[str] = Field(None, description="Reference id for source item")
    source_type: Optional[str] = Field(None, description="Source type (lesson, post, etc)")
    source_id: Optional[int] = Field(None, description="Source entity ID")
    context_data: Optional[Dict[str, Any]] = None

