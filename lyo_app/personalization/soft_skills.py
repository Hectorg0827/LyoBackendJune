"""
Soft Skills Tracking Model & Service.
Tracks non-cognitive skills like Communication, Critical Thinking, and Leadership based on user interactions.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base

class SoftSkillType(str, Enum):
    COMMUNICATION = "communication"
    CRITICAL_THINKING = "critical_thinking"
    CREATIVITY = "creativity"
    LEADERSHIP = "leadership"
    COLLABORATION = "collaboration"
    ADAPTABILITY = "adaptability"
    EMPATHY = "empathy"

class UserSoftSkill(Base):
    """Tracks a specific soft skill for a user."""
    __tablename__ = "user_soft_skills"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    skill_name = Column(String, index=True)  # From SoftSkillType
    
    score = Column(Float, default=0.0)  # 0.0 to 1.0
    confidence = Column(Float, default=0.0)  # How sure we are (based on evidence count)
    evidence_count = Column(Integer, default=0)
    
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    # Store recent evidence (e.g., "Asked a thoughtful question in Chat")
    recent_evidence = Column(JSON, default=list) 

class SoftSkillsService:
    """Service to update and retrieve soft skills."""
    
    async def record_evidence(
        self, 
        db: AsyncSession, 
        user_id: int, 
        skill: SoftSkillType, 
        score_delta: float, 
        evidence_description: str
    ):
        """
        Records new evidence for a soft skill.
        
        Args:
            score_delta: Positive or negative impact (e.g., +0.1 for good communication)
        """
        # Find existing record
        stmt = select(UserSoftSkill).where(
            UserSoftSkill.user_id == user_id,
            UserSoftSkill.skill_name == skill.value
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        
        if not record:
            record = UserSoftSkill(
                user_id=user_id,
                skill_name=skill.value,
                score=0.5,  # Start neutral
                confidence=0.1,
                evidence_count=0
            )
            db.add(record)
        
        # Update Score (Simple moving average-ish)
        # We weight the new evidence by confidence
        learning_rate = 0.1
        record.score = max(0.0, min(1.0, record.score + (score_delta * learning_rate)))
        
        # Update Metadata
        record.evidence_count += 1
        record.confidence = min(1.0, record.confidence + 0.05)
        record.last_updated = datetime.utcnow()
        
        # Update Evidence Log (Keep last 5)
        evidence_list = record.recent_evidence or []
        evidence_list.append({
            "date": datetime.utcnow().isoformat(),
            "desc": evidence_description,
            "delta": score_delta
        })
        record.recent_evidence = evidence_list[-5:]
        
        await db.commit()
        await db.refresh(record)
        return record

    async def get_user_profile(self, db: AsyncSession, user_id: int) -> Dict[str, float]:
        """Returns a dictionary of skill scores for the user."""
        stmt = select(UserSoftSkill).where(UserSoftSkill.user_id == user_id)
        result = await db.execute(stmt)
        skills = result.scalars().all()
        
        return {s.skill_name: s.score for s in skills}

class SoftSkillAnalyzer:
    """Analyzes text for soft skill signals."""
    
    def __init__(self):
        self.patterns = {
            SoftSkillType.CRITICAL_THINKING: [
                r"why\s+is\s+that",
                r"how\s+does\s+this\s+relate",
                r"what\s+if",
                r"evidence\s+for",
                r"compare\s+and\s+contrast",
                r"assuming\s+that"
            ],
            SoftSkillType.COMMUNICATION: [
                r"thank\s+you",
                r"please",
                r"could\s+you\s+clarify",
                r"in\s+other\s+words",
                r"to\s+summarize"
            ],
            SoftSkillType.CREATIVITY: [
                r"imagine\s+if",
                r"new\s+idea",
                r"what\s+about\s+combining",
                r"alternative\s+approach"
            ],
            SoftSkillType.LEADERSHIP: [
                r"let's\s+focus\s+on",
                r"next\s+steps",
                r"plan\s+of\s+action",
                r"goal\s+is"
            ]
        }
        
    def analyze(self, text: str) -> List[Dict]:
        """
        Returns a list of detected skills and evidence.
        Example: [{"skill": "critical_thinking", "delta": 0.1, "desc": "Asked 'why'"}]
        """
        import re
        text_lower = text.lower()
        results = []
        
        for skill, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    results.append({
                        "skill": skill,
                        "delta": 0.05,
                        "desc": f"Used phrase matching pattern: '{pattern}'"
                    })
                    break # Count once per skill per message
                    
        return results

