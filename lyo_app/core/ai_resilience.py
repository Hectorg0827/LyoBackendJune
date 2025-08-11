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
        
        # Configure available AI models - Google Gemini only
        self.models = {
            "gemini-pro": AIModelConfig(
                name="Google Gemini Pro",
                endpoint="https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent",
                api_key=settings.gemini_api_key or "",
                max_tokens=2000,
                timeout=30,
                priority=1,
                cost_per_token=0.002,
                capabilities=["chat", "code", "analysis", "creative", "multimodal"]
            ),
            "gemini-pro-vision": AIModelConfig(
                name="Google Gemini Pro Vision",
                endpoint="https://generativelanguage.googleapis.com/v1/models/gemini-pro-vision:generateContent",
                api_key=settings.gemini_api_key or "",
                max_tokens=1500,
                timeout=25,
                priority=2,
                cost_per_token=0.003,
                capabilities=["chat", "vision", "multimodal", "analysis"]
            ),
            "gemini-1.5-flash": AIModelConfig(
                name="Google Gemini 1.5 Flash",
                endpoint="https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent",
                api_key=settings.gemini_api_key or "",
                max_tokens=1000,
                timeout=15,
                priority=3,
                cost_per_token=0.001,
                capabilities=["chat", "fast", "lightweight"]
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
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        provider_order: Optional[List[str]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get AI chat completion with conversation context
        """
        
        # Convert messages to a single string for caching
        message_str = json.dumps(messages)
        
        # Check cache first
        if use_cache:
            cache_key = f"chat:{hash(message_str)}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                logger.debug("Returning cached AI response")
                return cached_result
        
        # Get available models in priority order
        if provider_order:
            # Map provider names to model names - Google Gemini only
            provider_map = {
                "google": "gemini-pro",
                "gemini": "gemini-pro",
                "gemini-pro": "gemini-pro",
                "gemini-vision": "gemini-pro-vision", 
                "gemini-flash": "gemini-1.5-flash"
            }
            available_models = [provider_map.get(p) for p in provider_order if provider_map.get(p) in self.models]
        else:
            available_models = self._get_available_models()
        
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
            
            try:
                result = await self._call_model_with_messages(
                    model_name, model, messages, temperature, max_tokens
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
                logger.warning(f"Model {model_name} failed: {e}")
                continue  # Move to next model
        
        # All models failed - return fallback response
        return self._get_fallback_response(message_str, str(last_exception))

    async def _call_model_with_messages(
        self, model_name: str, model: AIModelConfig, messages: List[Dict[str, str]], 
        temperature: float, max_tokens: int
    ) -> Dict[str, Any]:
        """Call AI model with conversation messages"""
        
        circuit_breaker = self.circuit_breakers[model_name]
        
        async def make_api_call():
            return await self._make_api_call_with_messages(model, messages, temperature, max_tokens)
        
        return await circuit_breaker.call(make_api_call)

    async def _make_api_call_with_messages(
        self, model: AIModelConfig, messages: List[Dict[str, str]], 
        temperature: float, max_tokens: int
    ) -> Dict[str, Any]:
        """Make actual API call to Google Gemini with messages"""
        
        if not model.api_key:
            raise Exception(f"No API key configured for {model.name}")
        
        start_time = time.time()
        
        # Convert messages to Gemini format
        contents = []
        
        for msg in messages:
            role = "user" if msg["role"] in ["user", "system"] else "model"
            content_part = {"text": msg["content"]}
            
            # Find existing conversation turn or create new one
            if contents and contents[-1]["role"] == role:
                # Append to existing turn
                contents[-1]["parts"].append(content_part)
            else:
                # Create new conversation turn
                contents.append({
                    "role": role,
                    "parts": [content_part]
                })
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
                "topP": 0.8,
                "topK": 40
            }
        }
        
        headers = {"Content-Type": "application/json"}
        endpoint = f"{model.endpoint}?key={model.api_key}"
        
        # Make API call to Google Gemini
        async with self.session.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=model.timeout)
        ) as response:
            
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Gemini API call failed: {response.status} - {error_text}")
            
            result_data = await response.json()
            response_time = time.time() - start_time
            
            # Parse Gemini response
            content = result_data["candidates"][0]["content"]["parts"][0]["text"]
            tokens_used = result_data.get("usageMetadata", {}).get("totalTokenCount", 0)
            
            return {
                "content": content,
                "model": model.name,
                "tokens_used": tokens_used,
                "response_time": response_time,
                "timestamp": time.time()
            }
    
    async def _call_model_with_circuit_breaker(
        self, model_name: str, model: AIModelConfig, message: str
    ) -> Dict[str, Any]:
        """Call AI model with circuit breaker protection"""
        
        circuit_breaker = self.circuit_breakers[model_name]
        
        async def make_api_call():
            return await self._make_api_call(model, message)
        
        return await circuit_breaker.call(make_api_call)
    
    async def _make_api_call(self, model: AIModelConfig, message: str) -> Dict[str, Any]:
        """Make actual API call to Google Gemini model"""
        
        if not model.api_key:
            raise Exception(f"No API key configured for {model.name}")
        
        # Prepare request for Google Gemini
        payload = {
            "contents": [{"parts": [{"text": message}]}],
            "generationConfig": {
                "maxOutputTokens": model.max_tokens,
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
        }
        headers = {"Content-Type": "application/json"}
        
        # Add API key to URL for Gemini
        endpoint_with_key = f"{model.endpoint}?key={model.api_key}"
        
        # Make API call
        async with self.session.post(
            endpoint_with_key,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=model.timeout)
        ) as response:
            
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"API call failed: {response.status} - {error_text}")
            
            result_data = await response.json()
            
            # Parse Google Gemini response
            if "candidates" in result_data and len(result_data["candidates"]) > 0:
                candidate = result_data["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    content = candidate["content"]["parts"][0]["text"]
                else:
                    raise Exception("No content found in Gemini response")
            else:
                raise Exception("No candidates found in Gemini response")
            
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
