"""
AI Resilience Manager with Circuit Breaker Pattern
Implements fallback mechanisms, retries, and load balancing for AI models
"""

import asyncio
import aiohttp
import time
import logging
import random
import json
import os
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from lyo_app.core.config import settings

try:
    from lyo_app.integrations.gcp_secrets import get_secret
except Exception:  # pragma: no cover
    def get_secret(name: str, default=None):
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
        print(f">>> [PID {os.getpid()}] AI Resilience Init: Starting...", flush=True)
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not gemini_key:
            # Try specific project-controlled secret first
            gemini_key = get_secret("GEMINI_API_KEY")
            if not gemini_key:
                # Fallback to general Google API key secret
                gemini_key = get_secret("GOOGLE_API_KEY")
            
        if not gemini_key:
            # Final fallback to settings
            gemini_key = settings.gemini_api_key or ""
            
        key_status = "FOUND" if gemini_key else "MISSING"
        key_len = len(gemini_key) if gemini_key else 0
        print(f">>> [PID {os.getpid()}] AI Resilience Init: GEMINI_API_KEY status={key_status}, length={key_len}", flush=True)
        logger.info(f"AI Resilience Init: GEMINI_API_KEY status={key_status}, length={key_len}")
        
        if not gemini_key:
            logger.warning(f"⚠️ GEMINI_API_KEY not found! AI models will NOT be functional.")
            logger.warning(f"   Checked: GEMINI_API_KEY, GOOGLE_API_KEY (env + secrets)")
            logger.warning(f"   Available env keys: {[k for k in os.environ.keys() if 'API' in k or 'KEY' in k or 'SECRET' in k][:10]}")
        
        self.models = {
            "gemini-2.5-flash": AIModelConfig(
                name="Google Gemini 2.5 Flash",
                endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                api_key=gemini_key,
                max_tokens=4000,
                timeout=45,
                priority=1,
                cost_per_token=0.001,
                capabilities=["chat", "code", "analysis", "fast"],
            ),
            "gemini-2.5-pro": AIModelConfig(
                name="Google Gemini 2.5 Pro",
                endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent",
                api_key=gemini_key,
                max_tokens=8000,
                timeout=60,
                priority=2,
                cost_per_token=0.005,
                capabilities=["chat", "code", "analysis", "creative", "multimodal"],
            ),
            "gemini-2.0-flash-lite": AIModelConfig(
                name="Google Gemini 2.0 Flash Lite",
                endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent",
                api_key=gemini_key,
                max_tokens=1000,
                timeout=15,
                priority=3,
                cost_per_token=0.0005,
                capabilities=["chat", "fast", "lightweight"],
            ),
        }
        print(f">>> [PID {os.getpid()}] AI Resilience Init: Configured {len(self.models)} models", flush=True)

        for model_name in self.models:
            self.circuit_breakers[model_name] = CircuitBreaker(
                CircuitBreakerConfig(
                    failure_threshold=3,
                    recovery_timeout=60,
                    expected_exception=Exception,
                )
            )

        # Create SSL context with proper certificates for macOS compatibility
        import ssl
        try:
            import certifi
            ssl_context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ssl_context = ssl.create_default_context()
        
        connector = aiohttp.TCPConnector(
            limit=100, limit_per_host=30, ttl_dns_cache=300, use_dns_cache=True,
            ssl=ssl_context
        )
        timeout = aiohttp.ClientTimeout(total=75, connect=15)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": "LyoApp/1.0"},
        )
        logger.info(
            f"AI Resilience Manager initialized with {len(self.models)} models"
        )
        
        # Pre-warm connection pool for faster first requests
        await self._prewarm_connections()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        provider_order: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        # Lazy initialization if lifespan failed
        if not self.models:
            print(f">>> [PID {os.getpid()}] AI Resilience: Lazy Initialization in chat_completion...", flush=True)
            await self.initialize()
            
        message_str = json.dumps(messages)
        if use_cache:
            cache_key = f"chat:{hash(message_str)}"
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached
        
        # Intelligent model routing based on message complexity
        if not provider_order:
            provider_order = self._select_optimal_provider(messages, max_tokens)
        
        if provider_order:
            # The original code had a hardcoded map, but the new _get_available_models
            # will return actual model configs. We need to adapt this.
            # For now, let's assume provider_order contains model names directly
            # or we need to map them to actual model names.
            # Given the new _get_available_models, we should probably pass capabilities
            # or rely on the optimal provider selection to give us model names.
            # Let's simplify this part to use the new _get_available_models.
            # The `_select_optimal_provider` returns a list of model names.
            available_models_with_configs = [
                (name, self.models[name]) for name in provider_order if name in self.models
            ]
        else:
            available_models_with_configs = self._get_available_models() # This now returns (name, config) tuples

        if not available_models_with_configs:
            error_msg = ("No AI models available. This usually means GEMINI_API_KEY is missing or invalid. "
                        "Check Cloud Run secrets: ensure 'GEMINI_API_KEY' or 'GOOGLE_API_KEY' secret is configured.")
            logger.error(error_msg)
            raise Exception(error_msg)
        
        last_exception = None
        for model_name, model in available_models_with_configs: # Iterate over (name, config) tuples
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
        system_parts = []
        
        # Separate system messages from chat history
        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                # Map 'user' to 'user' and everything else (assistant/model) to 'model'
                role = "user" if msg["role"] == "user" else "model"
                part = {"text": msg["content"]}
                
                # Merge consecutive messages of same role (Gemini requirement)
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
        
        # Add system instruction if present
        if system_parts:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}]
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
                error_text = await resp.text()
                logger.error(f"Gemini API Error ({resp.status}): {error_text}")
                raise Exception(
                    f"Gemini API call failed: {resp.status} - {error_text}"
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

    def _get_available_models(self, capabilities: Optional[List[str]] = None) -> List[Tuple[str, AIModelConfig]]:
        print(f">>> [PID {os.getpid()}] AI Resilience: Getting available models. Total models count: {len(self.models)}", flush=True)
        available = []
        for name, config in self.models.items():
            if not config.api_key:
                continue
            
            # Check circuit breaker
            breaker = self.circuit_breakers.get(name)
            if breaker and not breaker.is_closed: # Changed from can_execute() to is_closed
                continue
                
            if capabilities:
                if all(cap in config.capabilities for cap in capabilities):
                    available.append((name, config))
            else:
                available.append((name, config))
                
        # Sort by priority (1 is highest)
        available.sort(key=lambda x: x[1].priority)
        print(f">>> [PID {os.getpid()}] AI Resilience: Found {len(available)} available models", flush=True)
        return available # Corrected return statement
    
    def _select_optimal_provider(self, messages: List[Dict[str, str]], max_tokens: int) -> List[str]:
        """Select optimal provider based on message complexity.
        
        Routes simple/short queries to flash-lite for 2x faster responses.
        Routes complex queries to full flash models.
        """
        if not messages:
            return ["gemini-2.5-flash"]  # Default
        
        last_message = messages[-1].get("content", "")
        total_chars = sum(len(m.get("content", "")) for m in messages)
        
        # Simple query indicators
        simple_patterns = [
            "hello", "hi", "thanks", "help", "what is", "explain",
            "define", "meaning of", "quick", "simple", "briefly"
        ]
        is_simple = any(p in last_message.lower() for p in simple_patterns)
        
        # Complex query indicators
        complex_patterns = [
            "analyze", "compare", "evaluate", "detailed", "comprehensive",
            "research", "in-depth", "synthesize", "advanced", "complex"
        ]
        is_complex = any(p in last_message.lower() for p in complex_patterns)
        
        # Routing logic:
        # - Short messages (<100 chars) + simple patterns -> lite (fastest)
        # - Complex patterns or long context -> 2.5-pro (most capable)
        # - Otherwise -> 2.5-flash (balanced)
        if len(last_message) < 100 and (is_simple or max_tokens < 256):
            return ["gemini-2.0-flash-lite", "gemini-2.5-flash"]
        elif is_complex or total_chars > 2000 or max_tokens > 1500:
            return ["gemini-2.5-pro", "gemini-2.5-flash"]
        else:
            return ["gemini-2.5-flash", "gemini-2.5-pro"]

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
        if not self.models:
            print(f">>> [PID {os.getpid()}] AI Resilience: Lazy Initialization in get_health_status...", flush=True)
            await self.initialize()
            
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

    async def _prewarm_connections(self):
        """Pre-warm HTTP connection pool for faster first requests.
        
        Establishes connections to Gemini API endpoints to eliminate
        cold-start latency (~50-100ms per connection).
        """
        try:
            # Get any model's API key for the health check
            sample_model = next(iter(self.models.values()), None)
            if not sample_model or not sample_model.api_key:
                logger.info("Skipping connection pre-warm: no API key configured")
                return
            
            # Pre-warm with a lightweight request to Gemini's health endpoint
            # Using the models list endpoint which is lightweight
            prewarm_url = f"https://generativelanguage.googleapis.com/v1/models?key={sample_model.api_key}"
            
            async with self.session.get(
                prewarm_url,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    logger.info("✅ Connection pool pre-warmed successfully")
                else:
                    logger.info(f"Connection pre-warm returned status {response.status}")
        except asyncio.TimeoutError:
            logger.info("Connection pre-warm timed out (non-critical)")
        except Exception as e:
            logger.info(f"Connection pre-warm failed (non-critical): {e}")
    
    async def close(self):
        if self.session:
            await self.session.close()
        logger.info("AI Resilience Manager closed")


# Global instance
ai_resilience_manager = AIResilienceManager()

