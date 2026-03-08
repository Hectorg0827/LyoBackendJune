"""
Base Tool definition for Agent Agency.
Allows agents to interact with external systems (Calendar, Tasks, etc.).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

class ToolResult(BaseModel):
    """Result of a tool execution."""
    success: bool
    output: Any
    message: str
    data: Optional[Dict[str, Any]] = None

class BaseTool(ABC):
    """
    Abstract base class for all Lyo OS tools.
    """
    name: str
    description: str
    parameters_schema: Optional[type[BaseModel]] = None

    @abstractmethod
    async def execute(self, user_id: int, **kwargs) -> ToolResult:
        """Execute the tool logic."""
        pass

    def get_tool_definition(self) -> Dict[str, Any]:
        """Return a structured definition for LLM tool calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema.schema() if self.parameters_schema else {}
        }
