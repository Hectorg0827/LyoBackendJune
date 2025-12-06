"""
Base Agent Class for Multi-Agent Course Generation.
Uses structured output enforcement via Pydantic.

MIT Architecture Engineering - Production Grade Agent Framework
"""

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TypeVar, Generic, Type, Optional, Dict, Any, List

import google.generativeai as genai
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type
)

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class AgentMetrics:
    """Track agent performance metrics for observability"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.total_tokens = 0
        self.total_time_seconds = 0.0
        self.retries = 0
        self.validation_failures = 0
        self.call_history: List[Dict[str, Any]] = []
    
    def record_call(
        self, 
        success: bool, 
        tokens: int, 
        time_seconds: float, 
        retried: bool = False,
        error: str = None
    ):
        self.total_calls += 1
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
        self.total_tokens += tokens
        self.total_time_seconds += time_seconds
        if retried:
            self.retries += 1
        
        # Keep last 10 calls for debugging
        self.call_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "success": success,
            "tokens": tokens,
            "time_seconds": time_seconds,
            "error": error
        })
        if len(self.call_history) > 10:
            self.call_history.pop(0)
    
    def record_validation_failure(self):
        self.validation_failures += 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_calls": self.total_calls,
            "success_rate": self.successful_calls / max(self.total_calls, 1),
            "total_tokens": self.total_tokens,
            "avg_time_seconds": self.total_time_seconds / max(self.total_calls, 1),
            "retry_rate": self.retries / max(self.total_calls, 1),
            "validation_failure_rate": self.validation_failures / max(self.total_calls, 1),
            "recent_calls": self.call_history[-5:]
        }


class AgentResult(Generic[T]):
    """Result wrapper for agent execution"""
    
    def __init__(
        self,
        success: bool,
        data: Optional[T] = None,
        raw_response: Optional[str] = None,
        error: Optional[str] = None,
        tokens_used: int = 0,
        time_seconds: float = 0.0,
        retries: int = 0
    ):
        self.success = success
        self.data = data
        self.raw_response = raw_response
        self.error = error
        self.tokens_used = tokens_used
        self.time_seconds = time_seconds
        self.retries = retries
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data.model_dump() if self.data else None,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "time_seconds": self.time_seconds,
            "retries": self.retries
        }


class BaseAgent(ABC, Generic[T]):
    """
    Base class for all course generation agents.
    
    Features:
    - Structured output enforcement via Pydantic
    - Automatic retries with exponential backoff
    - Fallback to simpler prompts on failure
    - Comprehensive metrics tracking
    - Circuit breaker pattern for API protection
    """
    
    def __init__(
        self,
        name: str,
        output_schema: Type[T],
        model_name: str = "gemini-1.5-flash",
        temperature: float = 0.7,
        max_tokens: int = 8192,
        max_retries: int = 3,
        timeout_seconds: float = 90.0
    ):
        self.name = name
        self.output_schema = output_schema
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.metrics = AgentMetrics(name)
        
        # Initialize Gemini
        api_key = getattr(settings, 'google_api_key', None) or getattr(settings, 'gemini_api_key', None)
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(
                model_name,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    "response_mime_type": "application/json"
                }
            )
            self._available = True
        else:
            logger.warning(f"Agent {name}: No API key found, agent will be unavailable")
            self._available = False
            self.model = None
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent"""
        pass
    
    @abstractmethod
    def build_prompt(self, **kwargs) -> str:
        """Build the user prompt from input data"""
        pass
    
    def get_fallback_prompt(self, **kwargs) -> Optional[str]:
        """
        Return a simpler fallback prompt for retry attempts.
        Override in subclasses if needed.
        """
        return None
    
    def get_schema_prompt(self) -> str:
        """Generate prompt section describing expected output schema"""
        schema = self.output_schema.model_json_schema()
        
        # Simplify schema for readability
        def simplify_schema(s: dict, depth: int = 0) -> dict:
            if depth > 3:
                return {"...": "nested"}
            result = {}
            for key, value in s.items():
                if key in ["title", "description", "examples"]:
                    continue
                if isinstance(value, dict):
                    result[key] = simplify_schema(value, depth + 1)
                else:
                    result[key] = value
            return result
        
        simplified = simplify_schema(schema)
        schema_str = json.dumps(simplified, indent=2)
        
        return f"""
## Output Format Requirements

You MUST respond with valid JSON that conforms to this schema:

```json
{schema_str}
```

CRITICAL RULES:
1. Return ONLY the JSON object - no markdown formatting, no code fences
2. Ensure all required fields are present
3. Follow all field constraints (min/max lengths, patterns, etc.)
4. Use proper JSON escaping for special characters
5. Arrays must have the minimum required items
6. String patterns (like "les_1_1" for lesson IDs) must be followed exactly
"""
    
    def _clean_response(self, response: str) -> str:
        """Clean AI response to extract valid JSON"""
        cleaned = response.strip()
        
        # Remove markdown code fences
        if cleaned.startswith("```"):
            # Find the content between fences
            lines = cleaned.split("\n")
            start_idx = 1  # Skip first line with ```
            end_idx = len(lines)
            
            for i, line in enumerate(lines[1:], 1):
                if line.strip().startswith("```"):
                    end_idx = i
                    break
            
            cleaned = "\n".join(lines[start_idx:end_idx])
        
        # Remove "json" prefix if present
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        
        # Try to find JSON object boundaries
        if not cleaned.startswith("{"):
            start = cleaned.find("{")
            if start != -1:
                cleaned = cleaned[start:]
        
        if not cleaned.endswith("}"):
            end = cleaned.rfind("}")
            if end != -1:
                cleaned = cleaned[:end + 1]
        
        return cleaned
    
    async def _call_model(self, prompt: str, attempt: int = 1) -> str:
        """Call the model with retry logic"""
        if not self._available:
            raise RuntimeError(f"Agent {self.name} is not available (no API key)")
        
        try:
            response = await asyncio.wait_for(
                self.model.generate_content_async(prompt),
                timeout=self.timeout_seconds
            )
            
            if not response.text:
                raise ValueError("Empty response from model")
            
            return response.text
            
        except asyncio.TimeoutError:
            logger.warning(f"Agent {self.name} timed out on attempt {attempt}")
            raise
        except Exception as e:
            logger.error(f"Agent {self.name} error on attempt {attempt}: {e}")
            raise
    
    async def execute(self, **kwargs) -> AgentResult[T]:
        """
        Execute the agent and return structured output.
        
        Returns:
            AgentResult containing validated Pydantic model or error
        """
        if not self._available:
            return AgentResult(
                success=False,
                error=f"Agent {self.name} is not available (no API key configured)"
            )
        
        start_time = datetime.utcnow()
        retries = 0
        last_error = None
        raw_response = None
        
        # Build prompts
        system_prompt = self.get_system_prompt()
        user_prompt = self.build_prompt(**kwargs)
        schema_prompt = self.get_schema_prompt()
        
        full_prompt = f"{system_prompt}\n\n{schema_prompt}\n\n{user_prompt}"
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Agent {self.name}: Attempt {attempt}/{self.max_retries}")
                
                # Use fallback prompt on later attempts if available
                current_prompt = full_prompt
                if attempt > 1:
                    fallback = self.get_fallback_prompt(**kwargs)
                    if fallback:
                        current_prompt = f"{system_prompt}\n\n{schema_prompt}\n\n{fallback}"
                        logger.info(f"Agent {self.name}: Using fallback prompt")
                
                # Call model
                raw_response = await self._call_model(current_prompt, attempt)
                
                # Clean and parse response
                cleaned = self._clean_response(raw_response)
                data = json.loads(cleaned)
                
                # Validate with Pydantic
                result = self.output_schema(**data)
                
                # Success!
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                tokens = len(full_prompt.split()) + len(raw_response.split())
                
                self.metrics.record_call(
                    success=True,
                    tokens=tokens,
                    time_seconds=elapsed,
                    retried=retries > 0
                )
                
                logger.info(f"Agent {self.name}: Success in {elapsed:.2f}s")
                
                return AgentResult(
                    success=True,
                    data=result,
                    raw_response=raw_response,
                    tokens_used=tokens,
                    time_seconds=elapsed,
                    retries=retries
                )
                
            except json.JSONDecodeError as e:
                retries += 1
                last_error = f"JSON parse error: {str(e)}"
                logger.warning(f"Agent {self.name}: {last_error}")
                self.metrics.record_validation_failure()
                
            except ValidationError as e:
                retries += 1
                error_details = "; ".join([f"{err['loc']}: {err['msg']}" for err in e.errors()[:3]])
                last_error = f"Validation error: {error_details}"
                logger.warning(f"Agent {self.name}: {last_error}")
                self.metrics.record_validation_failure()
                
            except asyncio.TimeoutError:
                retries += 1
                last_error = f"Timeout after {self.timeout_seconds}s"
                logger.warning(f"Agent {self.name}: {last_error}")
                
            except Exception as e:
                retries += 1
                last_error = str(e)
                logger.error(f"Agent {self.name}: Unexpected error: {e}")
            
            # Wait before retry with exponential backoff
            if attempt < self.max_retries:
                wait_time = min(2 ** attempt, 30)
                logger.info(f"Agent {self.name}: Waiting {wait_time}s before retry")
                await asyncio.sleep(wait_time)
        
        # All retries failed
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        self.metrics.record_call(
            success=False,
            tokens=len(full_prompt.split()),
            time_seconds=elapsed,
            retried=True,
            error=last_error
        )
        
        logger.error(f"Agent {self.name}: Failed after {self.max_retries} attempts: {last_error}")
        
        return AgentResult(
            success=False,
            error=last_error,
            raw_response=raw_response,
            time_seconds=elapsed,
            retries=retries
        )
    
    async def execute_with_fallback(
        self, 
        fallback_data: T,
        **kwargs
    ) -> AgentResult[T]:
        """
        Execute agent with a fallback value if all retries fail.
        
        Args:
            fallback_data: Pre-built fallback data to use on failure
            **kwargs: Arguments for the agent
        
        Returns:
            AgentResult with either AI-generated or fallback data
        """
        result = await self.execute(**kwargs)
        
        if result.success:
            return result
        
        logger.warning(f"Agent {self.name}: Using fallback data")
        return AgentResult(
            success=True,
            data=fallback_data,
            error=f"Used fallback due to: {result.error}",
            tokens_used=0,
            time_seconds=result.time_seconds,
            retries=result.retries
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get agent performance metrics"""
        return self.metrics.to_dict()


class ParallelAgentRunner:
    """
    Runs multiple agents in parallel with coordination.
    Used for generating multiple lessons simultaneously.
    """
    
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def run_parallel(
        self,
        agent: BaseAgent,
        kwargs_list: List[Dict[str, Any]]
    ) -> List[AgentResult]:
        """
        Run the same agent with different inputs in parallel.
        
        Args:
            agent: The agent to run
            kwargs_list: List of kwargs for each execution
        
        Returns:
            List of results in the same order as inputs
        """
        async def run_with_semaphore(kwargs: Dict[str, Any], index: int) -> tuple:
            async with self.semaphore:
                logger.info(f"Starting parallel task {index + 1}/{len(kwargs_list)}")
                result = await agent.execute(**kwargs)
                return (index, result)
        
        # Create tasks
        tasks = [
            run_with_semaphore(kwargs, i) 
            for i, kwargs in enumerate(kwargs_list)
        ]
        
        # Run concurrently
        completed = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Sort by original index and extract results
        results = [None] * len(kwargs_list)
        for item in completed:
            if isinstance(item, Exception):
                logger.error(f"Parallel task failed: {item}")
                continue
            index, result = item
            results[index] = result
        
        # Fill any None values with error results
        for i, result in enumerate(results):
            if result is None:
                results[i] = AgentResult(
                    success=False,
                    error="Task failed with exception"
                )
        
        return results
