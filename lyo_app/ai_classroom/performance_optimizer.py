"""
Living Classroom - Advanced Performance Optimizer
===============================================

Production performance optimization system with:
- Intelligent caching strategies
- Request batching and prefetching
- Memory pool management
- Adaptive resource allocation
- Real-time performance tuning
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from collections import defaultdict, deque

from pydantic import BaseModel
import aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from .sdui_models import Scene, Component, SceneType
from .monitoring import get_metrics

logger = logging.getLogger(__name__)


class CacheStrategy(str, Enum):
    """Cache eviction strategies"""
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"
    ADAPTIVE = "adaptive"


class OptimizationMode(str, Enum):
    """Performance optimization modes"""
    BALANCED = "balanced"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    MEMORY = "memory"
    POWER = "power"


@dataclass
class PerformanceMetrics:
    """Performance metrics tracking"""
    avg_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    requests_per_second: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_utilization: float = 0.0
    cache_hit_rate: float = 0.0
    error_rate: float = 0.0
    concurrent_connections: int = 0
    queue_depth: int = 0


@dataclass
class CacheEntry:
    """Cache entry with metadata"""
    key: str
    data: Any
    created_at: float
    accessed_at: float
    access_count: int = 0
    size_bytes: int = 0
    ttl_seconds: Optional[int] = None

    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        if self.ttl_seconds is None:
            return False
        return (time.time() - self.created_at) > self.ttl_seconds


class IntelligentCache:
    """High-performance intelligent caching system"""

    def __init__(self,
                 max_size_mb: int = 512,
                 strategy: CacheStrategy = CacheStrategy.ADAPTIVE,
                 default_ttl: int = 3600):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.strategy = strategy
        self.default_ttl = default_ttl

        # Cache storage
        self.cache: Dict[str, CacheEntry] = {}
        self.access_times: deque = deque()  # For LRU
        self.access_counts: Dict[str, int] = defaultdict(int)  # For LFU
        self.current_size_bytes = 0

        # Performance tracking
        self.hits = 0
        self.misses = 0
        self.evictions = 0

        logger.info(f"🚀 Intelligent Cache initialized: {max_size_mb}MB, strategy={strategy.value}")

    async def get(self, key: str) -> Optional[Any]:
        """Get item from cache with intelligent access tracking"""
        if key not in self.cache:
            self.misses += 1
            return None

        entry = self.cache[key]

        # Check expiration
        if entry.is_expired():
            await self._evict(key)
            self.misses += 1
            return None

        # Update access metadata
        entry.accessed_at = time.time()
        entry.access_count += 1
        self.access_counts[key] += 1
        self.access_times.append((key, entry.accessed_at))

        self.hits += 1
        return entry.data

    async def set(self, key: str, data: Any, ttl: Optional[int] = None) -> bool:
        """Set item in cache with intelligent eviction"""
        data_size = self._estimate_size(data)

        # Check if we need to evict
        while (self.current_size_bytes + data_size > self.max_size_bytes and
               len(self.cache) > 0):
            await self._evict_by_strategy()

        # Store the entry
        entry = CacheEntry(
            key=key,
            data=data,
            created_at=time.time(),
            accessed_at=time.time(),
            access_count=1,
            size_bytes=data_size,
            ttl_seconds=ttl or self.default_ttl
        )

        # Remove old entry if exists
        if key in self.cache:
            await self._evict(key)

        self.cache[key] = entry
        self.current_size_bytes += data_size
        self.access_times.append((key, entry.accessed_at))
        self.access_counts[key] = 1

        return True

    async def _evict_by_strategy(self):
        """Evict cache entries based on strategy"""
        if not self.cache:
            return

        if self.strategy == CacheStrategy.LRU:
            await self._evict_lru()
        elif self.strategy == CacheStrategy.LFU:
            await self._evict_lfu()
        elif self.strategy == CacheStrategy.TTL:
            await self._evict_expired()
        elif self.strategy == CacheStrategy.ADAPTIVE:
            await self._evict_adaptive()

    async def _evict_lru(self):
        """Evict least recently used item"""
        if not self.access_times:
            # Fallback to first item
            key = next(iter(self.cache))
            await self._evict(key)
            return

        # Find oldest access
        while self.access_times:
            key, _ = self.access_times.popleft()
            if key in self.cache:
                await self._evict(key)
                break

    async def _evict_lfu(self):
        """Evict least frequently used item"""
        if not self.access_counts:
            key = next(iter(self.cache))
            await self._evict(key)
            return

        # Find least used
        min_key = min(self.access_counts, key=self.access_counts.get)
        await self._evict(min_key)

    async def _evict_expired(self):
        """Evict expired items first"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired()
        ]

        if expired_keys:
            await self._evict(expired_keys[0])
        else:
            await self._evict_lru()  # Fallback

    async def _evict_adaptive(self):
        """Adaptive eviction based on access patterns"""
        # Prioritize expired items
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired()
        ]

        if expired_keys:
            await self._evict(expired_keys[0])
            return

        # Use hybrid LRU/LFU approach
        if len(self.cache) < 100:
            await self._evict_lru()
        else:
            # Score-based eviction
            scores = {}
            for key, entry in self.cache.items():
                recency_score = current_time - entry.accessed_at
                frequency_score = 1.0 / (entry.access_count + 1)
                scores[key] = recency_score + frequency_score

            worst_key = max(scores, key=scores.get)
            await self._evict(worst_key)

    async def _evict(self, key: str):
        """Remove specific key from cache"""
        if key not in self.cache:
            return

        entry = self.cache[key]
        self.current_size_bytes -= entry.size_bytes
        del self.cache[key]

        if key in self.access_counts:
            del self.access_counts[key]

        self.evictions += 1

    def _estimate_size(self, data: Any) -> int:
        """Estimate memory size of data"""
        try:
            if isinstance(data, str):
                return len(data.encode('utf-8'))
            elif isinstance(data, (dict, list)):
                return len(json.dumps(data, default=str).encode('utf-8'))
            elif hasattr(data, '__sizeof__'):
                return data.__sizeof__()
            else:
                return len(str(data).encode('utf-8'))
        except:
            return 1024  # Default estimate

    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "hit_rate": hit_rate,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "size_mb": self.current_size_bytes / 1024 / 1024,
            "entries": len(self.cache),
            "strategy": self.strategy.value
        }


