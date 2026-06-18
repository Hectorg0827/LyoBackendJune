"""Adaptive simulation engine (#5).

A scenario is a real, deterministic world model: given the current state and the
learner's decision, it computes the next state and an outcome. Determinism is
what makes the simulation *functional and testable* (not just an LLM narrating a
choose-your-own-adventure) — the LLM layer (in the service) only narrates on top.

The "adaptive" loop has two levels:
  1. Across runs — starting difficulty comes from the learner's mastery.
  2. Within a run — `effective_difficulty()` nudges event severity up when the
     learner is ahead of objective pace and down when they're behind, so the
     challenge tracks the individual.

`coffee_shop` is the implemented anchor scenario (teaches pricing, price
elasticity, margin, inventory, and cash flow). The Scenario ABC + registry make
the pattern extensible to other domains.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class Scenario(ABC):
    key: str
    title: str

    @abstractmethod
    def initial_state(self, difficulty: str) -> Dict[str, Any]: ...

    @abstractmethod
    def objective(self, difficulty: str) -> Dict[str, Any]: ...

    @abstractmethod
    def decision_schema(self) -> Dict[str, Any]:
        """Describe valid decision inputs so the client can render controls."""

    @abstractmethod
    def apply(self, state: Dict[str, Any], decision: Dict[str, Any],
              difficulty: str, turn: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Return (new_state, outcome)."""

    @abstractmethod
    def status(self, state: Dict[str, Any], objective: Dict[str, Any],
               turn: int) -> str:
        """One of 'active' | 'won' | 'lost'."""

    def effective_difficulty(self, state: Dict[str, Any], objective: Dict[str, Any],
                             difficulty: str, turn: int) -> str:
        """In-run adaptivity: shift event severity by objective pace. Default = none."""
        return difficulty


