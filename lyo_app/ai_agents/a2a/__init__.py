"""
A2A (Agent-to-Agent) Protocol Implementation for Lyo AI Classroom.

This module implements Google's A2A protocol for multi-agent orchestration,
enabling specialized agents to collaborate on cinematic course generation.

Architecture:
- AgentCard: Self-describing agent capabilities (per A2A spec)
- TaskInput/TaskOutput: Standardized message passing
- Artifacts: Reusable outputs between agents
- Streaming: Real-time SSE updates during generation

Agents:
- PedagogyAgent: Learning design, objectives, scaffolding
- CinematicDirectorAgent: Scene flow, pacing, engagement
- QACheckerAgent: Fact validation, accuracy, bias detection
- VisualDirectorAgent: Image prompts, diagrams, visuals
- VoiceAgent: TTS with emotion, avatar sync

Orchestrator:
- A2AOrchestrator: Pipeline coordination, agent handoffs, parallel execution

Routes:
- /api/v2/courses/generate-a2a - Synchronous course generation
- /api/v2/courses/stream-a2a - Streaming course generation (SSE)
- /api/v2/agents - Agent discovery
- /.well-known/agent.json - A2A protocol discovery

MIT Architecture Engineering - A2A Protocol Implementation
"""

# Core Schemas
from .schemas import (
    AgentCard,
    AgentSkill,
    AgentCapability,
    TaskInput,
    TaskOutput,
    TaskStatus,
    Artifact,
    ArtifactType,
    StreamingEvent,
    EventType,
    A2AMessage,
    MessageRole,
    A2ACourseRequest,
    A2ACourseResponse,
)

# Base Agent Class
from .base import A2ABaseAgent, A2AAgentMetrics

# Specialized Agents
from .pedagogy_agent import PedagogyAgent, PedagogyOutput
from .cinematic_director_agent import CinematicDirectorAgent, CinematicOutput
from .qa_checker_agent import QACheckerAgent, QAOutput
from .visual_director_agent import VisualDirectorAgent, VisualDirectorOutput
from .voice_agent import VoiceAgent, VoiceAgentOutput

# Orchestrator
from .orchestrator import (
    A2AOrchestrator,
    PipelineConfig,
    PipelineState,
    PipelinePhase,
    PhaseStatus,
    PhaseResult,
    get_orchestrator,
)

# Routes
from .routes import router as a2a_router, discovery_router, include_a2a_routes

__all__ = [
    # Core Schemas
    "AgentCard",
    "AgentSkill",
    "AgentCapability", 
    "TaskInput",
    "TaskOutput",
    "TaskStatus",
    "Artifact",
    "ArtifactType",
    "StreamingEvent",
    "EventType",
    "A2AMessage",
    "MessageRole",
    "A2ACourseRequest",
    "A2ACourseResponse",
    
    # Base Classes
    "A2ABaseAgent",
    "A2AAgentMetrics",
    
    # Specialized Agents
    "PedagogyAgent",
    "PedagogyOutput",
    "CinematicDirectorAgent",
    "CinematicOutput",
    "QACheckerAgent",
    "QAOutput",
    "VisualDirectorAgent",
    "VisualDirectorOutput",
    "VoiceAgent",
    "VoiceAgentOutput",
    
    # Orchestrator
    "A2AOrchestrator",
    "PipelineConfig",
    "PipelineState",
    "PipelinePhase",
    "PhaseStatus",
    "PhaseResult",
    "get_orchestrator",
    
    # Routes
    "a2a_router",
    "discovery_router",
    "include_a2a_routes",
]