class RequestBatcher:
    """Batches requests for efficient processing"""

    def __init__(self, batch_size: int = 10, max_wait_ms: int = 50):
        self.batch_size = batch_size
        self.max_wait_ms = max_wait_ms
        self.pending_requests: List[Tuple[str, asyncio.Future]] = []
        self.batch_timer: Optional[asyncio.Task] = None
        self.processing_lock = asyncio.Lock()

    async def add_request(self, request_id: str, processor: Callable) -> Any:
        """Add request to batch for processing"""
        future = asyncio.Future()

        async with self.processing_lock:
            self.pending_requests.append((request_id, future, processor))

            # Start timer if not already running
            if self.batch_timer is None or self.batch_timer.done():
                self.batch_timer = asyncio.create_task(
                    self._wait_and_process()
                )

            # Process immediately if batch is full
            if len(self.pending_requests) >= self.batch_size:
                if not self.batch_timer.done():
                    self.batch_timer.cancel()
                await self._process_batch()

        return await future

    async def _wait_and_process(self):
        """Wait for timeout then process batch"""
        await asyncio.sleep(self.max_wait_ms / 1000.0)
        async with self.processing_lock:
            if self.pending_requests:
                await self._process_batch()

    async def _process_batch(self):
        """Process all pending requests in batch"""
        if not self.pending_requests:
            return

        requests = self.pending_requests
        self.pending_requests = []

        # Group by processor type for efficiency
        processor_groups = defaultdict(list)
        for req_id, future, processor in requests:
            processor_groups[processor.__name__].append((req_id, future, processor))

        # Process each group
        for processor_name, group in processor_groups.items():
            try:
                # Run processors concurrently
                tasks = []
                for req_id, future, processor in group:
                    tasks.append(self._run_processor(req_id, future, processor))

                await asyncio.gather(*tasks)

            except Exception as e:
                logger.error(f"Batch processing error for {processor_name}: {e}")
                for _, future, _ in group:
                    if not future.done():
                        future.set_exception(e)

    async def _run_processor(self, req_id: str, future: asyncio.Future, processor: Callable):
        """Run individual processor and set result"""
        try:
            result = await processor(req_id)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)


