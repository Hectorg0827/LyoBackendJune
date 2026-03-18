"""Cross-pipeline AI cost accounting.

Usage::

    from lyo_app.core.cost_tracker import cost_tracker

    cost_tracker.record_call(
        pipeline="a2a",
        model="gemini-2.0-flash",
        tokens=1200,
        user_id="user-abc",
    )

    report = cost_tracker.get_total_cost("user-abc")
    # {"total_cost_usd": 0.00072, "total_tokens": 1200, "calls": 1}
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Approximate USD cost per 1 000 tokens (input+output blended estimate).
# Update these whenever pricing changes.
# ---------------------------------------------------------------------------
_COST_PER_1K_TOKENS: Dict[str, float] = {
    # OpenAI
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
    "gpt-4-turbo": 0.01,
    "gpt-3.5-turbo": 0.0005,
    # Google Gemini
    "gemini-2.0-flash": 0.000075,
    "gemini-2.0-flash-lite": 0.000038,
    "gemini-1.5-pro": 0.00175,
    "gemini-1.5-flash": 0.000075,
    "gemini-pro": 0.0005,
}
_DEFAULT_COST_PER_1K = 0.001  # fallback for unknown models


@dataclass
class CallRecord:
    pipeline: str
    model: str
    tokens: int
    cost_usd: float
    user_id: Optional[str]
    timestamp: float = field(default_factory=time.time)


class CostTracker:
    """Thread-safe, in-memory cost tracker with per-user and global aggregates."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # user_id -> list of records  (None key = anonymous / system calls)
        self._records: Dict[Optional[str], List[CallRecord]] = defaultdict(list)
        self._global_records: List[CallRecord] = []

    @staticmethod
    def _estimate_cost(model: str, tokens: int) -> float:
        rate = _COST_PER_1K_TOKENS.get(model, _DEFAULT_COST_PER_1K)
        return rate * tokens / 1000

    def record_call(
        self,
        pipeline: str,
        model: str,
        tokens: int,
        user_id: Optional[str] = None,
    ) -> float:
        """Record a model call synchronously and return the estimated cost in USD."""
        cost = self._estimate_cost(model, tokens)
        rec = CallRecord(
            pipeline=pipeline,
            model=model,
            tokens=tokens,
            cost_usd=cost,
            user_id=user_id,
        )
        self._records[user_id].append(rec)
        self._global_records.append(rec)
        logger.debug(
            "[CostTracker] pipeline=%s model=%s tokens=%d cost=$%.6f user=%s",
            pipeline,
            model,
            tokens,
            cost,
            user_id or "anon",
        )
        return cost

    async def async_record_call(
        self,
        pipeline: str,
        model: str,
        tokens: int,
        user_id: Optional[str] = None,
    ) -> float:
        """Async-safe version of record_call."""
        async with self._lock:
            return self.record_call(pipeline, model, tokens, user_id)

    def get_total_cost(self, user_id: Optional[str] = None) -> Dict:
        """Return aggregated stats for a user (or all users if user_id is None)."""
        records = self._records[user_id] if user_id else self._global_records
        total_cost = sum(r.cost_usd for r in records)
        total_tokens = sum(r.tokens for r in records)
        return {
            "total_cost_usd": round(total_cost, 6),
            "total_tokens": total_tokens,
            "calls": len(records),
        }

    def get_breakdown_by_pipeline(self, user_id: Optional[str] = None) -> Dict[str, Dict]:
        """Return per-pipeline cost breakdown."""
        records = self._records[user_id] if user_id else self._global_records
        breakdown: Dict[str, Dict] = defaultdict(lambda: {"cost_usd": 0.0, "tokens": 0, "calls": 0})
        for rec in records:
            entry = breakdown[rec.pipeline]
            entry["cost_usd"] += rec.cost_usd
            entry["tokens"] += rec.tokens
            entry["calls"] += 1
        return {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in breakdown.items()}

    def reset(self, user_id: Optional[str] = None) -> None:
        """Clear records (useful in tests)."""
        if user_id:
            self._records[user_id].clear()
        else:
            self._records.clear()
            self._global_records.clear()


# Module-level singleton
cost_tracker = CostTracker()
