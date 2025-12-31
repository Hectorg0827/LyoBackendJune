"""
Pydantic schemas for Proactive Intervention API
"""

from datetime import datetime, time
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class InterventionResponse(BaseModel):
    """Single intervention to deliver to user"""
    intervention_type: str
    priority: int
    title: str
    message: str
    action: str
    timing: str = "immediate"
    context: Dict[str, Any] = {}


class GetInterventionsResponse(BaseModel):
    """Response with list of interventions for user"""
    interventions: List[InterventionResponse]
    count: int


class LogInterventionRequest(BaseModel):
    """Request to log an intervention"""
    intervention_type: str
    priority: int
    title: str
    message: str
    action: str
    context: Optional[Dict[str, Any]] = None


class RecordInterventionResponseRequest(BaseModel):
    """Request to record user's response to intervention"""
    intervention_log_id: int
    user_response: str = Field(..., description="'engaged', 'dismissed', 'ignored', 'snoozed'")


class UserNotificationPreferencesUpdate(BaseModel):
    """Update user notification preferences"""
    dnd_enabled: Optional[bool] = None
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    max_notifications_per_day: Optional[int] = None
    enabled_intervention_types: Optional[List[str]] = None
    disabled_intervention_types: Optional[List[str]] = None
    preferred_study_times: Optional[Dict[str, Any]] = None


class UserNotificationPreferencesResponse(BaseModel):
    """User's notification preferences"""
    user_id: int
    dnd_enabled: bool
    quiet_hours_start: Optional[time]
    quiet_hours_end: Optional[time]
    max_notifications_per_day: int
    enabled_intervention_types: Optional[List[str]]
    disabled_intervention_types: Optional[List[str]]
    preferred_study_times: Optional[Dict[str, Any]]
    updated_at: datetime
