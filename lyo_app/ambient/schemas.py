"""
Pydantic schemas for Ambient Presence API
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class PresenceUpdateRequest(BaseModel):
    """Request to update user's presence state"""
    page: str = Field(..., description="Current page/section")
    topic: Optional[str] = Field(None, description="Current topic")
    content_id: Optional[str] = Field(None, description="Current content ID")
    time_on_page: float = Field(0.0, description="Seconds on current page")
    scroll_count: int = Field(0, description="Number of scrolls")
    mouse_hesitations: int = Field(0, description="Mouse hover without click count")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class InlineHelpRequest(BaseModel):
    """Request to check if inline help should be shown"""
    user_behavior: Dict[str, Any] = Field(..., description="User behavior signals")
    current_context: Dict[str, Any] = Field(..., description="Current page context")


class InlineHelpResponse(BaseModel):
    """Response indicating if inline help should be shown"""
    should_show: bool
    help_message: Optional[str] = None
    help_type: Optional[str] = None


class LogInlineHelpRequest(BaseModel):
    """Request to log inline help shown"""
    help_type: str
    help_text: str
    page: str
    topic: Optional[str] = None
    content_id: Optional[str] = None


class RecordHelpResponseRequest(BaseModel):
    """Request to record user's response to help"""
    help_log_id: int
    user_response: str = Field(..., description="'accepted', 'dismissed', or 'ignored'")


class QuickActionResponse(BaseModel):
    """Quick action item for context palette"""
    id: str
    label: str
    action_type: str
    icon: str
    context: Dict[str, Any] = {}


class QuickActionsRequest(BaseModel):
    """Request for contextual quick actions"""
    current_page: str
    current_content: Dict[str, Any] = {}


class QuickActionsResponse(BaseModel):
    """Response with list of quick actions"""
    actions: List[QuickActionResponse]
