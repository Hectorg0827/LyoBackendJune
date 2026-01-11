"""
A2A Base Agent - Foundation class for all A2A-compliant agents.

Extends the existing BaseAgent with A2A protocol support:
- AgentCard self-description
- TaskInput/TaskOutput handling
- Artifact production
- Streaming event emission
- Inter-agent communication

MIT Architecture Engineering - A2A Base Agent
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TypeVar, Generic, Type, Optional, Dict, Any, List, AsyncGenerator

import google.generativeai as genai
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type
)

from lyo_app.core.config import settings
from lyo_app.ai_agents.multi_agent_v2.model_manager import (
    ModelManager, 
    ModelConfig,
    ModelTier,
    TaskComplexity
)
from .schemas import (
    AgentCard,
    AgentCapability,
    AgentSkill,
    TaskInput,
    TaskOutput,
    TaskStatus,
    Artifact,
    ArtifactType,
    StreamingEvent,
    EventType,
    A2AMessage,
    MessageRole,
)

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class A2AAgentMetrics:
    """Track agent performance metrics with A2A-specific fields"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.total_tasks = 0
        self.successful_tasks = 0
        self.failed_tasks = 0
        self.total_tokens = 0
        self.total_time_seconds = 0.0
        self.artifacts_created = 0
        self.handoffs_sent = 0
        self.handoffs_received = 0
        self.call_history: List[Dict[str, Any]] = []
    
    def record_task(
        self, 
        success: bool, 
        tokens: int, 
        time_seconds: float,
        artifacts_count: int = 0,
        error: str = None
    ):
        self.total_tasks += 1
        if success:
            self.successful_tasks += 1
        else:
            self.failed_tasks += 1
        self.total_tokens += tokens
        self.total_time_seconds += time_seconds
        self.artifacts_created += artifacts_count
        
        self.call_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "success": success,
            "tokens": tokens,
            "time_seconds": time_seconds,
            "artifacts": artifacts_count,
            "error": error
        })
        if len(self.call_history) > 20:
            self.call_history.pop(0)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_tasks": self.total_tasks,
            "success_rate": self.successful_tasks / max(self.total_tasks, 1),
            "total_tokens": self.total_tokens,
            "avg_time_seconds": self.total_time_seconds / max(self.total_tasks, 1),
            "artifacts_created": self.artifacts_created,
            "handoffs_sent": self.handoffs_sent,
            "handoffs_received": self.handoffs_received,
        }


