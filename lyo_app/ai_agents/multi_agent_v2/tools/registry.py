"""
Tool Registry for managing and dispatching agent tools.
"""

import logging
from typing import Dict, List, Type, Optional
from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

class ToolRegistry:
    """
    Central registry for all available OS tools.
    """
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool):
        """Register a new tool instance."""
        if tool.name in self._tools:
            logger.warning(f"Overwriting already registered tool: {tool.name}")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Retrieve a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    async def execute_tool(self, tool_name: str, user_id: int, **kwargs) -> ToolResult:
        """Execute a tool by name."""
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output=None,
                message=f"Tool '{tool_name}' not found."
            )
        
        try:
            return await tool.execute(user_id=user_id, **kwargs)
        except Exception as e:
            logger.exception(f"Error executing tool '{tool_name}': {e}")
            return ToolResult(
                success=False,
                output=None,
                message=f"Tool execution failed: {str(e)}"
            )

# Global registry instance
tool_registry = ToolRegistry()