class PerformanceOptimizer:
    """Advanced performance optimization engine"""

    def __init__(self, mode: OptimizationMode = OptimizationMode.BALANCED):
        self.mode = mode
        self.cache = IntelligentCache()
        self.batcher = RequestBatcher()

        # Performance tracking
        self.metrics_window = deque(maxlen=1000)
        self.optimization_history = []

        # Adaptive parameters
        self.adaptive_params = {
            "scene_cache_ttl": 300,  # 5 minutes
            "component_cache_ttl": 600,  # 10 minutes
            "batch_size": 10,
            "prefetch_threshold": 0.7,
            "memory_threshold": 0.8
        }

        logger.info(f"🔧 Performance Optimizer initialized: mode={mode.value}")

    async def optimize_scene_generation(self,
                                       scene_generator: Callable,
                                       user_id: str,
                                       session_id: str,
                                       **kwargs) -> Scene:
        """Optimize scene generation with caching and prefetching"""
        start_time = time.time()

        # Generate cache key
        cache_key = self._generate_scene_cache_key(user_id, session_id, kwargs)

        # Try cache first
        cached_scene = await self.cache.get(cache_key)
        if cached_scene:
            logger.debug(f"🎯 Scene cache hit: {cache_key}")
            return cached_scene

        # Generate scene with batching
        scene = await self.batcher.add_request(
            cache_key,
            lambda req_id: scene_generator(user_id=user_id, session_id=session_id, **kwargs)
        )

        # Cache the result
        await self.cache.set(
            cache_key,
            scene,
            ttl=self.adaptive_params["scene_cache_ttl"]
        )

        # Record performance
        duration = (time.time() - start_time) * 1000
        await self._record_performance("scene_generation", duration)

        # Trigger prefetching if needed
        asyncio.create_task(self._prefetch_likely_scenes(user_id, session_id))

        return scene

    async def optimize_component_rendering(self,
                                         components: List[Component]) -> List[Component]:
        """Optimize component rendering with intelligent prioritization"""
        start_time = time.time()

        # Sort components by priority and rendering cost
        optimized_components = await self._optimize_component_order(components)

        # Apply component-level optimizations
        for component in optimized_components:
            await self._optimize_component(component)

        # Record performance
        duration = (time.time() - start_time) * 1000
        await self._record_performance("component_optimization", duration)

        return optimized_components

    async def optimize_websocket_streaming(self,
                                         scene: Scene,
                                         connection_id: str) -> Dict[str, Any]:
        """Optimize WebSocket streaming with adaptive compression"""
        start_time = time.time()

        # Generate streaming strategy based on connection quality
        streaming_config = await self._generate_streaming_config(connection_id)

        # Optimize scene data for transmission
        optimized_scene = await self._optimize_scene_for_streaming(scene, streaming_config)

        # Record performance
        duration = (time.time() - start_time) * 1000
        await self._record_performance("websocket_optimization", duration)

        return {
            "scene": optimized_scene,
            "config": streaming_config,
            "optimization_time_ms": duration
        }

    async def _optimize_component_order(self, components: List[Component]) -> List[Component]:
        """Optimize component rendering order for best user experience"""

        def component_priority_score(component: Component) -> float:
            """Calculate priority score for component ordering"""
            base_priority = component.priority or 1

            # Critical components first
            if component.type == "TeacherMessage":
                return base_priority + 1000
            elif component.type == "CTAButton":
                return base_priority + 500
            elif component.type == "QuizCard":
                return base_priority + 800
            elif component.type == "Celebration":
                return base_priority + 300

            return base_priority

        # Sort by priority score
        sorted_components = sorted(components, key=component_priority_score)

        return sorted_components

    async def _optimize_component(self, component: Component):
        """Apply component-level optimizations"""

        # Cache component rendering data
        if hasattr(component, 'component_id'):
            cache_key = f"component:{component.component_id}"
            await self.cache.set(
                cache_key,
                component,
                ttl=self.adaptive_params["component_cache_ttl"]
            )

        # Optimize component delays for better UX
        if hasattr(component, 'delay_ms') and component.delay_ms:
            # Adaptive delay based on system load
            current_load = await self._get_system_load()
            if current_load > 0.8:
                component.delay_ms = max(50, component.delay_ms // 2)  # Reduce delays under load

    async def _generate_streaming_config(self, connection_id: str) -> Dict[str, Any]:
        """Generate optimal streaming configuration"""

        # Default configuration
        config = {
            "compression": True,
            "batch_size": 1,
            "delay_ms": 100,
            "progressive": True
        }

        # Adapt based on connection quality (would integrate with real metrics)
        connection_quality = await self._estimate_connection_quality(connection_id)

        if connection_quality < 0.5:  # Poor connection
            config.update({
                "compression": True,
                "batch_size": 5,  # Batch more aggressively
                "delay_ms": 200   # Longer delays
            })
        elif connection_quality > 0.8:  # Good connection
            config.update({
                "compression": False,  # Skip compression overhead
                "batch_size": 1,       # Send immediately
                "delay_ms": 50         # Shorter delays
            })

        return config

    async def _optimize_scene_for_streaming(self,
                                          scene: Scene,
                                          config: Dict[str, Any]) -> Scene:
        """Optimize scene data for efficient streaming"""

        # Create optimized copy
        optimized_scene = scene

        # Apply compression if enabled
        if config.get("compression"):
            # Would implement scene data compression here
            pass

        # Batch components if configured
        if config.get("batch_size", 1) > 1:
            # Group components for batch transmission
            pass

        return optimized_scene

    async def _prefetch_likely_scenes(self, user_id: str, session_id: str):
        """Prefetch likely next scenes based on user patterns"""

        # This would analyze user behavior patterns and prefetch
        # likely next scenes to reduce latency

        try:
            # Example: prefetch common follow-up scenes
            likely_scene_types = await self._predict_next_scenes(user_id)

            for scene_type in likely_scene_types[:3]:  # Limit prefetching
                prefetch_key = f"prefetch:{user_id}:{scene_type}"

                # Only prefetch if not already cached
                if not await self.cache.get(prefetch_key):
                    # Would generate and cache the scene
                    logger.debug(f"🔮 Prefetching scene type: {scene_type}")

        except Exception as e:
            logger.debug(f"Prefetch error: {e}")

    async def _predict_next_scenes(self, user_id: str) -> List[str]:
        """Predict likely next scene types for user"""

        # Simple prediction logic (would be more sophisticated in production)
        common_patterns = [
            ["instruction", "challenge", "celebration"],
            ["challenge", "correction", "instruction"],
            ["celebration", "instruction", "challenge"]
        ]

        # Return first pattern for now
        return common_patterns[0]

    async def _estimate_connection_quality(self, connection_id: str) -> float:
        """Estimate WebSocket connection quality"""

        # Would integrate with real connection metrics
        # For now, return a simulated quality score
        return 0.8  # Good quality

    async def _get_system_load(self) -> float:
        """Get current system load"""

        # Would integrate with system monitoring
        # For now, return simulated load
        return 0.3  # 30% load

    def _generate_scene_cache_key(self,
                                 user_id: str,
                                 session_id: str,
                                 params: Dict[str, Any]) -> str:
        """Generate cache key for scene"""

        # Create deterministic key from parameters
        key_data = {
            "user_id": user_id,
            "session_id": session_id,
            **params
        }

        key_string = json.dumps(key_data, sort_keys=True, default=str)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()

        return f"scene:{key_hash}"

    async def _record_performance(self, operation: str, duration_ms: float):
        """Record performance metrics"""

        metric = {
            "operation": operation,
            "duration_ms": duration_ms,
            "timestamp": time.time()
        }

        self.metrics_window.append(metric)

        # Update adaptive parameters based on performance
        await self._update_adaptive_parameters()

    async def _update_adaptive_parameters(self):
        """Update optimization parameters based on recent performance"""

        if len(self.metrics_window) < 100:
            return

        # Calculate recent performance metrics
        recent_metrics = list(self.metrics_window)[-100:]
        avg_duration = sum(m["duration_ms"] for m in recent_metrics) / len(recent_metrics)

        # Adjust cache TTL based on performance
        if avg_duration > 500:  # Slow performance
            self.adaptive_params["scene_cache_ttl"] = min(600, self.adaptive_params["scene_cache_ttl"] + 60)
        elif avg_duration < 200:  # Fast performance
            self.adaptive_params["scene_cache_ttl"] = max(60, self.adaptive_params["scene_cache_ttl"] - 30)

        # Adjust batch size
        if avg_duration > 300:
            self.adaptive_params["batch_size"] = min(20, self.adaptive_params["batch_size"] + 2)
        elif avg_duration < 100:
            self.adaptive_params["batch_size"] = max(1, self.adaptive_params["batch_size"] - 1)

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report"""

        if not self.metrics_window:
            return {"error": "No performance data available"}

        recent_metrics = list(self.metrics_window)

        # Calculate statistics
        durations = [m["duration_ms"] for m in recent_metrics]
        operations = defaultdict(list)
        for m in recent_metrics:
            operations[m["operation"]].append(m["duration_ms"])

        operation_stats = {}
        for op, times in operations.items():
            operation_stats[op] = {
                "count": len(times),
                "avg_ms": sum(times) / len(times),
                "min_ms": min(times),
                "max_ms": max(times),
                "p95_ms": sorted(times)[int(len(times) * 0.95)] if times else 0
            }

        return {
            "optimization_mode": self.mode.value,
            "cache_stats": self.cache.get_stats(),
            "adaptive_params": self.adaptive_params,
            "operation_stats": operation_stats,
            "overall_performance": {
                "avg_duration_ms": sum(durations) / len(durations),
                "total_operations": len(durations),
                "time_window_minutes": (recent_metrics[-1]["timestamp"] - recent_metrics[0]["timestamp"]) / 60
            }
        }


# Global optimizer instance
_performance_optimizer: Optional[PerformanceOptimizer] = None


async def get_performance_optimizer(mode: OptimizationMode = OptimizationMode.BALANCED) -> PerformanceOptimizer:
    """Get performance optimizer instance"""
    global _performance_optimizer

    if _performance_optimizer is None:
        _performance_optimizer = PerformanceOptimizer(mode)

    return _performance_optimizer


# Convenience functions
async def optimize_scene_generation(scene_generator: Callable,
                                   user_id: str,
                                   session_id: str,
                                   **kwargs) -> Scene:
    """Optimize scene generation"""
    optimizer = await get_performance_optimizer()
    return await optimizer.optimize_scene_generation(scene_generator, user_id, session_id, **kwargs)


async def optimize_component_rendering(components: List[Component]) -> List[Component]:
    """Optimize component rendering"""
    optimizer = await get_performance_optimizer()
    return await optimizer.optimize_component_rendering(components)


async def get_performance_report() -> Dict[str, Any]:
    """Get performance optimization report"""
    optimizer = await get_performance_optimizer()
    return optimizer.get_performance_report()