"""
Redis-backed Job Store for Course Generation.

Replaces the in-memory dict that was causing 404s when Cloud Run
routes consecutive requests to different container instances.

Falls back to an in-memory dict when Redis is unavailable (local dev).
"""
import json
import os
import logging
from typing import Optional, Dict, Any

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

# TTL for job entries: 1 hour (jobs are short-lived)
JOB_TTL_SECONDS = 3600


class RedisJobStore:
    """
    Dict-like wrapper around Redis for course generation job tracking.
    
    Supports the same interface as a Python dict so it can be a
    drop-in replacement for the old `job_store: Dict[str, Dict] = {}`.
    
    Usage:
        store = RedisJobStore()
        store[job_id] = {"status": "processing", ...}
        job = store.get(job_id)
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis = None
        self._use_redis = False
        self._fallback: Dict[str, Dict[str, Any]] = {}

        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")

        if REDIS_AVAILABLE:
            try:
                self._redis = redis.from_url(url, decode_responses=True)
                self._redis.ping()
                self._use_redis = True
                logger.info("✅ RedisJobStore: Connected to Redis")
            except Exception as e:
                logger.warning(f"⚠️ RedisJobStore: Redis unavailable ({e}). Using in-memory fallback.")
        else:
            logger.warning("⚠️ RedisJobStore: redis package not installed. Using in-memory fallback.")

    # ── Dict-compatible interface ──────────────────────────────────────

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID. Returns None if not found."""
        if self._use_redis:
            try:
                data = self._redis.get(f"job:{job_id}")
                if data:
                    return json.loads(data)
                return None
            except Exception as e:
                logger.error(f"RedisJobStore.get error: {e}")
                # Fallthrough to in-memory
                return self._fallback.get(job_id)
        return self._fallback.get(job_id)

    def __getitem__(self, job_id: str) -> Dict[str, Any]:
        """Dict-style access: store[job_id]"""
        result = self.get(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    def __setitem__(self, job_id: str, job_data: Dict[str, Any]):
        """Dict-style assignment: store[job_id] = {...}"""
        self.set(job_id, job_data)

    def __contains__(self, job_id: str) -> bool:
        return self.get(job_id) is not None

    def set(self, job_id: str, job_data: Dict[str, Any]):
        """Store a job with TTL."""
        if self._use_redis:
            try:
                self._redis.setex(
                    f"job:{job_id}",
                    JOB_TTL_SECONDS,
                    json.dumps(job_data, default=str),
                )
                return
            except Exception as e:
                logger.error(f"RedisJobStore.set error: {e}")
                # Fallthrough to in-memory

        self._fallback[job_id] = job_data

    def save(self, job_id: str, job_data: Dict[str, Any]):
        """Alias for set() — used after mutating a job dict to persist changes."""
        self.set(job_id, job_data)

    def delete(self, job_id: str):
        """Remove a job."""
        if self._use_redis:
            try:
                self._redis.delete(f"job:{job_id}")
            except Exception as e:
                logger.error(f"RedisJobStore.delete error: {e}")

        self._fallback.pop(job_id, None)


# ── Singleton ──────────────────────────────────────────────────────────

_store: Optional[RedisJobStore] = None


def get_job_store() -> RedisJobStore:
    """Get or create the global job store instance."""
    global _store
    if _store is None:
        _store = RedisJobStore()
    return _store
