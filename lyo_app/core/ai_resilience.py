"""
AI Resilience Manager with Circuit Breaker Pattern
Implements fallback mechanisms, retries, and load balancing for AI models
"""

import asyncio
try:
    import aiohttp
except ImportError:
    aiohttp = None
import time
import logging
import random
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import json
from lyo_app.core.config import settings
try:
    from lyo_app.integrations.gcp_secrets import get_secret
except Exception:  # pragma: no cover
    def get_secret(name: str, default=None):
        import os
        return os.getenv(name, default)

# Remove duplicate imports
#"""AI Resilience Manager with Circuit Breaker Pattern (restored)."""
#
#import aiohttp
#import time
#import logging
#import random
#import json
#from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass, field
from lyo_app.core.config import settings

try:
    from lyo_app.integrations.gcp_secrets import get_secret
except Exception:  # pragma: no cover
    def get_secret(name: str, default=None):
        import os
        return os.getenv(name, default)

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: int = 60
    expected_exception: type = Exception
    success_threshold: int = 3


@dataclass
class AIModelConfig:
    name: str
    endpoint: str
    api_key: str
    max_tokens: int = 1000
    timeout: int = 30
    priority: int = 1
    cost_per_token: float = 0.001
    capabilities: List[str] = field(default_factory=list)


class CircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.last_success_time = None

    async def call(self, func: Callable, *args, **kwargs):
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
        return (
            self.last_failure_time
            and time.time() - self.last_failure_time >= self.config.recovery_timeout
        )

    def _on_success(self, result):
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
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker OPENED after {self.failure_count} failures"
            )

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED


class AIResilienceManager:
    def __init__(self):
        self.models: Dict[str, AIModelConfig] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_cache: Dict[str, Any] = {}
        self.cache_ttl = 300
        self.daily_costs: Dict[str, float] = {}
        self.daily_usage_reset = time.time()

    async def initialize(self):
        gemini_key = get_secret("GEMINI_API_KEY", settings.gemini_api_key or "")
        self.models = {
            "gemini-pro": AIModelConfig(
                name="Google Gemini Pro",
                endpoint="https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent",
                api_key=gemini_key,
                max_tokens=2000,
                timeout=30,
                priority=1,
                cost_per_token=0.002,
                capabilities=["chat", "code", "analysis", "creative", "multimodal"],
            ),
            "gemini-pro-vision": AIModelConfig(
                name="Google Gemini Pro Vision",
                endpoint="https://generativelanguage.googleapis.com/v1/models/gemini-pro-vision:generateContent",
                api_key=gemini_key,
                max_tokens=1500,
                timeout=25,
                priority=2,
                cost_per_token=0.003,
                capabilities=["chat", "vision", "multimodal", "analysis"],
            ),
            "gemini-1.5-flash": AIModelConfig(
                name="Google Gemini 1.5 Flash",
                endpoint="https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent",
                api_key=gemini_key,
                max_tokens=1000,
                timeout=15,
                priority=3,
                cost_per_token=0.001,
                capabilities=["chat", "fast", "lightweight"],
            ),
        }

        for model_name in self.models:
            self.circuit_breakers[model_name] = CircuitBreaker(
                CircuitBreakerConfig(
                    failure_threshold=3,
                    recovery_timeout=60,
                    expected_exception=Exception,
                )
            )

        connector = aiohttp.TCPConnector(
            limit=100, limit_per_host=30, ttl_dns_cache=300, use_dns_cache=True
        )
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": "LyoApp/1.0"},
        )
        logger.info(
            f"AI Resilience Manager initialized with {len(self.models)} models"
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        provider_order: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        message_str = json.dumps(messages)
        if use_cache:
            cache_key = f"chat:{hash(message_str)}"
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached
        if provider_order:
            provider_map = {
                "google": "gemini-pro",
                "gemini": "gemini-pro",
                "gemini-pro": "gemini-pro",
                "gemini-vision": "gemini-pro-vision",
                "gemini-flash": "gemini-1.5-flash",
            }
            available_models = [
                provider_map.get(p)
                for p in provider_order
                if provider_map.get(p) in self.models
            ]
        else:
            available_models = self._get_available_models()
        if not available_models:
            raise Exception("No AI models available")
        last_exception = None
        for model_name in available_models:
            model = self.models[model_name]
            cb = self.circuit_breakers[model_name]
            if not cb.is_closed:
                continue
            if self._is_over_cost_limit(model_name, model):
                continue
            try:
                result = await self._call_model_with_messages(
                    model_name, model, messages, temperature, max_tokens
                )
                if use_cache:
                    self._add_to_cache(cache_key, result)
                self._track_usage(model_name, result.get("tokens_used", 0), model)
                return result
            except Exception as e:  # noqa: PERF203
                last_exception = e
                continue
        return self._get_fallback_response(message_str, str(last_exception))

    async def _call_model_with_messages(
        self,
        model_name: str,
        model: AIModelConfig,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        cb = self.circuit_breakers[model_name]

        async def make_call():
            return await self._make_api_call_with_messages(
                model, messages, temperature, max_tokens
            )

        return await cb.call(make_call)

    async def _make_api_call_with_messages(
        self,
        model: AIModelConfig,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        if not model.api_key:
            raise Exception(f"No API key configured for {model.name}")
        start_time = time.time()
        contents = []
        for msg in messages:
            role = "user" if msg["role"] in ["user", "system"] else "model"
            part = {"text": msg["content"]}
            if contents and contents[-1]["role"] == role:
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": role, "parts": [part]})
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
                "topP": 0.8,
                "topK": 40,
            },
        }
        headers = {"Content-Type": "application/json"}
        endpoint = f"{model.endpoint}?key={model.api_key}"
        async with self.session.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=model.timeout),
        ) as resp:
            if resp.status != 200:
                raise Exception(
                    f"Gemini API call failed: {resp.status} - {await resp.text()}"
                )
            data = await resp.json()
        response_time = time.time() - start_time
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        tokens_used = data.get("usageMetadata", {}).get("totalTokenCount", 0)
        return {
            "content": content,
            "model": model.name,
            "tokens_used": tokens_used,
            "response_time": response_time,
            "timestamp": time.time(),
        }

    def _get_available_models(self, preference: Optional[str] = None) -> List[str]:
        available = [
            name
            for name, model in self.models.items()
            if model.api_key and self.circuit_breakers[name].is_closed
        ]
        available.sort(key=lambda x: self.models[x].priority)
        if preference and preference in available:
            available.remove(preference)
            available.insert(0, preference)
        return available

    def _is_over_cost_limit(self, model_name: str, model: AIModelConfig) -> bool:
        if time.time() - self.daily_usage_reset > 86400:
            self.daily_costs.clear()
            self.daily_usage_reset = time.time()
        return self.daily_costs.get(model_name, 0) >= settings.ai_daily_cost_limit

    def _track_usage(self, model_name: str, tokens_used: int, model: AIModelConfig):
        cost = tokens_used * model.cost_per_token
        self.daily_costs[model_name] = self.daily_costs.get(model_name, 0) + cost

    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        item = self.request_cache.get(key)
        if item and time.time() - item["timestamp"] < self.cache_ttl:
            return item["data"]
        if item:
            del self.request_cache[key]
        return None

    def _add_to_cache(self, key: str, data: Dict[str, Any]):
        self.request_cache[key] = {"data": data, "timestamp": time.time()}
        if len(self.request_cache) > 1000:
            oldest = min(self.request_cache, key=lambda k: self.request_cache[k]["timestamp"])
            del self.request_cache[oldest]

    def _get_fallback_response(self, message: str, error: str) -> Dict[str, Any]:
        return {
            "response": random.choice(
                [
                    "I'm temporarily unable to process your request. Please try again soon.",
                    "Experiencing technical issues; retry shortly.",
                    "AI services unavailable right now; please retry in a minute.",
                ]
            ),
            "model": "fallback",
            "tokens_used": 0,
            "timestamp": time.time(),
            "error": error,
            "is_fallback": True,
        }

    async def get_health_status(self) -> Dict[str, Any]:
        status = {
            "models": {},
            "circuit_breakers": {},
            "cache_size": len(self.request_cache),
            "daily_costs": self.daily_costs.copy(),
        }
        for name, model in self.models.items():
            cb = self.circuit_breakers[name]
            status["models"][name] = {
                "configured": bool(model.api_key),
                "priority": model.priority,
                "capabilities": model.capabilities,
            }
            status["circuit_breakers"][name] = {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "last_failure": cb.last_failure_time,
                "last_success": cb.last_success_time,
            }
        return status

    async def close(self):
        if self.session:
            await self.session.close()
        logger.info("AI Resilience Manager closed")

