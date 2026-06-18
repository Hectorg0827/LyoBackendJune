"""Adaptive simulation service (#5).

Wires the deterministic engine to the learner model and persistence:
  - start: difficulty from mastery (suggest_content_difficulty); init world state
    + objective; persist the run.
  - step: validate decision -> engine computes next state + outcome -> persist a
    turn -> resolve win/lose -> narrate (LLM, degrades to a deterministic recap).
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from lyo_app.simulation.engine import get_scenario, available_scenarios
from lyo_app.simulation.models import Simulation, SimulationTurn, SimStatus

logger = logging.getLogger(__name__)


class SimulationService:
    def scenarios(self) -> Dict[str, str]:
        return available_scenarios()

    # ------------------------------------------------------------- start
    async def start(
        self, db: AsyncSession, *, user_id: int, scenario_key: str,
        skill_id: Optional[str] = None, difficulty: Optional[str] = None,
    ) -> Simulation:
        scenario = get_scenario(scenario_key)  # raises ValueError if unknown
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = await self._difficulty_for(db, user_id, skill_id)

        sim = Simulation(
            user_id=user_id,
            scenario=scenario_key,
            skill_id=skill_id,
            difficulty=difficulty,
            world_state=scenario.initial_state(difficulty),
            objective=scenario.objective(difficulty),
            turn=0,
            status=SimStatus.ACTIVE,
        )
        db.add(sim)
        await db.commit()
        await db.refresh(sim)
        return sim

    async def get(self, db: AsyncSession, sim_id: int, user_id: int
                  ) -> Optional[Simulation]:
        sim = (await db.execute(
            select(Simulation).where(Simulation.id == sim_id)
        )).scalar_one_or_none()
        if sim is None or sim.user_id != user_id:
            return None
        return sim

    async def list(self, db: AsyncSession, user_id: int) -> List[Simulation]:
        rows = (await db.execute(
            select(Simulation).where(Simulation.user_id == user_id)
            .order_by(desc(Simulation.created_at))
        )).scalars().all()
        return list(rows)

    # ------------------------------------------------------------- step
    async def step(
        self, db: AsyncSession, *, sim_id: int, user_id: int,
        decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        sim = await self.get(db, sim_id, user_id)
        if sim is None:
            raise ValueError("simulation not found")
        if sim.status != SimStatus.ACTIVE:
            raise ValueError("simulation is already over")

        scenario = get_scenario(sim.scenario)
        # Pass the objective into the decision so in-run adaptivity can see pace.
        dec = dict(decision or {})
        dec["_objective"] = sim.objective

        new_state, outcome = scenario.apply(
            sim.world_state, dec, sim.difficulty, sim.turn)
        next_turn = sim.turn + 1
        new_status = scenario.status(new_state, sim.objective, next_turn)

        narration, degraded = await self._narrate(
            scenario.title, outcome, new_status, sim.objective)

        # Persist the turn (store the decision without our internal _objective).
        clean_decision = {k: v for k, v in dec.items() if not k.startswith("_")}
        db.add(SimulationTurn(
            simulation_id=sim.id, turn_index=sim.turn,
            decision=clean_decision, outcome=outcome,
            narration=narration, degraded=degraded))

        # Advance the run. JSON columns need an explicit dirty flag.
        sim.world_state = new_state
        flag_modified(sim, "world_state")
        sim.turn = next_turn
        sim.status = SimStatus(new_status)
        if new_status in ("won", "lost"):
            sim.completed_at = datetime.utcnow()

        await db.commit()
        await db.refresh(sim)
        return {
            "turn": sim.turn,
            "status": sim.status.value,
            "world_state": sim.world_state,
            "outcome": outcome,
            "narration": narration,
            "degraded": degraded,
            "objective": sim.objective,
        }

    # ----------------------------------------------------------- helpers
    async def _difficulty_for(self, db: AsyncSession, user_id: int,
                              skill_id: Optional[str]) -> str:
        try:
            from lyo_app.personalization.service import personalization_engine
            return await personalization_engine.suggest_content_difficulty(
                db, str(user_id), skill_id=skill_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"sim difficulty lookup failed for {user_id}: {e}")
            return "medium"

    async def _narrate(
        self, title: str, outcome: Dict[str, Any], status: str,
        objective: Dict[str, Any],
    ) -> tuple[str, bool]:
        """LLM color commentary + a coaching nudge; deterministic recap fallback."""
        prompt = (
            f"Scenario: {title}. The learner just finished day {outcome.get('day')}.\n"
            f"Numbers: {outcome}\n"
            f"Objective: {objective.get('description')}\n"
            f"Run status now: {status}.\n"
            "In 2-3 sentences, narrate what happened in-world and give ONE concrete "
            "coaching tip about pricing, inventory, or cash flow. Be encouraging."
        )
        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            resp = await ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a sharp, supportive business-sim coach."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6, max_tokens=220,
            )
            if resp and not resp.get("is_fallback"):
                content = resp.get("content") or resp.get("text")
                if content and content.strip():
                    return content.strip(), False
        except Exception as e:  # noqa: BLE001
            logger.warning(f"sim narration LLM unavailable: {e}")

        return self._fallback_narration(outcome, status), True

    @staticmethod
    def _fallback_narration(outcome: Dict[str, Any], status: str) -> str:
        parts = [f"Day {outcome.get('day')}: sold {outcome.get('sales')} of "
                 f"{outcome.get('demand')} cups wanted at ${outcome.get('price')}, "
                 f"profit ${outcome.get('profit')}, cash ${outcome.get('cash')}."]
        if outcome.get("event"):
            parts.append(outcome["event"])
        if outcome.get("stockout"):
            parts.append("You sold out — lost sales and a reputation hit. "
                         "Stock more next time.")
        elif outcome.get("sales", 0) == 0:
            parts.append("No sales — your price may be too high for your reputation. "
                         "Try lowering it.")
        if status == "won":
            parts.append("🎉 You hit the cash goal — well played!")
        elif status == "lost":
            parts.append("The run ended short of the goal. Review your pricing and "
                         "restock pacing and try again.")
        return " ".join(parts)


simulation_service = SimulationService()
