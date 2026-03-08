"""
Tool Integration Hub initialization.
"""

from .registry import tool_registry
from .task_tool import TaskTool
from .calendar_tool import CalendarTool

# Initialize concrete tools
task_tool = TaskTool()
calendar_tool = CalendarTool()

# Register with global registry
tool_registry.register_tool(task_tool)
tool_registry.register_tool(calendar_tool)

__all__ = ["tool_registry", "task_tool", "calendar_tool"]
