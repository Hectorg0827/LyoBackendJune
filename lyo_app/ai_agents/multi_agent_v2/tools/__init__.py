"""
Tool Integration Hub initialization.
"""

from .registry import tool_registry
from .task_tool import TaskTool
from .calendar_tool import CalendarTool
from .web_search_tool import WebSearchTool
from .memory_tool import MemoryManagementTool

# Initialize concrete tools
task_tool = TaskTool()
calendar_tool = CalendarTool()
web_search_tool = WebSearchTool()
memory_tool = MemoryManagementTool()

# Register with global registry
tool_registry.register_tool(task_tool)
tool_registry.register_tool(calendar_tool)
tool_registry.register_tool(web_search_tool)
tool_registry.register_tool(memory_tool)

__all__ = ["tool_registry", "task_tool", "calendar_tool", "web_search_tool", "memory_tool"]
