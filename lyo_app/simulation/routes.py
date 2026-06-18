"""Adaptive simulation API (#5).

  GET  /api/v1/simulations/scenarios            list available scenarios
  POST /api/v1/simulations                      start a run (mastery-scaffolded)
  GET  /api/v1/simulations                      list my runs
  GET  /api/v1/simulations/{id}                 current world state + objective
  POST /api/v1/simulations/{id}/step            make a decision, advance a turn
"""
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user
from lyo_app.core.database import get_db
from lyo_app.models.enhanced import User
from lyo_app.simulation.engine import get_scenario
from lyo_app.simulation.service import simulation_service

router = APIRouter(prefix="/api/v1/simulations", tags=["adaptive-simulation"])


def _sim_dto(s, *, schema: Optional[dict] = None) -> dict:
    dto = {
        "id": s.id, "scenario": s.scenario, "skill_id": s.skill_id,
        "difficulty": s.difficulty, "turn": s.turn,
        "status": s.status.value if hasattr(s.status, "value") else s.status,
        "world_state": s.world_state, "objective": s.objective,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
    }
    if schema is not None:
        dto["decision_schema"] = schema
    return dto


@router.get("/scenarios")
async def list_scenarios(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return {"scenarios": simulation_service.scenarios()}


@router.post("")
async def start_simulation(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    scenario: str = Body("coffee_shop", embed=True),
    skill_id: Optional[str] = Body(None, embed=True),
    difficulty: Optional[str] = Body(None, embed=True),
):
    try:
        sim = await simulation_service.start(
            db, user_id=current_user.id, scenario_key=scenario,
            skill_id=skill_id, difficulty=difficulty)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _sim_dto(sim, schema=get_scenario(sim.scenario).decision_schema())


@router.get("")
async def list_simulations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sims = await simulation_service.list(db, current_user.id)
    return {"simulations": [_sim_dto(s) for s in sims]}


@router.get("/{sim_id}")
async def get_simulation(
    sim_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sim = await simulation_service.get(db, sim_id, current_user.id)
    if sim is None:
        raise HTTPException(status_code=404, detail="simulation not found")
    return _sim_dto(sim, schema=get_scenario(sim.scenario).decision_schema())


@router.post("/{sim_id}/step")
async def step_simulation(
    sim_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    decision: Dict[str, Any] = Body(..., embed=True),
):
    try:
        return await simulation_service.step(
            db, sim_id=sim_id, user_id=current_user.id, decision=decision)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
