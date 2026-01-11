"""
AI Performance Optimization Engine
Intelligent caching, response optimization, and resource management for production AI agents.
"""

import asyncio
import time
import hashlib
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import threading

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None


# Torch and Transformers disabled to save memory on Cloud Run
TORCH_AVAILABLE = False
torch = None

TRANSFORMERS_AVAILABLE = False
pipeline = None

import structlog

# Optional prometheus metrics
try:
    from prometheus_client import Counter, Histogram, Gauge
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Create dummy classes
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def inc(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self

import redis.asyncio as redis

logger = structlog.get_logger(__name__)

# Metrics
response_time_histogram = Histogram('ai_response_time_seconds', 'AI response time', ['agent_type', 'model'])
cache_hit_counter = Counter('ai_cache_hits_total', 'Cache hits', ['cache_type'])
cache_miss_counter = Counter('ai_cache_misses_total', 'Cache misses', ['cache_type'])
gpu_utilization = Gauge('ai_gpu_utilization_percent', 'GPU utilization percentage')
memory_usage = Gauge('ai_memory_usage_bytes', 'Memory usage in bytes')

class OptimizationLevel(Enum):
    """Optimization aggressiveness levels."""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    MAXIMUM = "maximum"

@dataclass
class CacheConfig:
    """Cache configuration for different content types."""
    ttl_seconds: int
    max_size: int
    compression: bool = True
    versioning: bool = True

@dataclass
class PerformanceMetrics:
    """Performance tracking metrics."""
    response_time: float
    cache_hit_rate: float
    memory_usage: float
    gpu_utilization: float
    cost_per_request: float
    throughput: float
    
class IntelligentCacheManager:
    """Advanced caching with TTL, compression, and smart invalidation."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self.local_cache: Dict[str, Any] = {}
        self.cache_stats: Dict[str, int] = {"hits": 0, "misses": 0}
        self._initialized = False
        
        # Cache configurations for different content types
        self.cache_configs = {
            "curriculum": CacheConfig(ttl_seconds=3600, max_size=1000),  # 1 hour
            "content_curation": CacheConfig(ttl_seconds=1800, max_size=2000),  # 30 min
            "user_recommendations": CacheConfig(ttl_seconds=600, max_size=5000),  # 10 min
            "sentiment_analysis": CacheConfig(ttl_seconds=300, max_size=10000),  # 5 min
            "translations": CacheConfig(ttl_seconds=86400, max_size=20000),  # 24 hours
            "model_responses": CacheConfig(ttl_seconds=900, max_size=3000),  # 15 min
        }
    
    async def initialize(self):
        """Initialize cache manager."""
        if not self._initialized:
            logger.info("Initializing cache manager")
            self._initialized = True
    
    def _generate_cache_key(self, content_type: str, **kwargs) -> str:
        """Generate deterministic cache key."""
        key_data = {
            "type": content_type,
            "params": sorted(kwargs.items())
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return f"ai_cache:{hashlib.sha256(key_string.encode()).hexdigest()[:16]}"
    
    async def get(self, content_type: str, **kwargs) -> Optional[Any]:
        """Get from cache with intelligent fallback."""
        cache_key = self._generate_cache_key(content_type, **kwargs)
        
        try:
            # Try Redis first
            if self.redis:
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    self.cache_stats["hits"] += 1
                    cache_hit_counter.labels(cache_type=content_type).inc()
                    return json.loads(cached_data)
            
            # Fallback to local cache
            if cache_key in self.local_cache:
                cached_item = self.local_cache[cache_key]
                if cached_item["expires"] > time.time():
                    self.cache_stats["hits"] += 1
                    cache_hit_counter.labels(cache_type=content_type).inc()
                    return cached_item["data"]
                else:
                    del self.local_cache[cache_key]
            
            self.cache_stats["misses"] += 1
            cache_miss_counter.labels(cache_type=content_type).inc()
            return None
            
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None
    
    async def set(self, content_type: str, data: Any, **kwargs) -> bool:
        """Set cache with TTL and size management."""
        cache_key = self._generate_cache_key(content_type, **kwargs)
        config = self.cache_configs.get(content_type, self.cache_configs["model_responses"])
        
        try:
            serialized_data = json.dumps(data)
            expires_at = time.time() + config.ttl_seconds
            
            # Store in Redis
            if self.redis:
                await self.redis.setex(
                    cache_key, 
                    config.ttl_seconds, 
                    serialized_data
                )
            
            # Store in local cache
            self.local_cache[cache_key] = {
                "data": data,
                "expires": expires_at,
                "size": len(serialized_data)
            }
            
            # Manage cache size
            await self._manage_cache_size(content_type, config.max_size)
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def _manage_cache_size(self, content_type: str, max_size: int):
        """Remove oldest entries if cache exceeds size limit."""
        if len(self.local_cache) > max_size:
            # Sort by expiration time and remove oldest
            sorted_items = sorted(
                self.local_cache.items(),
                key=lambda x: x[1]["expires"]
            )
            
            items_to_remove = len(self.local_cache) - max_size
            for key, _ in sorted_items[:items_to_remove]:
                del self.local_cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = self.cache_stats["hits"] / total_requests if total_requests > 0 else 0
        
        return {
            "hit_rate": hit_rate,
            "total_hits": self.cache_stats["hits"],
            "total_misses": self.cache_stats["misses"],
            "cache_size": len(self.local_cache),
            "configurations": {k: asdict(v) for k, v in self.cache_configs.items()}
        }

class ResponseOptimizer:
    """Optimize AI responses for speed and quality."""
    
    def __init__(self):
        self.response_templates: Dict[str, str] = {}
        self.optimization_patterns: Dict[str, callable] = {}
        self._load_optimization_patterns()
    
    def _load_optimization_patterns(self):
        """Load common optimization patterns."""
        self.optimization_patterns = {
            "curriculum_generation": self._optimize_curriculum_response,
            "content_curation": self._optimize_curation_response,
            "sentiment_analysis": self._optimize_sentiment_response,
            "mentoring": self._optimize_mentoring_response,
        }
    
    async def optimize_response(self, agent_type: str, raw_response: str, context: Dict[str, Any]) -> str:
        """Apply intelligent response optimization."""
        start_time = time.time()
        
        try:
            # Apply specific optimization pattern
            if agent_type in self.optimization_patterns:
                optimized = await self.optimization_patterns[agent_type](raw_response, context)
            else:
                optimized = await self._generic_optimization(raw_response, context)
            
            # Record metrics
            optimization_time = time.time() - start_time
            response_time_histogram.labels(
                agent_type=agent_type, 
                model="optimization"
            ).observe(optimization_time)
            
            return optimized
            
        except Exception as e:
            logger.error(f"Response optimization failed: {e}")
            return raw_response
    
    async def _optimize_curriculum_response(self, response: str, context: Dict[str, Any]) -> str:
        """Optimize curriculum generation responses."""
        # Extract structured data from response
        # Apply curriculum-specific formatting
        # Add personalization based on user context
        
        user_level = context.get("user_level", "beginner")
        language = context.get("language", "en")
        
        # Add level-appropriate language complexity
        if user_level == "beginner":
            response = self._simplify_language(response)
        elif user_level == "advanced":
            response = self._enhance_technical_depth(response)
        
        return response
    
    async def _optimize_curation_response(self, response: str, context: Dict[str, Any]) -> str:
        """Optimize content curation responses."""
        # Rank recommendations by relevance score
        # Add personalization signals
        # Format for optimal presentation
        
        user_interests = context.get("user_interests", [])
        if user_interests:
            response = self._boost_relevant_content(response, user_interests)
        
        return response
    
    async def _optimize_sentiment_response(self, response: str, context: Dict[str, Any]) -> str:
        """Optimize sentiment analysis responses."""
        # Standardize sentiment scores
        # Add confidence intervals
        # Include actionable insights
        
        return self._format_sentiment_data(response)
    
    async def _optimize_mentoring_response(self, response: str, context: Dict[str, Any]) -> str:
        """Optimize mentoring responses."""
        # Personalize tone and style
        # Add encouraging elements
        # Include next steps
        
        user_mood = context.get("current_mood", "neutral")
        if user_mood == "frustrated":
            response = self._add_encouragement(response)
        elif user_mood == "confident":
            response = self._add_challenge(response)
        
        return response
    
    async def _generic_optimization(self, response: str, context: Dict[str, Any]) -> str:
        """Generic response optimization."""
        # Remove redundant information
        # Improve readability
        # Add context-appropriate formatting
        
        optimized = response.strip()
        optimized = self._improve_readability(optimized)
        return optimized
    
    def _simplify_language(self, text: str) -> str:
        """Simplify language for beginners."""
        # Replace complex terms with simpler alternatives
        simplifications = {
            "utilize": "use",
            "implement": "do",
            "demonstrate": "show",
            "facilitate": "help",
        }
        
        for complex_term, simple_term in simplifications.items():
            text = text.replace(complex_term, simple_term)
        
        return text
    
    def _enhance_technical_depth(self, text: str) -> str:
        """Add technical depth for advanced users."""
        # This would add more sophisticated technical details
        return text
    
    def _boost_relevant_content(self, text: str, interests: List[str]) -> str:
        """Boost content relevance based on user interests."""
        # This would reorder or emphasize content based on interests
        return text
    
    def _format_sentiment_data(self, text: str) -> str:
        """Format sentiment analysis data consistently."""
        # Standardize sentiment output format
        return text
    
    def _add_encouragement(self, text: str) -> str:
        """Add encouraging elements to mentoring responses."""
        encouraging_phrases = [
            "You're making great progress!",
            "This is a common challenge, and you're handling it well.",
            "Let's break this down into smaller steps.",
        ]
        
        # Add appropriate encouragement
        return f"{encouraging_phrases[0]} {text}"
    
    def _add_challenge(self, text: str) -> str:
        """Add challenges for confident users."""
        return f"{text}\n\nReady for a challenge? Try exploring..."
    
    def _improve_readability(self, text: str) -> str:
        """Improve text readability."""
        # Add proper spacing, formatting, etc.
        return text

class ResourceOptimizer:
    """Optimize system resources for AI workloads."""
    
    def __init__(self):
        self.gpu_available = TORCH_AVAILABLE and torch.cuda.is_available() if TORCH_AVAILABLE else False
        self.gpu_count = torch.cuda.device_count() if self.gpu_available else 0
        self.memory_threshold = 0.8  # 80% memory usage threshold
        self.cpu_threshold = 0.9     # 90% CPU usage threshold
        
        # Resource monitoring is now started explicitly via start() method
        # to prevent side effects during module import
        self._monitoring_active = False

    
    def start(self):
        """Start background resource monitoring explicitly."""
        if self._monitoring_active:
            return

        if PSUTIL_AVAILABLE:
            self._start_monitoring()
            self._monitoring_active = True
        else:
            logger.warning("psutil not available - resource monitoring disabled")

    def _start_monitoring(self):
        """Start background resource monitoring."""
        if not PSUTIL_AVAILABLE:
            logger.warning("Resource monitoring disabled - psutil not available")
            return
            
        def monitor_resources():
            while True:
                try:
                    # Monitor GPU
                    if self.gpu_available:
                        gpu_util = self._get_gpu_utilization()
                        gpu_utilization.set(gpu_util)
                    
                    # Monitor memory
                    memory_info = psutil.virtual_memory()
                    memory_usage.set(memory_info.used)
                    
                    time.sleep(5)  # Monitor every 5 seconds
                    
                except Exception as e:
                    logger.error(f"Resource monitoring error: {e}")
                    time.sleep(10)
        
        monitoring_thread = threading.Thread(target=monitor_resources, daemon=True)
        monitoring_thread.start()
    
    def _get_gpu_utilization(self) -> float:
        """Get current GPU utilization percentage."""
        if not self.gpu_available:
            return 0.0
        
        try:
            # This would use nvidia-ml-py or similar for actual GPU monitoring
            # For now, return a placeholder
            return 50.0
        except Exception:
            return 0.0
    
    def should_use_gpu(self, task_complexity: str) -> bool:
        """Decide whether to use GPU for a task."""
        if not self.gpu_available:
            return False
        
        gpu_util = self._get_gpu_utilization()
        
        # Use GPU for complex tasks if utilization is low
        if task_complexity in ["complex", "very_complex"] and gpu_util < 70:
            return True
        
        # Use GPU for simple tasks only if very low utilization
        if task_complexity == "simple" and gpu_util < 30:
            return True
        
        return False
    
    def get_optimal_batch_size(self, task_type: str) -> int:
        """Calculate optimal batch size based on available resources."""
        if not PSUTIL_AVAILABLE:
            # Default conservative batch sizes when monitoring unavailable
            base_sizes = {
                "sentiment_analysis": 16,
                "text_generation": 4,
                "translation": 8,
                "summarization": 2,
            }
            return base_sizes.get(task_type, 4)
        
        memory_info = psutil.virtual_memory()
        available_memory_gb = memory_info.available / (1024**3)
        
        # Base batch sizes by task type
        base_sizes = {
            "sentiment_analysis": 32,
            "text_generation": 8,
            "translation": 16,
            "summarization": 4,
        }
        
        base_size = base_sizes.get(task_type, 8)
        
        # Adjust based on available memory
        if available_memory_gb > 16:
            return base_size * 2
        elif available_memory_gb > 8:
            return base_size
        else:
            return max(1, base_size // 2)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system resource status."""
        if not PSUTIL_AVAILABLE:
            return {
                "memory": {
                    "total_gb": 0,
                    "available_gb": 0,
                    "percent_used": 0,
                    "threshold_exceeded": False
                },
                "cpu": {
                    "percent_used": 0,
                    "threshold_exceeded": False,
                    "core_count": 1
                },
                "gpu": {
                    "available": self.gpu_available,
                    "count": self.gpu_count,
                    "utilization": 0
                }
            }
        
        memory_info = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        
        return {
            "memory": {
                "total_gb": memory_info.total / (1024**3),
                "available_gb": memory_info.available / (1024**3),
                "percent_used": memory_info.percent,
                "threshold_exceeded": memory_info.percent > (self.memory_threshold * 100)
            },
            "cpu": {
                "percent_used": cpu_percent,
                "threshold_exceeded": cpu_percent > (self.cpu_threshold * 100),
                "core_count": psutil.cpu_count()
            },
            "gpu": {
                "available": self.gpu_available,
                "count": self.gpu_count,
                "utilization": self._get_gpu_utilization() if self.gpu_available else 0
            }
        }

class AIPerformanceOptimizer:
    """Main AI performance optimization coordinator."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.cache_manager = IntelligentCacheManager(redis_client)
        self.response_optimizer = ResponseOptimizer()
        self.resource_optimizer = ResourceOptimizer()
        self.optimization_level = OptimizationLevel.BALANCED
        self._initialized = False
        
        logger.info("AI Performance Optimizer initialized")
    
    async def initialize(self):
        """Initialize the performance optimizer."""
        if not self._initialized:
            await self.cache_manager.initialize()
            
            # Start resource monitoring thread
            self.resource_optimizer.start()
            
            self._initialized = True
            logger.info("AI Performance Optimizer fully initialized")
    
    def set_optimization_level(self, level: OptimizationLevel):
        """Set global optimization aggressiveness."""
        self.optimization_level = level
        logger.info(f"Optimization level set to: {level.value}")
    
    async def optimize_request(self, agent_type: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize an incoming AI request."""
        start_time = time.time()
        
        # Check cache first
        cached_response = await self.cache_manager.get(agent_type, **request_data)
        if cached_response:
            logger.debug(f"Cache hit for {agent_type}")
            return cached_response
        
        # Apply resource optimization
        resource_status = self.resource_optimizer.get_system_status()
        
        # Adjust request based on system load
        if resource_status["memory"]["threshold_exceeded"]:
            request_data = self._reduce_request_complexity(request_data)
        
        # Determine optimal processing strategy
        processing_config = self._get_processing_config(agent_type, resource_status)
        
        optimization_time = time.time() - start_time
        logger.debug(f"Request optimization took {optimization_time:.3f}s")
        
        return {
            "optimized_request": request_data,
            "processing_config": processing_config,
            "cache_key": self.cache_manager._generate_cache_key(agent_type, **request_data)
        }
    
    async def optimize_response(self, agent_type: str, response: str, context: Dict[str, Any]) -> str:
        """Optimize an AI response."""
        optimized = await self.response_optimizer.optimize_response(agent_type, response, context)
        
        # Cache the optimized response
        await self.cache_manager.set(agent_type, optimized, **context)
        
        return optimized
    
    def _reduce_request_complexity(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Reduce request complexity when resources are constrained."""
        # Reduce batch sizes, simplify processing, etc.
        if "max_tokens" in request_data:
            request_data["max_tokens"] = min(request_data["max_tokens"], 500)
        
        if "complexity" in request_data:
            request_data["complexity"] = "simple"
        
        return request_data
    
    def _get_processing_config(self, agent_type: str, resource_status: Dict[str, Any]) -> Dict[str, Any]:
        """Get optimal processing configuration."""
        config = {
            "use_gpu": self.resource_optimizer.should_use_gpu("medium"),
            "batch_size": self.resource_optimizer.get_optimal_batch_size(agent_type),
            "parallel_workers": 1,
            "timeout_seconds": 30
        }
        
        # Adjust based on optimization level
        if self.optimization_level == OptimizationLevel.AGGRESSIVE:
            config["parallel_workers"] = 2
            config["timeout_seconds"] = 60
        elif self.optimization_level == OptimizationLevel.MAXIMUM:
            config["parallel_workers"] = 4
            config["timeout_seconds"] = 120
        
        return config
    
    def get_performance_metrics(self) -> PerformanceMetrics:
        """Get comprehensive performance metrics."""
        cache_stats = self.cache_manager.get_stats()
        resource_status = self.resource_optimizer.get_system_status()
        
        return PerformanceMetrics(
            response_time=0.0,  # Would be calculated from recent requests
            cache_hit_rate=cache_stats["hit_rate"],
            memory_usage=resource_status["memory"]["percent_used"],
            gpu_utilization=resource_status["gpu"]["utilization"],
            cost_per_request=0.0,  # Would be calculated from usage tracking
            throughput=0.0  # Would be calculated from request metrics
        )

# Global optimizer instance
ai_performance_optimizer = AIPerformanceOptimizer()
