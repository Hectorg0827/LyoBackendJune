"""
Course Semantic Cache
Implements smart caching for course generation results.
Uses exact match normalization and optional Redis/File persistence.
"""
import json
import hashlib
import os
import re
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

# Try importing Redis, handle failure
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

class CourseSemanticCache:
    """
    Caches completed course courses to avoid regenerating the same content.
    Supports Redis (primary) and Filesystem (fallback).
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0", fallback_dir: str = "/tmp/.lyo_cache"):
        self.redis_client = None
        self.use_redis = False
        self.fallback_dir = fallback_dir
        
        # Try connecting to Redis
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                self.redis_client.ping()
                self.use_redis = True
                logger.info("✅ CourseSemanticCache: Connected to Redis")
            except Exception as e:
                logger.warning(f"⚠️ CourseSemanticCache: Redis unavailable ({e}). Using filesystem.")
        
        # Ensure fallback dir exists
        if not self.use_redis:
            os.makedirs(self.fallback_dir, exist_ok=True)

    def _normalize_topic(self, topic: str) -> str:
        """
        Normalize topic string for better cache hit rate.
        - Lowercase
        - Remove special chars
        - Remove common prefixes (intro to, basics of)
        """
        text = topic.lower().strip()
        # Remove common prefixes
        prefixes = ["introduction to ", "intro to ", "basics of ", "fundamentals of ", "guide to ", "course on ", "learn "]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):]
        
        # Remove special chars but keep spaces
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return text.strip()

    def _generate_key(self, topic: str, level: str, language: str = "English") -> str:
        """Generate a deterministic cache key."""
        norm_topic = self._normalize_topic(topic)
        norm_level = level.lower().strip()
        norm_lang = language.lower().strip()
        
        raw_key = f"{norm_topic}|{norm_level}|{norm_lang}"
        return hashlib.sha256(raw_key.encode()).hexdigest()

    async def get_cached_course(self, topic: str, level: str = "beginner", language: str = "English") -> Optional[Dict[str, Any]]:
        """Retrieve a course from cache."""
        key = self._generate_key(topic, level, language)
        
        try:
            # 1. Try Redis
            if self.use_redis:
                data = self.redis_client.get(f"course:{key}")
                if data:
                    logger.info(f"🎯 Cache HIT (Redis): {topic}")
                    return json.loads(data)
            
            # 2. Try File
            else:
                path = os.path.join(self.fallback_dir, f"{key}.json")
                if os.path.exists(path):
                    async with self._read_file_async(path) as content:
                        logger.info(f"🎯 Cache HIT (File): {topic}")
                        return json.loads(content)
                        
        except Exception as e:
            logger.error(f"❌ Cache Read Error: {e}")
            
        return None

    async def cache_course(self, topic: str, level: str, course_data: Dict[str, Any], language: str = "English"):
        """Store a completed course in cache."""
        key = self._generate_key(topic, level, language)
        
        try:
            json_data = json.dumps(course_data)
            
            # 1. Store in Redis (TTL: 7 days)
            if self.use_redis:
                self.redis_client.setex(f"course:{key}", 604800, json_data)
                
            # 2. Store in File
            else:
                path = os.path.join(self.fallback_dir, f"{key}.json")
                with open(path, "w") as f:
                    f.write(json_data)
                    
            logger.info(f"💾 Cached course: {topic}")
            
        except Exception as e:
            logger.error(f"❌ Cache Write Error: {e}")

    # Helper for async file I/O shim
    def _read_file_async(self, path):
        class AsyncContext:
            async def __aenter__(self):
                with open(path, 'r') as f:
                    return f.read()
            async def __aexit__(self, exc_type, exc, tb):
                pass
        return AsyncContext()

# Global instance
course_cache = CourseSemanticCache()
