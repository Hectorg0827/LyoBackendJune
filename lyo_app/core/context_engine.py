"""
Context Engine for Unified Learning OS.
Determines the user's current context (Student, Professional, Hobbyist) based on deterministic rules.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from lyo_app.personalization.models import LearnerState

logger = logging.getLogger(__name__)

class ContextEngine:
    """
    Rule-based engine to infer user context without expensive LLM calls.
    """
    
    def __init__(self):
        self.context_keywords = {
            "student": ["exam", "syllabus", "homework", "grade", "professor", "assignment", "quiz", "study"],
            "professional": ["meeting", "deadline", "client", "project", "presentation", "report", "quarterly", "boss"],
            "hobbyist": ["fun", "curious", "weekend", "project", "build", "learn", "explore"]
        }

    async def get_user_context(
        self, 
        db: AsyncSession, 
        user_id: int, 
        current_input: str = "",
        recent_history: list = None
    ) -> str:
        """
        Determines the user's current context.
        Priority:
        1. Explicit Keywords in current input (Emergency/Immediate intent)
        2. Time-based rules (Work hours vs Weekend)
        3. Stored state in DB
        """
        
        # 1. Check Immediate Input for Strong Signals
        input_lower = current_input.lower()
        
        # Emergency Student Context
        if any(k in input_lower for k in ["exam tomorrow", "test today", "due tonight", "panic"]):
            return "student_emergency"
            
        # Professional Context
        if any(k in input_lower for k in self.context_keywords["professional"]):
            return "professional"
            
        # Student Context
        if any(k in input_lower for k in self.context_keywords["student"]):
            return "student"

        # Hobbyist Context
        if any(k in input_lower for k in self.context_keywords["hobbyist"]):
            return "hobbyist"

        # 2. Time-Based Heuristics (if no strong keyword)
        # This is a weak signal, so we only use it if we don't have a stored state or to weight the decision
        # For now, let's skip complex time rules and rely on DB state as fallback
        
        # 3. Fallback to Stored State
        stmt = select(LearnerState).where(LearnerState.user_id == user_id)
        result = await db.execute(stmt)
        state = result.scalar_one_or_none()
        
        if state and state.current_active_context:
            return state.current_active_context
            
        # Default
        return "student"

    async def update_context_signal(self, db: AsyncSession, user_id: int, new_context: str):
        """
        Updates the persistent context state if a strong signal is detected.
        """
        stmt = select(LearnerState).where(LearnerState.user_id == user_id)
        result = await db.execute(stmt)
        state = result.scalar_one_or_none()
        
        if state:
            state.current_active_context = new_context
            state.updated_at = datetime.utcnow()
            await db.commit()

# Global instance
context_engine = ContextEngine()
