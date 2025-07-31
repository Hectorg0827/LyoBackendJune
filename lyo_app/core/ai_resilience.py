"""
AI Resilience Manager with Circuit Breaker Pattern
Implements fallback mechanisms, retries, and load balancing for AI models
"""

import asyncio
import aiohttp
import time
import logging
import random
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import json
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service is back

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5      # Number of failures before opening circuit
    recovery_timeout: int = 60      # Seconds to wait before trying again
    expected_exception: type = Exception
    success_threshold: int = 3      # Successful calls needed to close circuit

@dataclass
class AIModelConfig:
    name: str
    endpoint: str
    api_key: str
    max_tokens: int = 1000
    timeout: int = 30
    priority: int = 1  # Lower number = higher priority
    cost_per_token: float = 0.001
    capabilities: List[str] = field(default_factory=list)

class CircuitBreaker:
    """Circuit breaker implementation for AI model calls"""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.last_success_time = None
    
    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise Exception("Circuit breaker is OPEN - failing fast")
        
        try:
            result = await func(*args, **kwargs)
            return self._on_success(result)
        except self.config.expected_exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        return (
            self.last_failure_time and
            time.time() - self.last_failure_time >= self.config.recovery_timeout
        )
    
    def _on_success(self, result):
        """Handle successful call"""
        self.failure_count = 0
        self.last_success_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.success_count = 0
                logger.info("Circuit breaker CLOSED - service recovered")
        
        return result
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")
    
    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

