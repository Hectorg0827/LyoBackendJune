"""
Calendar Tool for the Lyo OS.
Allows agents to suggest and manage learning time blocks.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from .base import BaseTool, ToolResult
from datetime import datetime, timedelta

class CalendarParameters(BaseModel):
    summary: str = Field(..., description="Short summary of the calendar event.")
    start_time: str = Field(..., description="Start time in ISO format.")
    duration_minutes: int = Field(30, description="Duration in minutes.")

class CalendarTool(BaseTool):
    """
    Tool to manage the member's learning calendar.
    (Mocked for Phase 5 to demonstrate agency).
    """
    name = "schedule_event"
    description = "Schedule a learning block or review session in the member's calendar."
    parameters_schema = CalendarParameters

    async def execute(self, user_id: int, **kwargs) -> ToolResult:
        summary = kwargs.get("summary")
        start_time_str = kwargs.get("start_time")
        duration = kwargs.get("duration_minutes", 30)
        
        # In a real implementation, this would call Google Calendar / Outlook API
        # For now, we simulate a successful integration.
        
        event_id = f"cal_{int(datetime.now().timestamp())}"
        
        # Trigger proactive notification reminder
        try:
            from lyo_app.services.proactive_dispatcher import proactive_dispatcher
            from datetime import datetime
            
            # Parse start time
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            reminder_time = start_time - timedelta(minutes=15)
            
            if reminder_time > datetime.now(start_time.tzinfo):
                proactive_dispatcher.schedule_notification(
                    user_id=user_id,
                    title=f"Calendar: {summary}",
                    body=f"Your scheduled session '{summary}' starts in 15 minutes.",
                    eta=reminder_time,
                    data={"type": "calendar_reminder", "event_id": event_id}
                )
        except Exception as e:
            pass # Non-critical failure for mock tool
        
        return ToolResult(
            success=True,
            output={"event_id": event_id, "summary": summary},
            message=f"Successfully scheduled '{summary}' for {start_time_str} ({duration} mins)."
        )
