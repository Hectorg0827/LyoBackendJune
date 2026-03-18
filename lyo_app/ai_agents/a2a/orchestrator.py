"""
A2A Orchestrator - Multi-Agent Pipeline Coordinator.

The Conductor that coordinates all A2A agents to generate
complete cinematic courses through parallel and sequential
agent execution with intelligent handoffs.

Implements Google A2A protocol with:
- Agent discovery and capability matching
- Task routing and load balancing
- Streaming progress updates
- Error recovery and fallbacks
- Quality gates between phases
"""

import asyncio
import time
import uuid
from typing import Optional, Dict, Any, List, AsyncGenerator, Callable
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import json
import traceback
import logging

logger = logging.getLogger(__name__)

from .schemas import (
    AgentCard,
    TaskInput,
    TaskOutput,
    TaskStatus,
    Artifact,
    ArtifactType,
    StreamingEvent,
    EventType,
    A2ACourseRequest,
    A2ACourseResponse,
)
from .pedagogy_agent import PedagogyAgent, PedagogyOutput
from .cinematic_director_agent import CinematicDirectorAgent, CinematicOutput
from .qa_checker_agent import QACheckerAgent, QAOutput
from .visual_director_agent import VisualDirectorAgent, VisualDirectorOutput
from .voice_agent import VoiceAgent, VoiceAgentOutput
from .researcher_agent import ResearcherAgent, ResearcherOutput


# ============================================================
# ORCHESTRATOR SCHEMAS
# ============================================================

class PipelinePhase(str, Enum):
    """Phases of the A2A course generation pipeline"""
    INITIALIZATION = "initialization"
    RESEARCH = "research"
    PEDAGOGY = "pedagogy"
    CINEMATIC = "cinematic"
    VISUAL = "visual"
    VOICE = "voice"
    QA_CHECK = "qa_check"
    ASSEMBLY = "assembly"
    FINALIZATION = "finalization"