class A2ABaseAgent(ABC, Generic[T]):
    """
    A2A-compliant base agent class.
    
    Implements Google's A2A protocol with:
    - Self-describing AgentCard
    - Standardized task handling
    - Artifact production
    - Streaming support
    - Inter-agent communication
    
    All agents in the pipeline inherit from this class.
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        output_schema: Type[T],
        capabilities: List[AgentCapability],
        skills: Optional[List[AgentSkill]] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
        timeout_seconds: float = 120.0,
        force_model_tier: Optional[ModelTier] = None
    ):
        self.name = name
        self.description = description
        self.output_schema = output_schema
        self.capabilities = capabilities
        self.skills = skills or []
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.metrics = A2AAgentMetrics(name)
        
        # Get model configuration
        if force_model_tier:
            model_config = ModelManager.MODELS[force_model_tier]
        else:
            model_config = ModelManager.get_model_for_task(name)
        
        self.model_name = model_name or model_config.model_name
        self.temperature = temperature if temperature is not None else model_config.temperature
        self.max_tokens = max_tokens or model_config.max_tokens
        
        logger.info(f"A2A Agent '{name}' initialized with model: {self.model_name}")
        
        # Initialize Gemini
        api_key = getattr(settings, 'google_api_key', None) or getattr(settings, 'gemini_api_key', None)
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(
                self.model_name,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                    "response_mime_type": "application/json"
                }
            )
            self._available = True
        else:
            logger.warning(f"A2A Agent {name}: No API key, agent unavailable")
            self._available = False
            self.model = None
        
        # Build agent card
        self._agent_card = self._build_agent_card()
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    @property
    def agent_card(self) -> AgentCard:
        return self._agent_card
    
    def _build_agent_card(self) -> AgentCard:
        """Build the self-describing agent card"""
        return AgentCard(
            name=self.name,
            description=self.description,
            version="1.0.0",
            capabilities=self.capabilities,
            skills=self.skills,
            model_name=self.model_name,
            model_provider="google",
            streaming_supported=True,
            a2a_version="0.1.0"
        )
    
    # ============================================================
    # ABSTRACT METHODS (Must be implemented by subclasses)
    # ============================================================
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent"""
        pass
    
    @abstractmethod
    def build_prompt(self, task_input: TaskInput, **kwargs) -> str:
        """Build the prompt from task input"""
        pass
    
    @abstractmethod
    def get_output_artifact_type(self) -> ArtifactType:
        """Return the type of artifact this agent produces"""
        pass
    
    # ============================================================
    # TASK EXECUTION
    # ============================================================
    
    async def execute(
        self,
        task_input: TaskInput,
        emit_event: Optional[callable] = None,
        **kwargs
    ) -> TaskOutput:
        """
        Execute a task with full A2A protocol support.
        
        Args:
            task_input: Standardized task input
            emit_event: Optional callback for streaming events
            **kwargs: Additional arguments for prompt building
            
        Returns:
            TaskOutput with results and artifacts
        """
        start_time = datetime.utcnow()
        tokens_used = 0
        
        # Emit task started event
        if emit_event:
            await emit_event(StreamingEvent(
                event_type=EventType.TASK_STARTED,
                task_id=task_input.task_id,
                agent_name=self.name,
                message=f"Agent {self.name} starting task"
            ))
        
        try:
            # Build prompt
            prompt = self.build_prompt(task_input, **kwargs)
            system_prompt = self.get_system_prompt()
            
            # Emit thinking event if requested
            if task_input.include_thinking and emit_event:
                await emit_event(StreamingEvent(
                    event_type=EventType.THINKING,
                    task_id=task_input.task_id,
                    agent_name=self.name,
                    thinking_content=f"Processing request: {task_input.user_message[:100]}..."
                ))
            
            # Execute with retries
            result = await self._execute_with_retry(
                system_prompt=system_prompt,
                prompt=prompt,
                task_input=task_input,
                emit_event=emit_event
            )
            
            if result is None:
                raise ValueError("Agent returned no result")
            
            tokens_used = getattr(result, '_tokens_used', 0)
            
            # Create artifact from result
            artifact = Artifact(
                type=self.get_output_artifact_type(),
                name=f"{self.name}_output",
                description=f"Output from {self.name}",
                data=result.model_dump() if hasattr(result, 'model_dump') else result,
                created_by=self.name
            )
            
            # Emit artifact created event
            if emit_event:
                await emit_event(StreamingEvent(
                    event_type=EventType.ARTIFACT_CREATED,
                    task_id=task_input.task_id,
                    agent_name=self.name,
                    artifact=artifact,
                    message=f"Created artifact: {artifact.name}"
                ))
            
            # Calculate duration
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            # Record metrics
            self.metrics.record_task(
                success=True,
                tokens=tokens_used,
                time_seconds=duration,
                artifacts_count=1
            )
            
            # Emit completion event
            if emit_event:
                await emit_event(StreamingEvent(
                    event_type=EventType.TASK_COMPLETED,
                    task_id=task_input.task_id,
                    agent_name=self.name,
                    progress_percent=100,
                    message=f"Agent {self.name} completed successfully"
                ))
            
            return TaskOutput(
                task_id=task_input.task_id,
                status=TaskStatus.COMPLETED,
                response_message=f"Successfully generated {self.get_output_artifact_type().value}",
                output_artifacts=[artifact],
                started_at=start_time,
                completed_at=end_time,
                duration_seconds=duration,
                tokens_used=tokens_used,
                agents_involved=[self.name]
            )
            
        except Exception as e:
            logger.error(f"A2A Agent {self.name} failed: {e}")
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            self.metrics.record_task(
                success=False,
                tokens=tokens_used,
                time_seconds=duration,
                error=str(e)
            )
            
            if emit_event:
                await emit_event(StreamingEvent(
                    event_type=EventType.TASK_FAILED,
                    task_id=task_input.task_id,
                    agent_name=self.name,
                    error=str(e),
                    message=f"Agent {self.name} failed: {e}"
                ))
            
            return TaskOutput(
                task_id=task_input.task_id,
                status=TaskStatus.FAILED,
                error_message=str(e),
                started_at=start_time,
                completed_at=end_time,
                duration_seconds=duration,
                agents_involved=[self.name]
            )
    
    async def _execute_with_retry(
        self,
        system_prompt: str,
        prompt: str,
        task_input: TaskInput,
        emit_event: Optional[callable] = None
    ) -> T:
        """Execute with exponential backoff retry"""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                if emit_event and attempt > 0:
                    await emit_event(StreamingEvent(
                        event_type=EventType.TASK_PROGRESS,
                        task_id=task_input.task_id,
                        agent_name=self.name,
                        message=f"Retry attempt {attempt + 1}/{self.max_retries}"
                    ))
                
                # Call the model
                full_prompt = f"{system_prompt}\n\n{prompt}"
                
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.model.generate_content,
                        full_prompt
                    ),
                    timeout=self.timeout_seconds
                )
                
                # Extract JSON from response
                raw_text = response.text.strip()
                
                # Clean markdown code blocks if present
                if raw_text.startswith("```"):
                    lines = raw_text.split("\n")
                    raw_text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
                
                # Parse and validate
                try:
                    data = json.loads(raw_text)
                    
                    # Handle wrapped responses (e.g., {"pedagogy_output": {...}})
                    # Check if data is a single-key dict containing the actual output
                    if isinstance(data, dict) and len(data) == 1:
                        single_key = list(data.keys())[0]
                        inner_data = data[single_key]
                        # If the inner data has required fields, use it
                        if isinstance(inner_data, dict):
                            try:
                                result = self.output_schema.model_validate(inner_data)
                                if hasattr(response, 'usage_metadata'):
                                    result._tokens_used = getattr(response.usage_metadata, 'total_token_count', 0)
                                return result
                            except ValidationError:
                                pass  # Fall through to try original data
                    
                    result = self.output_schema.model_validate(data)
                    
                    # Store token count if available
                    if hasattr(response, 'usage_metadata'):
                        result._tokens_used = getattr(response.usage_metadata, 'total_token_count', 0)
                    
                    return result
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON decode error: {e}")
                    last_error = e
                    continue
                    
                except ValidationError as e:
                    logger.warning(f"Validation error: {e}")
                    last_error = e
                    continue
                    
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Agent {self.name} timed out")
                logger.warning(f"Timeout on attempt {attempt + 1}")
                
            except Exception as e:
                last_error = e
                logger.warning(f"Error on attempt {attempt + 1}: {e}")
            
            # Exponential backoff
            if attempt < self.max_retries - 1:
                delay = 2 ** attempt
                await asyncio.sleep(delay)
        
        raise last_error or Exception("Max retries exceeded")
    
    # ============================================================
    # STREAMING SUPPORT
    # ============================================================
    
    async def execute_streaming(
        self,
        task_input: TaskInput,
        **kwargs
    ) -> AsyncGenerator[StreamingEvent, None]:
        """
        Execute task with streaming events.
        
        Yields StreamingEvent objects that can be sent via SSE.
        """
        events = []
        
        async def capture_event(event: StreamingEvent):
            events.append(event)
        
        # Start execution in background
        task = asyncio.create_task(
            self.execute(task_input, emit_event=capture_event, **kwargs)
        )
        
        # Yield events as they come
        while not task.done() or events:
            if events:
                yield events.pop(0)
            else:
                await asyncio.sleep(0.1)
        
        # Yield any remaining events
        for event in events:
            yield event
        
        # Get result (may raise exception)
        await task
    
    # ============================================================
    # UTILITY METHODS
    # ============================================================
    
    def get_artifact(
        self,
        artifacts: List[Artifact],
        artifact_type: ArtifactType
    ) -> Optional[Artifact]:
        """Get an artifact of a specific type from a list"""
        for artifact in artifacts:
            if artifact.type == artifact_type:
                return artifact
        return None
    
    def extract_artifact_data(
        self,
        artifacts: List[Artifact],
        artifact_type: ArtifactType
    ) -> Optional[Dict[str, Any]]:
        """Extract data from an artifact"""
        artifact = self.get_artifact(artifacts, artifact_type)
        if artifact and artifact.data:
            return artifact.data
        return None
    
    def format_conversation_history(
        self,
        messages: List[A2AMessage]
    ) -> str:
        """Format conversation history for prompt"""
        if not messages:
            return ""
        
        formatted = []
        for msg in messages[-10:]:  # Last 10 messages
            role = msg.role.value.upper()
            formatted.append(f"[{role}]: {msg.content}")
        
        return "\n".join(formatted)
    
    def create_message(
        self,
        content: str,
        thinking: Optional[str] = None
    ) -> A2AMessage:
        """Create a message from this agent"""
        return A2AMessage(
            role=MessageRole.AGENT,
            content=content,
            agent_name=self.name,
            thinking=thinking
        )
