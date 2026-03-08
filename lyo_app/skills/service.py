"""
Service layer for the Canonical Skill Graph.
Handles database operations, relationship traversal, and skill queries.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import Skill, SkillEdge, SkillTag, SkillDomain
from .schemas import SkillCreate, SkillEdgeCreate


async def create_skill(db: AsyncSession, skill_in: SkillCreate) -> Skill:
    """Create a new skill node in the graph."""
    db_skill = Skill(
        name=skill_in.name,
        domain=skill_in.domain,
        description=skill_in.description,
        is_active=skill_in.is_active
    )
    
    db.add(db_skill)
    await db.commit()
    await db.refresh(db_skill)
    
    if skill_in.tags:
        for tag_name in skill_in.tags:
            tag = SkillTag(skill_id=db_skill.id, tag=tag_name)
            db.add(tag)
        await db.commit()
        await db.refresh(db_skill)
        
    return db_skill


async def get_skill(db: AsyncSession, skill_id: int) -> Optional[Skill]:
    """Retrieve a specific skill by its ID, complete with its tags."""
    query = (
        select(Skill)
        .where(Skill.id == skill_id)
        .options(selectinload(Skill.tags))
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_skill_by_name(db: AsyncSession, name: str) -> Optional[Skill]:
    """Retrieve a skill by its exact name."""
    query = (
        select(Skill)
        .where(Skill.name == name)
        .options(selectinload(Skill.tags))
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_skills_by_domain(db: AsyncSession, domain: SkillDomain) -> List[Skill]:
    """Retrieve all skills within a specific domain."""
    query = (
        select(Skill)
        .where(Skill.domain == domain)
        .options(selectinload(Skill.tags))
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def add_prerequisite(db: AsyncSession, edge_in: SkillEdgeCreate) -> SkillEdge:
    """
    Establish a directed edge indicating that `prerequisite_skill_id` 
    must be mastered before mastering `skill_id`.
    """
    db_edge = SkillEdge(
        skill_id=edge_in.skill_id,
        prerequisite_skill_id=edge_in.prerequisite_skill_id,
        weight=edge_in.weight
    )
    db.add(db_edge)
    await db.commit()
    await db.refresh(db_edge)
    return db_edge


async def get_prerequisites(db: AsyncSession, skill_id: int) -> List[SkillEdge]:
    """Retrieve all direct prerequisites for a given skill."""
    query = (
        select(SkillEdge)
        .where(SkillEdge.skill_id == skill_id)
        .options(selectinload(SkillEdge.prerequisite))
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_unlocks(db: AsyncSession, skill_id: int) -> List[SkillEdge]:
    """Retrieve all skills that become unlocked/available by mastering this skill."""
    query = (
        select(SkillEdge)
        .where(SkillEdge.prerequisite_skill_id == skill_id)
        .options(selectinload(SkillEdge.skill))
    )
    result = await db.execute(query)
    return list(result.scalars().all())