# --------------------------------------------------------------- coffee shop
class CoffeeShopScenario(Scenario):
    key = "coffee_shop"
    title = "Run a Coffee Shop"

    SWEET_SPOT = 3.0       # price ($) where demand is at baseline
    ELASTICITY = 0.8       # how sharply demand reacts to price moves
    UNIT_COST = 1.0        # $ to make/stock one cup
    FIXED_COST = 20.0      # daily rent etc.
    BASE_DEMAND = 50       # baseline customers/day at the sweet-spot price

    _PRESETS = {
        # start_cash, goal (cash to ADD), max_days
        "easy":   (200.0, 100.0, 7),
        "medium": (150.0, 150.0, 7),
        "hard":   (100.0, 250.0, 7),
    }

    def initial_state(self, difficulty: str) -> Dict[str, Any]:
        start_cash, _, _ = self._PRESETS.get(difficulty, self._PRESETS["medium"])
        return {
            "cash": start_cash,
            "inventory": 40,
            "reputation": 0.6,
            "price": self.SWEET_SPOT,
            "last_sales": 0,
            "last_demand": 0,
        }

    def objective(self, difficulty: str) -> Dict[str, Any]:
        start_cash, goal, max_days = self._PRESETS.get(
            difficulty, self._PRESETS["medium"])
        return {
            "target_cash": round(start_cash + goal, 2),
            "max_days": max_days,
            "description": f"Reach ${round(start_cash + goal)} cash within {max_days} days.",
        }

    def decision_schema(self) -> Dict[str, Any]:
        return {
            "price": {"type": "float", "min": 0.0, "max": 15.0,
                      "help": "Price per cup ($). Too high cuts demand."},
            "restock": {"type": "int", "min": 0, "max": 500,
                        "help": "Cups to stock today (costs $%.2f each)." % self.UNIT_COST},
            "marketing": {"type": "int", "min": 0, "max": 200,
                          "help": "Marketing spend ($); lifts demand + reputation."},
        }

    # -- the deterministic world model --------------------------------------
    def _event(self, difficulty: str, turn: int) -> Dict[str, float]:
        """Deterministic per-turn shocks (no RNG -> testable, still varied)."""
        demand_mult, cost_mult, note = 1.0, 1.0, ""
        if difficulty == "medium":
            if turn % 3 == 2:
                demand_mult, note = 0.8, "Rainy day — foot traffic is down."
        elif difficulty == "hard":
            if turn % 2 == 1:
                cost_mult, note = 1.5, "Supplier prices spiked today."
            elif turn % 3 == 0 and turn > 0:
                demand_mult, note = 0.7, "A competitor opened across the street."
        return {"demand_mult": demand_mult, "cost_mult": cost_mult, "note": note}

    def apply(self, state, decision, difficulty, turn):
        s = dict(state)
        price = _clamp(float(decision.get("price", s["price"])), 0.0, 15.0)
        restock = int(_clamp(int(decision.get("restock", 0)), 0, 500))
        marketing = int(_clamp(int(decision.get("marketing", 0)), 0, 200))

        eff = self.effective_difficulty(state, decision.get("_objective", {}),
                                        difficulty, turn)
        ev = self._event(eff, turn)

        # Demand: elastic around the sweet spot, scaled by reputation + marketing,
        # then hit by the day's event.
        price_factor = 1.0 - self.ELASTICITY * (price - self.SWEET_SPOT) / self.SWEET_SPOT
        price_factor = _clamp(price_factor, 0.0, 2.0)
        rep_factor = 0.5 + 0.5 * s["reputation"]
        marketing_boost = marketing / 10.0           # cups of extra demand
        demand = self.BASE_DEMAND * price_factor * rep_factor * ev["demand_mult"]
        demand = max(0, int(round(demand + marketing_boost)))

        sales = min(demand, s["inventory"])
        revenue = sales * price
        unit_cost = self.UNIT_COST * ev["cost_mult"]
        spend = restock * unit_cost + self.FIXED_COST + marketing
        cash = round(s["cash"] + revenue - spend, 2)
        inventory = s["inventory"] - sales + restock

        # Reputation: stockouts hurt; well-served demand + marketing help; gouging hurts.
        rep = s["reputation"]
        stockout = demand > s["inventory"]
        if stockout:
            rep -= 0.10
        elif sales > 0:
            rep += 0.04
        if price > self.SWEET_SPOT * 1.8:
            rep -= 0.06
        if marketing > 0:
            rep += min(0.05, marketing / 1000.0)
        rep = round(_clamp(rep, 0.0, 1.0), 3)

        new_state = {
            "cash": cash, "inventory": inventory, "reputation": rep,
            "price": price, "last_sales": sales, "last_demand": demand,
        }
        outcome = {
            "day": turn + 1,
            "price": price, "demand": demand, "sales": sales,
            "revenue": round(revenue, 2), "spend": round(spend, 2),
            "profit": round(revenue - spend, 2),
            "cash": cash, "inventory": inventory, "reputation": rep,
            "stockout": stockout, "event": ev["note"],
            "unit_cost": round(unit_cost, 2),
        }
        return new_state, outcome

    def status(self, state, objective, turn):
        if state["cash"] < 0:
            return "lost"
        if state["cash"] >= objective.get("target_cash", float("inf")):
            return "won"
        if turn >= objective.get("max_days", 7):
            return "lost"
        return "active"

    def effective_difficulty(self, state, objective, difficulty, turn):
        """Nudge severity by objective pace: ahead -> harder, behind -> easier."""
        target = objective.get("target_cash")
        max_days = objective.get("max_days", 7)
        if not target or turn <= 0:
            return difficulty
        order = ["easy", "medium", "hard"]
        if difficulty not in order:
            return difficulty
        # Linear pace: where cash "should" be by this turn.
        start = self.initial_state(difficulty)["cash"]
        expected = start + (target - start) * (turn / max_days)
        idx = order.index(difficulty)
        if state["cash"] > expected * 1.15:        # comfortably ahead -> escalate
            idx = min(idx + 1, len(order) - 1)
        elif state["cash"] < expected * 0.85:      # behind -> ease off
            idx = max(idx - 1, 0)
        return order[idx]


_REGISTRY: Dict[str, Scenario] = {
    CoffeeShopScenario.key: CoffeeShopScenario(),
}


def get_scenario(key: str) -> Scenario:
    scenario = _REGISTRY.get(key)
    if scenario is None:
        raise ValueError(f"unknown scenario '{key}'. "
                         f"available: {sorted(_REGISTRY)}")
    return scenario


def available_scenarios() -> Dict[str, str]:
    return {k: s.title for k, s in _REGISTRY.items()}
