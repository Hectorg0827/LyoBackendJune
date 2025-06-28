"""
AI Orchestrator - Intelligent Model Routing and Management

The orchestrator is the central brain of the AI system, providing:
- Intelligent routing between on-device Gemma and cloud LLM models
- Circuit breaker pattern for fault tolerance
- Performance monitoring and cost optimization
- Context-aware model selection
- Fallback mechanisms and error recovery
"""

import asyncio
import json
import logging
import time
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    """Available AI model types."""
    GEMMA_ON_DEVICE = "gemma_on_device"
    CLOUD_LLM = "cloud_llm"
    HYBRID = "hybrid"


class TaskComplexity(str, Enum):
    """Task complexity levels for routing decisions."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    CRITICAL = "critical"


@dataclass
class ModelResponse:
    """Standardized response from any AI model."""
    content: str
    model_used: ModelType
    response_time_ms: float
    tokens_used: Optional[int] = None
    cost_estimate: Optional[float] = None
    confidence_score: Optional[float] = None
    error: Optional[str] = None


@dataclass
class ModelMetrics:
    """Performance metrics for a model."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0
    last_failure: Optional[datetime] = None
    circuit_breaker_open: bool = False


class OnDeviceGemmaClient:
    """
    Mock implementation of on-device Gemma client.
    In production, this would interface with the actual Gemma model.
    """
    
    def __init__(self, model_path: str = "./models/gemma-2b"):
        self.model_path = model_path
        self.is_loaded = False
        self.load_time = None
        
    async def initialize(self) -> bool:
        """Initialize the on-device model."""
        try:
            # Mock initialization - in production, load actual model
            await asyncio.sleep(0.1)  # Simulate loading time
            self.is_loaded = True
            self.load_time = datetime.utcnow()
            logger.info("Gemma on-device model initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Gemma model: {e}")
            return False
    
    async def generate(self, prompt: str, max_tokens: int = 150, temperature: float = 0.7) -> ModelResponse:
        """Generate response using on-device Gemma model."""
        start_time = time.time()
        
        try:
            if not self.is_loaded:
                await self.initialize()
            
            # Mock generation - in production, call actual Gemma API
            await asyncio.sleep(0.2)  # Simulate processing time
            
            # Simple response generation based on prompt analysis
            response_content = self._generate_mock_response(prompt)
            response_time = (time.time() - start_time) * 1000
            
            return ModelResponse(
                content=response_content,
                model_used=ModelType.GEMMA_ON_DEVICE,
                response_time_ms=response_time,
                tokens_used=len(response_content.split()) * 2,  # Rough estimate
                cost_estimate=0.0,  # On-device is free
                confidence_score=0.8
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            logger.error(f"Gemma generation failed: {e}")
            
            return ModelResponse(
                content="",
                model_used=ModelType.GEMMA_ON_DEVICE,
                response_time_ms=response_time,
                error=str(e)
            )
    
    def _generate_mock_response(self, prompt: str) -> str:
        """Generate a mock response based on prompt analysis."""
        prompt_lower = prompt.lower()
        
        if "help" in prompt_lower or "assist" in prompt_lower:
            return "I'm here to help! What specific topic would you like assistance with?"
        elif "explain" in prompt_lower:
            return "Let me break this down for you in simple terms..."
        elif "quiz" in prompt_lower or "test" in prompt_lower:
            return "Great question! Let's work through this step by step."
        elif "struggling" in prompt_lower or "difficult" in prompt_lower:
            return "I understand this can be challenging. Let's approach it differently."
        else:
            return "That's an interesting question! Let me provide you with a helpful response."


class CloudLLMClient:
    """
    Cloud LLM client for complex tasks.
    Supports OpenAI, Anthropic, and other cloud providers.
    """
    
    def __init__(self, api_key: Optional[str] = None, endpoint: str = "https://api.openai.com/v1/chat/completions"):
        self.api_key = api_key or os.getenv("CLOUD_LLM_API_KEY")
        self.endpoint = endpoint
        self.model_name = "gpt-3.5-turbo"  # Default model
        
    async def generate(self, prompt: str, max_tokens: int = 300, temperature: float = 0.7) -> ModelResponse:
        """Generate response using cloud LLM."""
        start_time = time.time()
        
        try:
            if not self.api_key:
                raise Exception("Cloud LLM API key not configured")
            
            # Prepare request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": "You are a helpful AI mentor for an educational platform."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            # Make API call
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    json=payload
                )
                
                response_time = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    tokens_used = data.get("usage", {}).get("total_tokens", 0)
                    
                    # Rough cost estimate (varies by model)
                    cost_per_token = 0.000002  # $0.002 per 1K tokens for gpt-3.5-turbo
                    cost_estimate = tokens_used * cost_per_token
                    
                    return ModelResponse(
                        content=content,
                        model_used=ModelType.CLOUD_LLM,
                        response_time_ms=response_time,
                        tokens_used=tokens_used,
                        cost_estimate=cost_estimate,
                        confidence_score=0.95
                    )
                else:
                    raise Exception(f"API error: {response.status_code} - {response.text}")
                    
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            logger.error(f"Cloud LLM generation failed: {e}")
            
            return ModelResponse(
                content="",
                model_used=ModelType.CLOUD_LLM,
                response_time_ms=response_time,
                error=str(e)
            )


