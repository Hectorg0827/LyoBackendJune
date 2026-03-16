"""
Memory Management Tool for Lyo OS.
Allows agents to add, update, or delete long-term memory insights for a user.
"""

import logging
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from .base import BaseTool, ToolResult
from lyo_app.personalization.models import MemoryInsight
from lyo_app.services.embedding_service import embedding_service
from lyo_app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

class MemoryAction(BaseModel):
    action: Literal["add", "update", "delete"] = Field(..., description="The action to perform on user memory.")
    insight_id: Optional[int] = Field(None, description="The ID of the insight to update or delete (required for 'update' and 'delete').")
    text: Optional[str] = Field(None, description="The content of the insight (required for 'add' and 'update').")
    category: Optional[str] = Field("preference", description="The category of the insight (e.g., 'preference', 'struggle_point', 'goal').")
    confidence: float = Field(1.0, description="Confidence level of the insight (0-1).")

class MemoryManagementTool(BaseTool):
    """
    Tool to manage the member's persistent memory insights.
    Essential for 'forgetting' or 'correcting' information.
    """
    name = "manage_memory"
    description = "Add, update, or delete persistent memory insights (preferences, facts, goals) about the user."
    parameters_schema = MemoryAction

    async def execute(self, user_id: int, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        insight_id = kwargs.get("insight_id")
        text = kwargs.get("text")
        category = kwargs.get("category", "preference")
        confidence = kwargs.get("confidence", 1.0)

        async with AsyncSessionLocal() as db:
            if action == "add":
                return await self._add_insight(user_id, text, category, confidence, db)
            elif action == "update":
                return await self._update_insight(user_id, insight_id, text, category, db)
            elif action == "delete":
                return await self._delete_insight(user_id, insight_id, db)
            else:
                return ToolResult(success=False, output=None, message=f"Unknown action: {action}")

    async def _add_insight(self, user_id: int, text: str, category: str, confidence: float, db: AsyncSession) -> ToolResult:
        if not text:
            return ToolResult(success=False, output=None, message="Text is required for adding an insight.")
        
        try:
            # Generate embedding
            vector = await embedding_service.embed_text(text)
            
            new_insight = MemoryInsight(
                user_id=user_id,
                insight_text=text,
                category=category,
                confidence=confidence,
                embedding=vector
            )
            
            db.add(new_insight)
            await db.commit()
            await db.refresh(new_insight)
            
            return ToolResult(
                success=True,
                output={"id": new_insight.id, "text": text},
                message=f"Successfully added memory insight: '{text[:50]}...'"
            )
        except Exception as e:
            logger.error(f"Failed to add memory insight: {e}")
            return ToolResult(success=False, output=None, message=f"Error adding insight: {str(e)}")

    async def _update_insight(self, user_id: int, insight_id: int, text: str, category: str, db: AsyncSession) -> ToolResult:
        if not insight_id:
            return ToolResult(success=False, output=None, message="Insight ID is required for update.")
        
        try:
            result = await db.execute(
                select(MemoryInsight).where(MemoryInsight.id == insight_id, MemoryInsight.user_id == user_id)
            )
            insight = result.scalar_one_or_none()
            
            if not insight:
                return ToolResult(success=False, output=None, message=f"Insight with ID {insight_id} not found.")
            
            if text:
                insight.insight_text = text
                # Regenerate embedding if text changed
                insight.embedding = await embedding_service.embed_text(text)
            
            if category:
                insight.category = category
                
            await db.commit()
            
            return ToolResult(
                success=True,
                output={"id": insight.id, "text": insight.insight_text},
                message=f"Successfully updated memory insight {insight_id}."
            )
        except Exception as e:
            logger.error(f"Failed to update memory insight: {e}")
            return ToolResult(success=False, output=None, message=f"Error updating insight: {str(e)}")

    async def _delete_insight(self, user_id: int, insight_id: int, db: AsyncSession) -> ToolResult:
        if not insight_id:
            return ToolResult(success=False, output=None, message="Insight ID is required for deletion.")
        
        try:
            # First check if it exists and belongs to user
            result = await db.execute(
                select(MemoryInsight).where(MemoryInsight.id == insight_id, MemoryInsight.user_id == user_id)
            )
            insight = result.scalar_one_or_none()
            
            if not insight:
                return ToolResult(success=False, output=None, message=f"Insight with ID {insight_id} not found or access denied.")
            
            await db.execute(delete(MemoryInsight).where(MemoryInsight.id == insight_id))
            await db.commit()
            
            return ToolResult(
                success=True,
                output={"id": insight_id},
                message=f"Successfully deleted memory insight {insight_id}."
            )
        except Exception as e:
            logger.error(f"Failed to delete memory insight: {e}")
            return ToolResult(success=False, output=None, message=f"Error deleting insight: {str(e)}")
