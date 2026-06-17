"""Teaching-through-creation API ("build-with-me", #4).

  POST /api/v1/create/projects                 start a build (mastery-scaffolded)
  GET  /api/v1/create/projects                 list my projects
  GET  /api/v1/create/projects/{id}            current step + plan
  POST /api/v1/create/projects/{id}/submit     submit an artifact for review
  POST /api/v1/create/projects/{id}/to-pod     build it together as a pod challenge
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user
from lyo_app.core.database import get_db
from lyo_app.models.enhanced import User
from lyo_app.creation.service import creation_service

router = APIRouter(prefix="/api/v1/create", tags=["teaching-through-creation"])


def _project_dto(p) -> dict:
    return {
        "id": p.id, "title": p.title, "goal": p.goal, "skill_id": p.skill_id,
        "scaffold_level": p.scaffold_level.value if hasattr(p.scaffold_level, "value") else p.scaffold_level,
        "steps": p.steps, "current_step": p.current_step,
        "status": p.status.value if hasattr(p.status, "value") else p.status,
        "degraded": p.degraded,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "completed_at": p.completed_at.isoformat() if p.completed_at else None,
    }


@router.post("/projects")
async def start_project(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    goal: str = Body(..., embed=True),
    title: Optional[str] = Body(None, embed=True),
    skill_id: Optional[str] = Body(None, embed=True),
):
    """Start a build-with-me project; the tutor plans mastery-scaffolded steps."""
    project = await creation_service.start_project(
        db, user_id=current_user.id, goal=goal, title=title, skill_id=skill_id)
    return _project_dto(project)


@router.get("/projects")
async def list_projects(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    projects = await creation_service.list_projects(db, current_user.id)
    return {"projects": [_project_dto(p) for p in projects]}


@router.get("/projects/{project_id}")
async def get_project(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    project = await creation_service.get_project(db, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _project_dto(project)


@router.post("/projects/{project_id}/submit")
async def submit_artifact(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    content: str = Body(..., embed=True),
):
    """Submit the learner's work for the current step; tutor reviews + advances."""
    try:
        return await creation_service.submit_artifact(
            db, project_id=project_id, user_id=current_user.id, content=content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/projects/{project_id}/to-pod")
async def to_pod_challenge(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Turn this build into a collaborative pod challenge (build it together)."""
    try:
        return await creation_service.to_pod_challenge(
            db, project_id=project_id, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