class PhaseStatus(str, Enum):
    """Status of a pipeline phase"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineConfig(BaseModel):
    """Configuration for the orchestrator pipeline"""
    # Phase toggles
    enable_pedagogy: bool = True
    enable_cinematic: bool = True
    enable_visual: bool = True
    enable_voice: bool = True
    enable_qa: bool = True
    
    # Quality gates
    min_qa_score: float = 0.7
    max_retries: int = 2
    
    # Parallelization
    parallel_visual_voice: bool = True
    
    # Timeouts (seconds)
    phase_timeout: float = 300.0
    total_timeout: float = 900.0  # 15 minutes max
    
    # Streaming
    enable_streaming: bool = True
    stream_interval_ms: int = 100


class PhaseResult(BaseModel):
    """Result of a single pipeline phase"""
    phase: PipelinePhase
    status: PhaseStatus
    agent_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0


class PipelineState(BaseModel):
    """Current state of the pipeline"""
    pipeline_id: str
    request: A2ACourseRequest
    config: PipelineConfig
    
    # Phase tracking
    current_phase: PipelinePhase
    phase_results: Dict[str, PhaseResult] = Field(default_factory=dict)
    
    # Timing
    started_at: datetime
    estimated_completion: Optional[datetime] = None
    
    # Progress
    overall_progress: float = 0.0
    
    # Final output
    final_output: Optional[Dict[str, Any]] = None
    final_status: TaskStatus = TaskStatus.PENDING


class AgentHandoff(BaseModel):
    """Record of handoff between agents"""
    from_agent: str
    to_agent: str
    artifact_type: ArtifactType
    timestamp: datetime
    data_size_bytes: int
    success: bool


# ============================================================
# A2A ORCHESTRATOR
# ============================================================

class A2AOrchestrator:
    """
    Multi-agent pipeline orchestrator following A2A protocol.
    
    Coordinates specialized agents through phases:
    1. INITIALIZATION - Setup and validation
    2. PEDAGOGY - Learning science analysis
    3. CINEMATIC - Story and scene design
    4. VISUAL - Image and diagram specs (parallel)
    5. VOICE - Audio and narration (parallel)
    6. QA_CHECK - Quality validation
    7. ASSEMBLY - Combine all artifacts
    8. FINALIZATION - Final packaging
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        
        # Initialize agents
        self.pedagogy_agent = PedagogyAgent()
        self.cinematic_agent = CinematicDirectorAgent()
        self.visual_agent = VisualDirectorAgent()
        self.voice_agent = VoiceAgent()
        self.qa_agent = QACheckerAgent()
        self.researcher_agent = ResearcherAgent()
        
        # Agent registry
        self._agents = {
            "researcher": self.researcher_agent,
            "pedagogy": self.pedagogy_agent,
            "cinematic_director": self.cinematic_agent,
            "visual_director": self.visual_agent,
            "voice_agent": self.voice_agent,
            "qa_checker": self.qa_agent,
        }
        
        # Pipeline state
        self._current_state: Optional[PipelineState] = None
        self._handoffs: List[AgentHandoff] = []
        
        # Progress weights for each phase
        self._phase_weights = {
            PipelinePhase.INITIALIZATION: 0.05,
            PipelinePhase.RESEARCH: 0.10,
            PipelinePhase.PEDAGOGY: 0.15,
            PipelinePhase.CINEMATIC: 0.20,
            PipelinePhase.VISUAL: 0.15,
            PipelinePhase.VOICE: 0.15,
            PipelinePhase.QA_CHECK: 0.10,
            PipelinePhase.ASSEMBLY: 0.05,
            PipelinePhase.FINALIZATION: 0.05,
        }
        
        # Redis client for state persistence
        from lyo_app.core.redis_client import redis_client
        self.redis = redis_client
    
    # ========================
    # PUBLIC API
    # ========================
    
    async def generate_course(
        self,
        request: A2ACourseRequest,
        config: Optional[PipelineConfig] = None
    ) -> A2ACourseResponse:
        """
        Generate a complete course through the A2A pipeline.
        
        Args:
            request: Course generation request
            config: Optional pipeline configuration
            
        Returns:
            Complete course with all artifacts
        """
        if config:
            self.config = config
        
        # Initialize pipeline state
        pipeline_id = f"pipeline_{uuid.uuid4().hex[:12]}"
        self._current_state = PipelineState(
            pipeline_id=pipeline_id,
            request=request,
            config=self.config,
            current_phase=PipelinePhase.INITIALIZATION,
            started_at=datetime.utcnow()
        )
        
        try:
            # Run pipeline phases
            await self._run_pipeline()
            
            # Build response
            return self._build_response()
            
        except Exception as e:
            self._current_state.final_status = TaskStatus.FAILED
            raise RuntimeError(f"Pipeline failed: {str(e)}") from e
    
    async def generate_course_streaming(
        self,
        request: A2ACourseRequest,
        config: Optional[PipelineConfig] = None
    ) -> AsyncGenerator[StreamingEvent, None]:
        """
        Generate course with streaming progress updates.
        
        Yields StreamingEvent objects for real-time UI updates.
        """
        if config:
            self.config = config
        
        # Initialize
        pipeline_id = f"pipeline_{uuid.uuid4().hex[:12]}"
        self._current_state = PipelineState(
            pipeline_id=pipeline_id,
            request=request,
            config=self.config,
            current_phase=PipelinePhase.INITIALIZATION,
            started_at=datetime.utcnow()
        )
        
        # Emit start event
        yield StreamingEvent(
            type=EventType.PIPELINE_STARTED,
            task_id=pipeline_id,
            agent_name="orchestrator",
            progress_percent=0,
            data={
                "topic": request.topic,
                "phases": [p.value for p in PipelinePhase],
            },
            message="Starting A2A course generation pipeline"
        )
        
        try:
            # Run each phase with streaming
            async for event in self._run_pipeline_streaming():
                yield event
            
            # Emit completion
            response = self._build_response()
            yield StreamingEvent(
                type=EventType.PIPELINE_COMPLETED,
                task_id=pipeline_id,
                agent_name="orchestrator",
                progress_percent=100,
                payload=response.model_dump(mode='json'),
                message="Course generation complete!"
            )
            
        except Exception as e:
            yield StreamingEvent(
                type=EventType.ERROR,
                task_id=pipeline_id,
                agent_name="orchestrator",
                data={"error": str(e), "traceback": traceback.format_exc()},
                message=f"Pipeline failed: {str(e)}"
            )
            raise
    
    def get_agent_cards(self) -> List[AgentCard]:
        """Get agent cards for all registered agents."""
        return [agent.agent_card for agent in self._agents.values()]
    
    def get_pipeline_state(self) -> Optional[PipelineState]:
        """Get current pipeline state."""
        return self._current_state
    
    # ========================
    # PIPELINE EXECUTION
    # ========================
    
    async def _run_pipeline(self) -> None:
        """Execute the full pipeline synchronously."""
        state = self._current_state
        
        # Phase 1: Initialization
        await self._run_phase(PipelinePhase.INITIALIZATION, self._initialize)
        
        # Phase 1.5: Research
        await self._run_phase(PipelinePhase.RESEARCH, self._run_research)
        
        # Phase 2: Pedagogy
        if self.config.enable_pedagogy:
            await self._run_phase(PipelinePhase.PEDAGOGY, self._run_pedagogy)
        
        # Phase 3: Cinematic
        if self.config.enable_cinematic:
            await self._run_phase(PipelinePhase.CINEMATIC, self._run_cinematic)
        
        # Phase 4 & 5: Visual + Voice (parallel if enabled)
        if self.config.parallel_visual_voice:
            await self._run_parallel_phases()
        else:
            if self.config.enable_visual:
                await self._run_phase(PipelinePhase.VISUAL, self._run_visual)
            if self.config.enable_voice:
                await self._run_phase(PipelinePhase.VOICE, self._run_voice)
        
        # Phase 6: QA Check
        if self.config.enable_qa:
            await self._run_phase(PipelinePhase.QA_CHECK, self._run_qa)
        
        # Phase 7: Assembly
        await self._run_phase(PipelinePhase.ASSEMBLY, self._assemble)
        
        # Phase 8: Finalization
        await self._run_phase(PipelinePhase.FINALIZATION, self._finalize)
        
        state.final_status = TaskStatus.COMPLETED
    
    async def _run_pipeline_streaming(self) -> AsyncGenerator[StreamingEvent, None]:
        """Execute pipeline with streaming events."""
        state = self._current_state
        # Phases to execute sequentially
        phases = [
            (PipelinePhase.INITIALIZATION, self._initialize, True),
            (PipelinePhase.RESEARCH, self._run_research, True),
            (PipelinePhase.PEDAGOGY, self._run_pedagogy, self.config.enable_pedagogy),
        ]
        
        # Sequential phases first
        for phase, executor, enabled in phases:
            if enabled:
                async for event in self._run_phase_streaming(phase, executor):
                    yield event
                    
        # Cinematic with Quality Gate (Phase 22)
        if self.config.enable_cinematic:
            async for event in self._run_phase_streaming(PipelinePhase.CINEMATIC, self._run_cinematic):
                yield event
            
            # Quality Gate for Cinematic
            if self.config.enable_qa and state.request.quality_tier != "fast":
                yield StreamingEvent(
                    type=EventType.PHASE_PROGRESS,
                    task_id=state.pipeline_id,
                    phase=PipelinePhase.QA_CHECK.value,
                    agent_name="qa_checker",
                    message="Performing quality assurance on cinematic structure..."
                )
                
                qa_result = await self._run_qa_for_phase(PipelinePhase.CINEMATIC)
                if qa_result.get("approval_status") == "needs_revision":
                    critical_issues = qa_result.get("issues", [])
                    feedback_str = "; ".join([i.get("description", "") for i in critical_issues])
                    
                    yield StreamingEvent(
                        type=EventType.PHASE_PROGRESS,
                        task_id=state.pipeline_id,
                        phase=PipelinePhase.CINEMATIC.value,
                        agent_name="orchestrator",
                        message=f"QA requested revisions: {feedback_str}. Regenerating..."
                    )
                    
                    # Rerun with feedback
                    async for event in self._run_phase_streaming(
                        PipelinePhase.CINEMATIC, 
                        lambda: self._run_cinematic(feedback=feedback_str)
                    ):
                        yield event
        
        # Parallel visual + voice
        if self.config.parallel_visual_voice and (self.config.enable_visual or self.config.enable_voice):
            async for event in self._run_parallel_streaming():
                yield event
        else:
            if self.config.enable_visual:
                async for event in self._run_phase_streaming(PipelinePhase.VISUAL, self._run_visual):
                    yield event
            if self.config.enable_voice:
                async for event in self._run_phase_streaming(PipelinePhase.VOICE, self._run_voice):
                    yield event
        
        # QA
        if self.config.enable_qa:
            async for event in self._run_phase_streaming(PipelinePhase.QA_CHECK, self._run_qa):
                yield event
        
        # Assembly and finalization
        async for event in self._run_phase_streaming(PipelinePhase.ASSEMBLY, self._assemble):
            yield event
        async for event in self._run_phase_streaming(PipelinePhase.FINALIZATION, self._finalize):
            yield event
        
        state = self._current_state
        state.final_status = TaskStatus.COMPLETED
    
    async def _run_phase(
        self,
        phase: PipelinePhase,
        executor: Callable,
    ) -> PhaseResult:
        """Run a single pipeline phase."""
        state = self._current_state
        state.current_phase = phase
        
        result = PhaseResult(
            phase=phase,
            status=PhaseStatus.RUNNING,
            agent_name=self._get_phase_agent(phase),
            started_at=datetime.utcnow()
        )
        state.phase_results[phase.value] = result
        
        try:
            output = await asyncio.wait_for(
                executor(),
                timeout=self.config.phase_timeout
            )
            
            result.status = PhaseStatus.COMPLETED
            result.output = output if isinstance(output, dict) else None
            result.completed_at = datetime.utcnow()
            result.duration_ms = int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            )
            
            # Update progress
            self._update_progress(phase)
            
        except asyncio.TimeoutError:
            result.status = PhaseStatus.FAILED
            result.error = f"Phase {phase.value} timed out"
            raise
        except Exception as e:
            result.status = PhaseStatus.FAILED
            result.error = str(e)
            raise
        finally:
            # Auto-persist state after every phase (success or failure)
            await self._save_state()
        
        return result
    
    async def _run_phase_streaming(
        self,
        phase: PipelinePhase,
        executor: Callable,
    ) -> AsyncGenerator[StreamingEvent, None]:
        """Run phase with streaming events."""
        state = self._current_state
        state.current_phase = phase
        agent_name = self._get_phase_agent(phase)
        
        # Emit phase start
        yield StreamingEvent(
            type=EventType.PHASE_STARTED,
            task_id=state.pipeline_id,
            phase=phase.value,
            agent_name=agent_name,
            progress_percent=int(state.overall_progress * 100),
            message=f"Starting {phase.value} phase..."
        )
        
        result = PhaseResult(
            phase=phase,
            status=PhaseStatus.RUNNING,
            agent_name=agent_name,
            started_at=datetime.utcnow()
        )
        state.phase_results[phase.value] = result
        
        try:
            # Run executor
            start_time = time.time()
            output = await asyncio.wait_for(
                executor(),
                timeout=self.config.phase_timeout
            )
            elapsed = time.time() - start_time
            
            result.status = PhaseStatus.COMPLETED
            result.output = output if isinstance(output, dict) else None
            result.completed_at = datetime.utcnow()
            result.duration_ms = int(elapsed * 1000)
            
            self._update_progress(phase)
            
            # Emit completion
            yield StreamingEvent(
                type=EventType.PHASE_COMPLETED,
                task_id=state.pipeline_id,
                phase=phase.value,
                agent_name=agent_name,
                progress_percent=int(state.overall_progress * 100),
                data={"duration_ms": result.duration_ms},
                message=f"Completed {phase.value} in {elapsed:.1f}s"
            )

            # 🌊 NEW: Emit ARTIFACT_CREATED for significant results
            if result.output and phase in [PipelinePhase.PEDAGOGY, PipelinePhase.CINEMATIC, PipelinePhase.VISUAL, PipelinePhase.VOICE]:
                artifact_type = self._phase_to_artifact_type(phase)
                artifact = Artifact(
                    type=artifact_type,
                    name=f"{phase.value}_output",
                    data=result.output,
                    created_by=agent_name
                )
                yield StreamingEvent(
                    type=EventType.ARTIFACT_CREATED,
                    task_id=state.pipeline_id,
                    phase=phase.value,
                    agent_name=agent_name,
                    artifact=artifact,
                    message=f"Generated {artifact_type.value} artifact"
                )
            
        except Exception as e:
            result.status = PhaseStatus.FAILED
            result.error = str(e)
            
            yield StreamingEvent(
                type=EventType.ERROR,
                task_id=state.pipeline_id,
                phase=phase.value,
                agent_name=agent_name,
                data={"error": str(e)},
                message=f"Phase {phase.value} failed: {str(e)}"
            )
            raise
    
    async def _run_parallel_phases(self) -> None:
        """Run visual and voice phases in parallel."""
        tasks = []
        
        if self.config.enable_visual:
            tasks.append(self._run_phase(PipelinePhase.VISUAL, self._run_visual))
        if self.config.enable_voice:
            tasks.append(self._run_phase(PipelinePhase.VOICE, self._run_voice))
        
        if tasks:
            await asyncio.gather(*tasks)
    
    async def _run_parallel_streaming(self) -> AsyncGenerator[StreamingEvent, None]:
        """Run visual and voice in parallel with merged streaming."""
        state = self._current_state
        
        yield StreamingEvent(
            type=EventType.PHASE_PROGRESS,
            task_id=state.pipeline_id,
            agent_name="orchestrator",
            progress_percent=int(state.overall_progress * 100),
            message="Running visual and voice generation in parallel..."
        )
        
        # Create tasks
        visual_task = None
        voice_task = None
        
        if self.config.enable_visual:
            visual_task = asyncio.create_task(self._run_visual())
        if self.config.enable_voice:
            voice_task = asyncio.create_task(self._run_voice())
        
        # Wait for both
        if visual_task and voice_task:
            visual_out, voice_out = await asyncio.gather(visual_task, voice_task)
        elif visual_task:
            visual_out = await visual_task
        elif voice_task:
            voice_out = await voice_task
        
        # Record results
        if visual_task:
            state.phase_results[PipelinePhase.VISUAL.value] = PhaseResult(
                phase=PipelinePhase.VISUAL,
                status=PhaseStatus.COMPLETED,
                agent_name="visual_director",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
        if voice_task:
            state.phase_results[PipelinePhase.VOICE.value] = PhaseResult(
                phase=PipelinePhase.VOICE,
                status=PhaseStatus.COMPLETED,
                agent_name="voice_agent",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
        
        self._update_progress(PipelinePhase.VISUAL)
        self._update_progress(PipelinePhase.VOICE)
        
        yield StreamingEvent(
            type=EventType.PHASE_PROGRESS,
            task_id=state.pipeline_id,
            agent_name="orchestrator",
            progress_percent=int(state.overall_progress * 100),
            message="Visual and voice generation complete!"
        )
    
    # ========================
    # PHASE EXECUTORS
    # ========================
    
    async def _initialize(self) -> Dict[str, Any]:
        """Initialize the pipeline."""
        state = self._current_state
        
        # Validate request
        if not state.request.topic:
            raise ValueError("Topic is required")
        
        # Estimate timeline
        estimated_minutes = 3 if self.config.parallel_visual_voice else 5
        state.estimated_completion = datetime.utcnow()
        
        return {
            "initialized": True,
            "topic": state.request.topic,
            "config": self.config.dict(),
            "estimated_minutes": estimated_minutes
        }
    
    async def _run_research(self) -> Dict[str, Any]:
        """Run research phase."""
        state = self._current_state
        
        task_input = TaskInput(
            task_id=f"{state.pipeline_id}_research",
            requesting_agent="orchestrator",
            user_message=state.request.topic,
            attachment_ids=state.request.attachment_ids,
            context={
                "user_level": state.request.difficulty,
                "language": state.request.language
            }
        )
        
        output = await self.researcher_agent.execute(task_input)
        
        # Record handoff
        self._record_handoff(
            from_agent="orchestrator",
            to_agent="researcher",
            artifact_type=ArtifactType.JSON_DATA
        )
        
        return output.dict() if hasattr(output, 'dict') else output
    
    async def _run_pedagogy(self) -> Dict[str, Any]:
        """Run pedagogy analysis phase."""
        state = self._current_state
        
        task_input = TaskInput(
            task_id=f"{state.pipeline_id}_pedagogy",
            requesting_agent="orchestrator",
            user_message=state.request.topic,
            context={
                "quality_tier": state.request.quality_tier,
                "user_level": state.request.user_context.get("level", "intermediate") if state.request.user_context else "intermediate"
            }
        )
        
        output = await self.pedagogy_agent.execute(task_input)
        
        # Record handoff
        self._record_handoff(
            from_agent="orchestrator",
            to_agent="pedagogy",
            artifact_type=ArtifactType.LEARNING_OBJECTIVES
        )
        
        return output.dict() if hasattr(output, 'dict') else output
    
    async def _run_cinematic(self, feedback: Optional[str] = None) -> Dict[str, Any]:
        """Run cinematic direction phase."""
        state = self._current_state
        
        # Get pedagogy output
        pedagogy_result = state.phase_results.get(PipelinePhase.PEDAGOGY.value)
        pedagogy_output = pedagogy_result.output if pedagogy_result else None
        
        task_input = TaskInput(
            task_id=f"{state.pipeline_id}_cinematic",
            requesting_agent="orchestrator",
            user_message=state.request.topic,
            context={
                "quality_tier": state.request.quality_tier,
                "teaching_style": state.request.user_context.get("style", "storytelling") if state.request.user_context else "storytelling"
            },
            input_artifacts=[
                Artifact(
                    type=ArtifactType.LEARNING_OBJECTIVES,
                    name="pedagogy_output",
                    data=pedagogy_output,
                    created_by="pedagogy"
                )
            ] if pedagogy_output else None
        )
        
        output = await self.cinematic_agent.execute(
            task_input,
            pedagogy_output=pedagogy_output,
            feedback=feedback
        )
        
        self._record_handoff(
            from_agent="pedagogy",
            to_agent="cinematic_director",
            artifact_type=ArtifactType.CINEMATIC_SCENE
        )
        
        return output.dict() if hasattr(output, 'dict') else output
    
    async def _run_visual(self) -> Dict[str, Any]:
        """Run visual direction phase."""
        state = self._current_state
        
        cinematic_result = state.phase_results.get(PipelinePhase.CINEMATIC.value)
        cinematic_output = cinematic_result.output if cinematic_result else None
        
        pedagogy_result = state.phase_results.get(PipelinePhase.PEDAGOGY.value)
        pedagogy_output = pedagogy_result.output if pedagogy_result else None
        
        task_input = TaskInput(
            task_id=f"{state.pipeline_id}_visual",
            requesting_agent="orchestrator",
            user_message=state.request.topic,
            context={"quality_tier": state.request.quality_tier}
        )
        
        output = await self.visual_agent.execute(
            task_input,
            cinematic_output=cinematic_output,
            pedagogy_output=pedagogy_output
        )
        
        self._record_handoff(
            from_agent="cinematic_director",
            to_agent="visual_director",
            artifact_type=ArtifactType.VISUAL_ASSETS
        )
        
        return output.dict() if hasattr(output, 'dict') else output
    
    async def _run_voice(self) -> Dict[str, Any]:
        """Run voice generation phase."""
        state = self._current_state
        
        cinematic_result = state.phase_results.get(PipelinePhase.CINEMATIC.value)
        cinematic_output = cinematic_result.output if cinematic_result else None
        
        pedagogy_result = state.phase_results.get(PipelinePhase.PEDAGOGY.value)
        pedagogy_output = pedagogy_result.output if pedagogy_result else None
        
        task_input = TaskInput(
            task_id=f"{state.pipeline_id}_voice",
            requesting_agent="orchestrator",
            user_message=state.request.topic,
            context={"quality_tier": state.request.quality_tier}
        )
        
        output = await self.voice_agent.execute(
            task_input,
            cinematic_output=cinematic_output,
            pedagogy_output=pedagogy_output
        )
        
        self._record_handoff(
            from_agent="cinematic_director",
            to_agent="voice_agent",
            artifact_type=ArtifactType.VOICE_SCRIPTS
        )
        
        return output.dict() if hasattr(output, 'dict') else output
    
    async def _run_qa(self) -> Dict[str, Any]:
        """Run QA validation phase."""
        state = self._current_state
        
        # Collect all outputs for QA
        all_outputs = {
            phase: result.output
            for phase, result in state.phase_results.items()
            if result.output
        }
        
        # For 'fast' tier: run a lightweight factual-only QA instead of skipping
        # entirely.  This catches critical errors (hallucinations, broken code)
        # while still reducing latency vs. the full review.
        from lyo_app.ai_agents.a2a.qa_checker_agent import ReviewScope
        if state.request.quality_tier == "fast":
            logger.info("[A2A Orchestrator] Fast tier: using lightweight factual-only QA.")
            review_scope = ReviewScope.FACTUAL_ONLY
        else:
            review_scope = ReviewScope.FULL

        task_input = TaskInput(
            task_id=f"{state.pipeline_id}_qa",
            requesting_agent="orchestrator",
            user_message=state.request.topic,
            context={
                "quality_tier": state.request.quality_tier,
                "phase_outputs": list(all_outputs.keys()),
            },
        )

        output = await self.qa_agent.execute(
            task_input,
            content_to_review=all_outputs,
            review_scope=review_scope,
        )

        # Extract typed QA output to access overall_quality_score
        typed_qa = self.qa_agent.get_typed_output(output)

        # Enforce quality gate on the score
        if typed_qa is not None and typed_qa.overall_quality_score < self.config.min_qa_score:
            raise ValueError(
                f"QA score {typed_qa.overall_quality_score:.2f} below minimum "
                f"{self.config.min_qa_score} (scope={review_scope.value})"
            )
        
        self._record_handoff(
            from_agent="visual_director",
            to_agent="qa_checker",
            artifact_type=ArtifactType.QA_REPORT
        )
        
        # Return the typed QA output as a dict (includes overall_quality_score)
        if typed_qa is not None:
            return typed_qa.model_dump()
        return output.model_dump() if hasattr(output, "model_dump") else (
            output.dict() if hasattr(output, "dict") else {}
        )

    async def _run_qa_for_phase(self, phase: PipelinePhase) -> Dict[str, Any]:
        """Run QA specifically for a single phase output."""
        state = self._current_state
        phase_output = state.phase_results.get(phase.value).output if state.phase_results.get(phase.value) else None

        if not phase_output:
            return {"approval_status": "approved", "issues": [], "overall_quality_score": 1.0}
            
        task_input = TaskInput(
            task_id=f"{state.pipeline_id}_qa_{phase.value}",
            requesting_agent="orchestrator",
            user_message=state.request.topic,
            context={"quality_tier": state.request.quality_tier}
        )
        
        output = await self.qa_agent.execute(
            task_input,
            content_to_review={phase.value: phase_output},
        )

        typed_qa = self.qa_agent.get_typed_output(output)
        if typed_qa is not None:
            return typed_qa.model_dump()
        return output.model_dump() if hasattr(output, "model_dump") else (
            output.dict() if hasattr(output, "dict") else {}
        )

    # ========================
    # PERSISTENCE & RECOVERY (Phase 17)
    # ========================

    async def _save_state(self) -> None:
        """Persist current pipeline state to Redis for resilience."""
        if not self._current_state:
            return
            
        try:
            key = f"a2a:pipeline:{self._current_state.pipeline_id}"
            # Use Pydantic model_dump for clean JSON serialization
            state_data = self._current_state.model_dump(mode='json')
            await self.redis.set(key, state_data, expire=3600 * 24) # 24h retention
            logger.info(f"💾 [ORCHESTRATOR] Persisted state for {self._current_state.pipeline_id}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to persist pipeline state: {e}")

    async def resume_pipeline(self, pipeline_id: str) -> bool:
        """Attempt to resume a pipeline from persisted state."""
        try:
            key = f"a2a:pipeline:{pipeline_id}"
            data = await self.redis.get(key)
            if not data:
                logger.error(f"❌ No state found for pipeline {pipeline_id}")
                return False
                
            self._current_state = PipelineState(**data)
            logger.info(f"🔄 [ORCHESTRATOR] Resumed pipeline {pipeline_id} at {self._current_state.current_phase}")
            
            # Continue execution from the current phase (Simplified view)
            # In a full impl, we'd skip completed phases in _run_pipeline()
            return True
        except Exception as e:
            logger.error(f"💥 Failed to resume pipeline {pipeline_id}: {e}")
            return False
    
    async def _assemble(self) -> Dict[str, Any]:
        """Assemble all artifacts into final course."""
        state = self._current_state
        
        # Collect all phase outputs
        assembled = {
            "course_id": f"course_{uuid.uuid4().hex[:12]}",
            "topic": state.request.topic,
            "generated_at": datetime.utcnow().isoformat(),
            "pipeline_id": state.pipeline_id,
            "artifacts": {}
        }
        
        for phase, result in state.phase_results.items():
            if result.output:
                assembled["artifacts"][phase] = result.output
        
        return assembled
    
    async def _finalize(self) -> Dict[str, Any]:
        """Finalize the course package."""
        state = self._current_state
        
        assembly_result = state.phase_results.get(PipelinePhase.ASSEMBLY.value)
        assembled = assembly_result.output if assembly_result else {}
        
        # Add metadata
        finalized = {
            **assembled,
            "finalized": True,
            "total_duration_ms": self._calculate_total_duration(),
            "handoff_count": len(self._handoffs),
            "agents_used": list(set(h.from_agent for h in self._handoffs) | set(h.to_agent for h in self._handoffs))
        }
        
        state.final_output = finalized
        return finalized
    
    # ========================
    # HELPERS
    # ========================
    
    def _get_phase_agent(self, phase: PipelinePhase) -> str:
        """Map phase to agent name."""
        mapping = {
            PipelinePhase.INITIALIZATION: "orchestrator",
            PipelinePhase.PEDAGOGY: "pedagogy",
            PipelinePhase.CINEMATIC: "cinematic_director",
            PipelinePhase.VISUAL: "visual_director",
            PipelinePhase.VOICE: "voice_agent",
            PipelinePhase.QA_CHECK: "qa_checker",
            PipelinePhase.ASSEMBLY: "orchestrator",
            PipelinePhase.FINALIZATION: "orchestrator",
        }
        return mapping.get(phase, "unknown")
    
    def _update_progress(self, completed_phase: PipelinePhase) -> None:
        """Update overall progress based on completed phase."""
        state = self._current_state
        
        completed_weight = sum(
            self._phase_weights.get(PipelinePhase(phase), 0)
            for phase, result in state.phase_results.items()
            if result.status == PhaseStatus.COMPLETED
        )
        
        state.overall_progress = min(completed_weight, 1.0)
    
    def _record_handoff(
        self,
        from_agent: str,
        to_agent: str,
        artifact_type: ArtifactType
    ) -> None:
        """Record an agent handoff."""
        self._handoffs.append(AgentHandoff(
            from_agent=from_agent,
            to_agent=to_agent,
            artifact_type=artifact_type,
            timestamp=datetime.utcnow(),
            data_size_bytes=0,  # Could calculate actual size
            success=True
        ))
    
    def _calculate_total_duration(self) -> int:
        """Calculate total pipeline duration in ms."""
        state = self._current_state
        return sum(
            result.duration_ms or 0
            for result in state.phase_results.values()
        )
    
    def _build_response(self) -> A2ACourseResponse:
        """Build the final A2A response."""
        state = self._current_state
        
        # Collect artifacts
        artifacts = []
        for phase, result in state.phase_results.items():
            if result.output:
                artifact_type = self._phase_to_artifact_type(PipelinePhase(phase))
                artifacts.append(Artifact(
                    type=artifact_type,
                    name=f"{phase}_output",
                    data=result.output,
                    created_by=self._get_phase_agent(PipelinePhase(phase))
                ))
        
        return A2ACourseResponse(
            task_id=state.pipeline_id,
            status=state.final_status,
            course_id=state.final_output.get("course_id", state.pipeline_id) if state.final_output else state.pipeline_id,
            course_title=state.request.topic,
            artifacts=artifacts,
            stages_completed=[phase for phase, result in state.phase_results.items() if result.status.value == "completed"],
            progress_percent=int(state.overall_progress * 100),
            total_duration_seconds=self._calculate_total_duration() / 1000.0,
            quality_score=self._get_qa_score()
        )
    
    def _phase_to_artifact_type(self, phase: PipelinePhase) -> ArtifactType:
        """Map pipeline phase to artifact type."""
        mapping = {
            PipelinePhase.PEDAGOGY: ArtifactType.LEARNING_OBJECTIVES,
            PipelinePhase.CINEMATIC: ArtifactType.CINEMATIC_SCENE,
            PipelinePhase.VISUAL: ArtifactType.VISUAL_ASSETS,
            PipelinePhase.VOICE: ArtifactType.VOICE_SCRIPTS,
            PipelinePhase.QA_CHECK: ArtifactType.QA_REPORT,
            PipelinePhase.ASSEMBLY: ArtifactType.COURSE_MODULE,
        }
        return mapping.get(phase, ArtifactType.TEXT_CONTENT)
    
    def _get_qa_score(self) -> Optional[float]:
        """Get QA score from results."""
        qa_result = self._current_state.phase_results.get(PipelinePhase.QA_CHECK.value)
        if qa_result and qa_result.output:
            return qa_result.output.get("overall_quality_score")
        return None


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_orchestrator_instance: Optional[A2AOrchestrator] = None

def get_orchestrator() -> A2AOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = A2AOrchestrator()
    return _orchestrator_instance