class AIOrchestrator:
    """
    Central AI orchestrator with intelligent routing and management.
    
    Features:
    - Intelligent model selection based on task complexity
    - Circuit breaker pattern for fault tolerance
    - Performance monitoring and optimization
    - Cost-aware routing
    - Fallback mechanisms
    """
    
    def __init__(self):
        self.on_device_client = OnDeviceGemmaClient()
        self.cloud_client = CloudLLMClient()
        
        # Model metrics tracking
        self.model_metrics: Dict[ModelType, ModelMetrics] = {
            ModelType.GEMMA_ON_DEVICE: ModelMetrics(),
            ModelType.CLOUD_LLM: ModelMetrics()
        }
        
        # Circuit breaker configuration
        self.circuit_breaker_threshold = 5  # failures before opening
        self.circuit_breaker_timeout = 300  # 5 minutes
        
        # Cost optimization settings
        self.daily_cost_limit = 10.0  # $10 per day
        self.current_daily_cost = 0.0
        self.cost_reset_date = datetime.utcnow().date()
        
        # Task complexity mapping
        self.complexity_keywords = {
            TaskComplexity.SIMPLE: [
                "hello", "hi", "thanks", "okay", "yes", "no", 
                "good", "great", "help", "basic"
            ],
            TaskComplexity.MEDIUM: [
                "explain", "how", "why", "what", "understand",
                "clarify", "example", "show", "demonstrate"
            ],
            TaskComplexity.COMPLEX: [
                "analyze", "compare", "evaluate", "synthesize",
                "create", "design", "solve", "complex", "advanced"
            ],
            TaskComplexity.CRITICAL: [
                "emergency", "urgent", "critical", "important",
                "deadline", "exam", "assessment", "failing"
            ]
        }
        
        logger.info("AIOrchestrator initialized with hybrid routing capabilities")
    
    async def initialize(self) -> bool:
        """Initialize the orchestrator and all clients."""
        try:
            # Initialize on-device model
            gemma_success = await self.on_device_client.initialize()
            
            if gemma_success:
                logger.info("AI Orchestrator fully initialized")
                return True
            else:
                logger.warning("AI Orchestrator initialized with limited capabilities (cloud only)")
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize AI Orchestrator: {e}")
            return False
    
    async def route_and_execute(
        self, 
        task_type: str, 
        prompt: str, 
        user_context: Optional[Dict] = None,
        force_model: Optional[ModelType] = None
    ) -> ModelResponse:
        """
        Intelligently route and execute an AI task.
        
        Args:
            task_type: Type of task (conversation, analysis, generation, etc.)
            prompt: Input prompt for the AI
            user_context: Optional user context for better routing decisions
            force_model: Force use of specific model (for testing/debugging)
            
        Returns:
            ModelResponse: Response from the selected AI model
        """
        try:
            # Determine task complexity
            complexity = self._analyze_task_complexity(prompt, task_type)
            
            # Select appropriate model
            selected_model = force_model or self._select_model(complexity, task_type, user_context)
            
            # Check circuit breaker
            if self._is_circuit_breaker_open(selected_model):
                logger.warning(f"Circuit breaker open for {selected_model}, falling back")
                selected_model = self._get_fallback_model(selected_model)
            
            # Check cost limits
            if selected_model == ModelType.CLOUD_LLM and not self._is_within_cost_limit():
                logger.warning("Daily cost limit reached, falling back to on-device model")
                selected_model = ModelType.GEMMA_ON_DEVICE
            
            # Execute the task
            response = await self._execute_with_model(selected_model, prompt, complexity)
            
            # Update metrics
            await self._update_metrics(selected_model, response)
            
            # Log the interaction
            logger.info(f"Task executed: {task_type} -> {selected_model} -> {response.response_time_ms:.1f}ms")
            
            return response
            
        except Exception as e:
            logger.error(f"Orchestrator execution failed: {e}")
            
            # Emergency fallback
            return ModelResponse(
                content="I apologize, but I'm experiencing technical difficulties. Please try again in a moment.",
                model_used=ModelType.GEMMA_ON_DEVICE,
                response_time_ms=0,
                error=str(e)
            )
    
    def _analyze_task_complexity(self, prompt: str, task_type: str) -> TaskComplexity:
        """Analyze the complexity of a given task."""
        prompt_lower = prompt.lower()
        
        # Check for critical keywords first
        for keyword in self.complexity_keywords[TaskComplexity.CRITICAL]:
            if keyword in prompt_lower:
                return TaskComplexity.CRITICAL
        
        # Check task type patterns
        if task_type in ["curriculum_generation", "complex_analysis", "research"]:
            return TaskComplexity.COMPLEX
        
        # Check for complex keywords
        complex_count = sum(1 for keyword in self.complexity_keywords[TaskComplexity.COMPLEX] 
                          if keyword in prompt_lower)
        if complex_count >= 2:
            return TaskComplexity.COMPLEX
        
        # Check for medium keywords
        medium_count = sum(1 for keyword in self.complexity_keywords[TaskComplexity.MEDIUM] 
                          if keyword in prompt_lower)
        if medium_count >= 1:
            return TaskComplexity.MEDIUM
        
        # Check prompt length
        if len(prompt.split()) > 50:
            return TaskComplexity.MEDIUM
        
        return TaskComplexity.SIMPLE
    
    def _select_model(self, complexity: TaskComplexity, task_type: str, user_context: Optional[Dict]) -> ModelType:
        """Select the most appropriate model based on various factors."""
        
        # Complex tasks always go to cloud
        if complexity in [TaskComplexity.COMPLEX, TaskComplexity.CRITICAL]:
            return ModelType.CLOUD_LLM
        
        # Check user preferences
        if user_context and user_context.get("preferred_model"):
            return ModelType(user_context["preferred_model"])
        
        # Medium complexity: consider model performance
        if complexity == TaskComplexity.MEDIUM:
            cloud_metrics = self.model_metrics[ModelType.CLOUD_LLM]
            if cloud_metrics.successful_requests > 0:
                success_rate = cloud_metrics.successful_requests / cloud_metrics.total_requests
                if success_rate > 0.9:  # High success rate, use cloud
                    return ModelType.CLOUD_LLM
        
        # Default to on-device for simple tasks
        return ModelType.GEMMA_ON_DEVICE
    
    def _is_circuit_breaker_open(self, model_type: ModelType) -> bool:
        """Check if circuit breaker is open for a given model."""
        metrics = self.model_metrics[model_type]
        
        if not metrics.circuit_breaker_open:
            return False
        
        # Check if timeout has passed
        if metrics.last_failure:
            time_since_failure = datetime.utcnow() - metrics.last_failure
            if time_since_failure.total_seconds() > self.circuit_breaker_timeout:
                metrics.circuit_breaker_open = False
                logger.info(f"Circuit breaker reset for {model_type}")
                return False
        
        return True
    
    def _get_fallback_model(self, failed_model: ModelType) -> ModelType:
        """Get fallback model when primary model fails."""
        if failed_model == ModelType.CLOUD_LLM:
            return ModelType.GEMMA_ON_DEVICE
        else:
            # If on-device fails, we have no fallback (could add another cloud provider)
            return ModelType.GEMMA_ON_DEVICE
    
    def _is_within_cost_limit(self) -> bool:
        """Check if we're within daily cost limits."""
        current_date = datetime.utcnow().date()
        
        # Reset daily cost if new day
        if current_date > self.cost_reset_date:
            self.current_daily_cost = 0.0
            self.cost_reset_date = current_date
        
        return self.current_daily_cost < self.daily_cost_limit
    
    async def _execute_with_model(self, model_type: ModelType, prompt: str, complexity: TaskComplexity) -> ModelResponse:
        """Execute task with specified model."""
        
        # Adjust parameters based on complexity
        max_tokens = {
            TaskComplexity.SIMPLE: 100,
            TaskComplexity.MEDIUM: 200,
            TaskComplexity.COMPLEX: 400,
            TaskComplexity.CRITICAL: 500
        }.get(complexity, 200)
        
        temperature = {
            TaskComplexity.SIMPLE: 0.5,
            TaskComplexity.MEDIUM: 0.7,
            TaskComplexity.COMPLEX: 0.8,
            TaskComplexity.CRITICAL: 0.6  # More focused for critical tasks
        }.get(complexity, 0.7)
        
        if model_type == ModelType.CLOUD_LLM:
            return await self.cloud_client.generate(prompt, max_tokens, temperature)
        else:
            return await self.on_device_client.generate(prompt, max_tokens, temperature)
    
    async def _update_metrics(self, model_type: ModelType, response: ModelResponse) -> None:
        """Update performance metrics for a model."""
        metrics = self.model_metrics[model_type]
        
        metrics.total_requests += 1
        
        if response.error:
            metrics.failed_requests += 1
            metrics.last_failure = datetime.utcnow()
            
            # Check circuit breaker threshold
            if metrics.failed_requests >= self.circuit_breaker_threshold:
                total_requests = metrics.total_requests
                if total_requests >= self.circuit_breaker_threshold:
                    failure_rate = metrics.failed_requests / total_requests
                    if failure_rate > 0.5:  # More than 50% failure rate
                        metrics.circuit_breaker_open = True
                        logger.warning(f"Circuit breaker opened for {model_type}")
        else:
            metrics.successful_requests += 1
            
            # Update average response time
            total_successful = metrics.successful_requests
            current_avg = metrics.average_response_time
            new_avg = ((current_avg * (total_successful - 1)) + response.response_time_ms) / total_successful
            metrics.average_response_time = new_avg
            
            # Update cost tracking
            if response.cost_estimate:
                metrics.total_cost += response.cost_estimate
                self.current_daily_cost += response.cost_estimate
            
            # Update token tracking
            if response.tokens_used:
                metrics.total_tokens += response.tokens_used
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        stats = {
            "daily_cost": {
                "current": self.current_daily_cost,
                "limit": self.daily_cost_limit,
                "percentage_used": (self.current_daily_cost / self.daily_cost_limit) * 100
            },
            "models": {}
        }
        
        for model_type, metrics in self.model_metrics.items():
            success_rate = 0
            if metrics.total_requests > 0:
                success_rate = (metrics.successful_requests / metrics.total_requests) * 100
            
            stats["models"][model_type.value] = {
                "total_requests": metrics.total_requests,
                "successful_requests": metrics.successful_requests,
                "failed_requests": metrics.failed_requests,
                "success_rate_percent": success_rate,
                "average_response_time_ms": metrics.average_response_time,
                "total_tokens": metrics.total_tokens,
                "total_cost": metrics.total_cost,
                "circuit_breaker_open": metrics.circuit_breaker_open,
                "last_failure": metrics.last_failure.isoformat() if metrics.last_failure else None
            }
        
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all AI models."""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "models": {}
        }
        
        # Test on-device model
        try:
            test_response = await self.on_device_client.generate("test", max_tokens=10)
            health_status["models"]["gemma_on_device"] = {
                "status": "healthy" if not test_response.error else "unhealthy",
                "response_time_ms": test_response.response_time_ms,
                "error": test_response.error
            }
        except Exception as e:
            health_status["models"]["gemma_on_device"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Test cloud model (if API key available)
        if self.cloud_client.api_key:
            try:
                test_response = await self.cloud_client.generate("test", max_tokens=10)
                health_status["models"]["cloud_llm"] = {
                    "status": "healthy" if not test_response.error else "unhealthy",
                    "response_time_ms": test_response.response_time_ms,
                    "error": test_response.error
                }
            except Exception as e:
                health_status["models"]["cloud_llm"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
        else:
            health_status["models"]["cloud_llm"] = {
                "status": "not_configured",
                "error": "API key not provided"
            }
        
        # Determine overall status
        model_statuses = [model["status"] for model in health_status["models"].values()]
        if all(status == "unhealthy" for status in model_statuses):
            health_status["status"] = "critical"
        elif any(status == "unhealthy" for status in model_statuses):
            health_status["status"] = "degraded"
        
        return health_status


# Global orchestrator instance for dependency injection
ai_orchestrator = AIOrchestrator()