class AIResilienceManager:
    """Manages AI model calls with resilience patterns"""
    
    def __init__(self):
        self.models: Dict[str, AIModelConfig] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_cache: Dict[str, Any] = {}
        self.cache_ttl = 300  # 5 minutes
        self.daily_costs: Dict[str, float] = {}
        self.daily_usage_reset = time.time()
    
    async def initialize(self):
        """Initialize AI models and circuit breakers"""
        
        # Configure available AI models
        self.models = {
            "openai-gpt4": AIModelConfig(
                name="OpenAI GPT-4",
                endpoint="https://api.openai.com/v1/chat/completions",
                api_key=settings.openai_api_key or "",
                max_tokens=2000,
                timeout=30,
                priority=1,
                cost_per_token=0.03,
                capabilities=["chat", "code", "analysis", "creative"]
            ),
            "anthropic-claude": AIModelConfig(
                name="Anthropic Claude",
                endpoint="https://api.anthropic.com/v1/messages",
                api_key=settings.anthropic_api_key or "",
                max_tokens=1500,
                timeout=25,
                priority=2,
                cost_per_token=0.025,
                capabilities=["chat", "analysis", "reasoning"]
            ),
            "google-gemini": AIModelConfig(
                name="Google Gemini",
                endpoint="https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent",
                api_key=settings.gemini_api_key or "",
                max_tokens=1000,
                timeout=20,
                priority=3,
                cost_per_token=0.002,
                capabilities=["chat", "multimodal"]
            )
        }
        
        # Initialize circuit breakers for each model
        for model_name in self.models:
            self.circuit_breakers[model_name] = CircuitBreaker(
                CircuitBreakerConfig(
                    failure_threshold=3,
                    recovery_timeout=60,
                    expected_exception=Exception
                )
            )
        
        # Initialize HTTP session
        connector = aiohttp.TCPConnector(
            limit=100,  # Total connection pool size
            limit_per_host=30,  # Per host limit
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
        )
        
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": "LyoApp/1.0"}
        )
        
        logger.info(f"AI Resilience Manager initialized with {len(self.models)} models")
    
    async def chat_completion(
        self,
        message: str,
        model_preference: Optional[str] = None,
        max_retries: int = 3,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get AI chat completion with resilience features
        """
        
        # Check cache first
        if use_cache:
            cache_key = f"chat:{hash(message)}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                logger.debug("Returning cached AI response")
                return cached_result
        
        # Get available models in priority order
        available_models = self._get_available_models(model_preference)
        
        if not available_models:
            raise Exception("No AI models available")
        
        # Try models with exponential backoff
        last_exception = None
        
        for model_name in available_models:
            model = self.models[model_name]
            circuit_breaker = self.circuit_breakers[model_name]
            
            # Skip if circuit is open
            if not circuit_breaker.is_closed:
                logger.warning(f"Skipping {model_name} - circuit breaker is open")
                continue
            
            # Check daily cost limit
            if self._is_over_cost_limit(model_name, model):
                logger.warning(f"Skipping {model_name} - daily cost limit reached")
                continue
            
            # Attempt call with retries and exponential backoff
            for attempt in range(max_retries):
                try:
                    result = await self._call_model_with_circuit_breaker(
                        model_name, model, message
                    )
                    
                    # Cache successful result
                    if use_cache:
                        self._add_to_cache(cache_key, result)
                    
                    # Track usage costs
                    self._track_usage(model_name, result.get("tokens_used", 0), model)
                    
                    logger.info(f"Successful AI response from {model_name}")
                    return result
                    
                except Exception as e:
                    last_exception = e
                    wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff with jitter
                    logger.warning(f"Attempt {attempt + 1} failed for {model_name}: {e}")
                    
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {wait_time:.2f} seconds...")
                        await asyncio.sleep(wait_time)
                    break  # Move to next model
        
        # All models failed - return fallback response
        return self._get_fallback_response(message, str(last_exception))
    
    async def _call_model_with_circuit_breaker(
        self, model_name: str, model: AIModelConfig, message: str
    ) -> Dict[str, Any]:
        """Call AI model with circuit breaker protection"""
        
        circuit_breaker = self.circuit_breakers[model_name]
        
        async def make_api_call():
            return await self._make_api_call(model, message)
        
        return await circuit_breaker.call(make_api_call)
    
    async def _make_api_call(self, model: AIModelConfig, message: str) -> Dict[str, Any]:
        """Make actual API call to AI model"""
        
        if not model.api_key:
            raise Exception(f"No API key configured for {model.name}")
        
        # Prepare request based on model type
        if "openai" in model.name.lower():
            payload = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": message}],
                "max_tokens": model.max_tokens,
                "temperature": 0.7
            }
            headers = {
                "Authorization": f"Bearer {model.api_key}",
                "Content-Type": "application/json"
            }
        
        elif "anthropic" in model.name.lower():
            payload = {
                "model": "claude-3-sonnet-20240229",
                "max_tokens": model.max_tokens,
                "messages": [{"role": "user", "content": message}]
            }
            headers = {
                "x-api-key": model.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }
        
        elif "gemini" in model.name.lower():
            payload = {
                "contents": [{"parts": [{"text": message}]}],
                "generationConfig": {"maxOutputTokens": model.max_tokens}
            }
            headers = {"Content-Type": "application/json"}
            # Add API key to URL for Gemini
            model.endpoint += f"?key={model.api_key}"
        
        else:
            raise Exception(f"Unknown model type: {model.name}")
        
        # Make API call
        async with self.session.post(
            model.endpoint,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=model.timeout)
        ) as response:
            
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"API call failed: {response.status} - {error_text}")
            
            result_data = await response.json()
            
            # Parse response based on model type
            if "openai" in model.name.lower():
                content = result_data["choices"][0]["message"]["content"]
                tokens_used = result_data.get("usage", {}).get("total_tokens", 0)
            
            elif "anthropic" in model.name.lower():
                content = result_data["content"][0]["text"]
                tokens_used = result_data.get("usage", {}).get("output_tokens", 0)
            
            elif "gemini" in model.name.lower():
                content = result_data["candidates"][0]["content"]["parts"][0]["text"]
                tokens_used = result_data.get("usageMetadata", {}).get("totalTokenCount", 0)
            
            return {
                "response": content,
                "model": model.name,
                "tokens_used": tokens_used,
                "timestamp": time.time()
            }
    
    def _get_available_models(self, preference: Optional[str] = None) -> List[str]:
        """Get list of available models sorted by priority"""
        
        available = []
        for name, model in self.models.items():
            if model.api_key and self.circuit_breakers[name].is_closed:
                available.append(name)
        
        # Sort by priority (lower number = higher priority)
        available.sort(key=lambda x: self.models[x].priority)
        
        # Put preferred model first if specified and available
        if preference and preference in available:
            available.remove(preference)
            available.insert(0, preference)
        
        return available
    
    def _is_over_cost_limit(self, model_name: str, model: AIModelConfig) -> bool:
        """Check if daily cost limit would be exceeded"""
        
        # Reset daily usage if needed
        if time.time() - self.daily_usage_reset > 86400:  # 24 hours
            self.daily_costs.clear()
            self.daily_usage_reset = time.time()
        
        current_cost = self.daily_costs.get(model_name, 0)
        return current_cost >= settings.ai_daily_cost_limit
    
    def _track_usage(self, model_name: str, tokens_used: int, model: AIModelConfig):
        """Track usage and costs"""
        cost = tokens_used * model.cost_per_token
        self.daily_costs[model_name] = self.daily_costs.get(model_name, 0) + cost
        logger.debug(f"Usage tracked: {model_name} - {tokens_used} tokens, ${cost:.4f}")
    
    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get response from cache if still valid"""
        if key in self.request_cache:
            cached_item = self.request_cache[key]
            if time.time() - cached_item["timestamp"] < self.cache_ttl:
                return cached_item["data"]
            else:
                del self.request_cache[key]
        return None
    
    def _add_to_cache(self, key: str, data: Dict[str, Any]):
        """Add response to cache"""
        self.request_cache[key] = {
            "data": data,
            "timestamp": time.time()
        }
        
        # Simple cache cleanup - remove oldest entries if cache is too large
        if len(self.request_cache) > 1000:
            oldest_key = min(self.request_cache.keys(), 
                           key=lambda k: self.request_cache[k]["timestamp"])
            del self.request_cache[oldest_key]
    
    def _get_fallback_response(self, message: str, error: str) -> Dict[str, Any]:
        """Generate fallback response when all models fail"""
        
        fallback_responses = [
            "I'm temporarily unable to process your request. Please try again in a moment.",
            "I'm experiencing technical difficulties. Your message is important to me, so please retry shortly.",
            "My AI systems are currently unavailable. Please try your question again in a few minutes.",
        ]
        
        return {
            "response": random.choice(fallback_responses),
            "model": "fallback",
            "tokens_used": 0,
            "timestamp": time.time(),
            "error": error,
            "is_fallback": True
        }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all AI models"""
        
        status = {
            "models": {},
            "circuit_breakers": {},
            "cache_size": len(self.request_cache),
            "daily_costs": self.daily_costs.copy()
        }
        
        for model_name, model in self.models.items():
            circuit_breaker = self.circuit_breakers[model_name]
            
            status["models"][model_name] = {
                "configured": bool(model.api_key),
                "priority": model.priority,
                "capabilities": model.capabilities
            }
            
            status["circuit_breakers"][model_name] = {
                "state": circuit_breaker.state.value,
                "failure_count": circuit_breaker.failure_count,
                "last_failure": circuit_breaker.last_failure_time,
                "last_success": circuit_breaker.last_success_time
            }
        
        return status
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
        logger.info("AI Resilience Manager closed")

# Singleton instance
ai_resilience_manager = AIResilienceManager()
