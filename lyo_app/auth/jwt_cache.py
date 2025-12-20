import time
from typing import Optional, Dict, Any

class JWTCache:
    """Simple in-memory cache for JWT tokens."""
    
    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        
    def get(self, token: str) -> Optional[Dict[str, Any]]:
        if token in self._cache:
            entry = self._cache[token]
            if time.time() < entry["expires"]:
                return entry["data"]
            else:
                del self._cache[token]
        return None
        
    def set(self, token: str, data: Dict[str, Any]):
        self._cache[token] = {
            "data": data,
            "expires": time.time() + self.ttl
        }
        
    def invalidate(self, token: str):
        if token in self._cache:
            del self._cache[token]
