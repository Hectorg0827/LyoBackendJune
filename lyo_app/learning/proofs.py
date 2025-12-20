"""
Proof Engine.
Generates verifiable records of learning achievements.
"""

import hashlib
import json
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base

class ProofOfLearning(Base):
    """
    A verifiable record of a completed learning milestone.
    """
    __tablename__ = "proofs_of_learning"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # Link to either a standard Course or a GraphCourse
    course_id = Column(String, nullable=True) # String to support UUIDs of GraphCourses
    title = Column(String) # Snapshot of title
    
    issued_at = Column(DateTime, default=datetime.utcnow)
    proof_hash = Column(String, unique=True, index=True) # Cryptographic hash
    
    # Snapshot of skills validated by this proof
    skills_validated = Column(JSON, default=list) 
    
    # Metadata for verification
    issuer = Column(String, default="Lyo Learning OS")
    verification_url = Column(String, nullable=True)

class ProofEngine:
    """Service to generate and verify proofs."""
    
    async def generate_proof(
        self, 
        db: AsyncSession, 
        user_id: int, 
        course_id: str, 
        course_title: str,
        skills: List[str]
    ) -> ProofOfLearning:
        """
        Generates a new Proof of Learning.
        """
        # 1. Create the record data
        issued_at = datetime.utcnow()
        data_to_hash = {
            "user_id": user_id,
            "course_id": course_id,
            "issued_at": issued_at.isoformat(),
            "skills": sorted(skills),
            "issuer": "Lyo Learning OS"
        }
        
        # 2. Generate Hash
        payload = json.dumps(data_to_hash, sort_keys=True).encode()
        proof_hash = hashlib.sha256(payload).hexdigest()
        
        # 3. Save to DB
        proof = ProofOfLearning(
            user_id=user_id,
            course_id=course_id,
            title=course_title,
            issued_at=issued_at,
            proof_hash=proof_hash,
            skills_validated=skills,
            issuer="Lyo Learning OS",
            verification_url=f"https://lyo.app/verify/{proof_hash}"
        )
        
        db.add(proof)
        await db.commit()
        await db.refresh(proof)
        
        return proof

    async def get_user_proofs(self, db: AsyncSession, user_id: int) -> List[ProofOfLearning]:
        """Returns all proofs for a user."""
        stmt = select(ProofOfLearning).where(ProofOfLearning.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalars().all()
