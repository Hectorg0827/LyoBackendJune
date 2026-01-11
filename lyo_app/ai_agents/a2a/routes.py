"""
A2A Protocol API Routes.

FastAPI endpoints for the A2A course generation pipeline.
Implements both synchronous and streaming endpoints following
the Google A2A protocol specification.

Endpoints:
- POST /api/v2/courses/generate-a2a - Generate course (sync)
- POST /api/v2/courses/stream-a2a - Generate course (streaming SSE)
- GET /api/v2/agents - List all agent cards
- GET /api/v2/agents/{agent_name} - Get specific agent card
- GET /.well-known/agent.json - Agent discovery endpoint
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import json
import asyncio
import traceback

from .schemas import (
    A2ACourseRequest,
    A2ACourseResponse,
    AgentCard,
    StreamingEvent,
    TaskStatus,
)
from .orchestrator import (
    A2AOrchestrator,
    PipelineConfig,
    PipelineState,
    get_orchestrator,
)


# ============================================================
# API ROUTER
# ============================================================

router = APIRouter(prefix="/api/v2", tags=["A2A Course Generation"])


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class A2AGenerateRequest(BaseModel):
    """Request for A2A course generation."""
    topic: str = Field(..., description="Course topic or learning request")
    quality_tier: str = Field(default="standard", description="Quality tier: quick, standard, premium")
    user_context: Optional[Dict[str, Any]] = Field(default=None, description="User preferences and context")
    
    # Pipeline options
    enable_visual: bool = Field(default=True, description="Generate visual assets")
    enable_voice: bool = Field(default=True, description="Generate voice scripts")
    enable_qa: bool = Field(default=True, description="Run QA validation")
    parallel_execution: bool = Field(default=True, description="Run visual/voice in parallel")
    
    # Quality settings
    min_qa_score: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum QA score to pass")
    
    class Config:
        json_schema_extra = {
            "example": {
                "topic": "Introduction to Machine Learning",
                "quality_tier": "standard",
                "user_context": {
                    "level": "intermediate",
                    "style": "visual",
                    "goals": ["career change", "understand AI"]
                },
                "enable_visual": True,
                "enable_voice": True,
                "parallel_execution": True
            }
        }


class A2AStatusResponse(BaseModel):
    """Response for pipeline status check."""
    pipeline_id: str
    status: str
    current_phase: str
    progress: float
    phases_completed: List[str]
    estimated_remaining_seconds: Optional[int] = None


class AgentListResponse(BaseModel):
    """Response for agent listing."""
    agents: List[AgentCard]
    total_count: int


class AgentDiscoveryResponse(BaseModel):
    """Agent discovery response (/.well-known/agent.json format)."""
    agents: List[Dict[str, Any]]
    protocol_version: str = "1.0"
    capabilities: List[str]
    supported_content_types: List[str]


# ============================================================
# COURSE GENERATION ENDPOINTS
# ============================================================

@router.post("/courses/generate-a2a", response_model=A2ACourseResponse)
async def generate_course_a2a(request: A2AGenerateRequest) -> A2ACourseResponse:
    """
    Generate a complete course using the A2A multi-agent pipeline.
    
    This endpoint runs the full pipeline synchronously and returns
    the complete course with all artifacts when finished.
    
    For real-time progress updates, use the streaming endpoint instead.
    
    **Pipeline Phases:**
    1. Initialization - Validate request
    2. Pedagogy - Learning science analysis
    3. Cinematic - Story and scene design
    4. Visual - Image and diagram specs (parallel)
    5. Voice - Audio and narration (parallel)
    6. QA Check - Quality validation
    7. Assembly - Combine artifacts
    8. Finalization - Package course
    
    **Typical Duration:** 60-180 seconds depending on quality tier
    """
    orchestrator = get_orchestrator()
    
    # Build A2A request
    a2a_request = A2ACourseRequest(
        topic=request.topic,
        quality_tier=request.quality_tier,
        user_context=request.user_context
    )
    
    # Build pipeline config
    config = PipelineConfig(
        enable_visual=request.enable_visual,
        enable_voice=request.enable_voice,
        enable_qa=request.enable_qa,
        parallel_visual_voice=request.parallel_execution,
        min_qa_score=request.min_qa_score
    )
    
    try:
        response = await orchestrator.generate_course(a2a_request, config)
        return response
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Course generation failed: {str(e)}"
        )


@router.post("/courses/stream-a2a")
async def stream_course_a2a(request: A2AGenerateRequest) -> StreamingResponse:
    """
    Generate a course with real-time streaming progress updates.
    
    Returns Server-Sent Events (SSE) stream with:
    - Task started/completed events
    - Agent started/completed events
    - Progress updates
    - Partial content as it's generated
    - Final course data
    
    **SSE Event Format:**
    ```
    data: {"event_type": "agent_started", "agent_name": "pedagogy", "progress": 0.15, ...}
    
    data: {"event_type": "progress", "progress": 0.45, "message": "Generating scenes..."}
    
    data: {"event_type": "task_completed", "data": {<full_course>}}
    ```
    
    **Typical Duration:** 60-180 seconds with updates every few seconds
    """
    orchestrator = get_orchestrator()
    
    a2a_request = A2ACourseRequest(
        topic=request.topic,
        quality_tier=request.quality_tier,
        user_context=request.user_context
    )
    
    config = PipelineConfig(
        enable_visual=request.enable_visual,
        enable_voice=request.enable_voice,
        enable_qa=request.enable_qa,
        parallel_visual_voice=request.parallel_execution,
        min_qa_score=request.min_qa_score,
        enable_streaming=True
    )
    
    async def event_generator():
        """Generate SSE events from the pipeline."""
        try:
            async for event in orchestrator.generate_course_streaming(a2a_request, config):
                yield event.to_sse_data()
                # Small delay to prevent overwhelming client
                await asyncio.sleep(0.05)
        except Exception as e:
            error_event = StreamingEvent(
                event_type="error",
                task_id="unknown",
                agent_name="orchestrator",
                data={"error": str(e)},
                message=f"Pipeline error: {str(e)}"
            )
            yield error_event.to_sse_data()
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.get("/courses/status/{pipeline_id}", response_model=A2AStatusResponse)
async def get_pipeline_status(pipeline_id: str) -> A2AStatusResponse:
    """
    Get the current status of a running pipeline.
    
    Note: This is for polling status. For real-time updates,
    use the streaming endpoint instead.
    """
    orchestrator = get_orchestrator()
    state = orchestrator.get_pipeline_state()
    
    if not state or state.pipeline_id != pipeline_id:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    completed_phases = [
        phase for phase, result in state.phase_results.items()
        if result.status.value == "completed"
    ]
    
    return A2AStatusResponse(
        pipeline_id=state.pipeline_id,
        status=state.final_status.value,
        current_phase=state.current_phase.value,
        progress=state.overall_progress,
        phases_completed=completed_phases
    )


# ============================================================
# AGENT DISCOVERY ENDPOINTS
# ============================================================

@router.get("/agents", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    """
    List all available A2A agents and their capabilities.
    
    Returns agent cards describing:
    - Agent name and description
    - Skills and capabilities
    - Input/output formats
    - Performance characteristics
    """
    orchestrator = get_orchestrator()
    cards = orchestrator.get_agent_cards()
    
    return AgentListResponse(
        agents=cards,
        total_count=len(cards)
    )


@router.get("/agents/{agent_name}", response_model=AgentCard)
async def get_agent(agent_name: str) -> AgentCard:
    """
    Get the agent card for a specific agent.
    
    Agent names:
    - pedagogy
    - cinematic_director
    - visual_director
    - voice_agent
    - qa_checker
    """
    orchestrator = get_orchestrator()
    cards = orchestrator.get_agent_cards()
    
    for card in cards:
        if card.name.lower().replace(" ", "_") == agent_name.lower():
            return card
    
    raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")


# ============================================================
# WELL-KNOWN DISCOVERY ENDPOINT
# ============================================================

# This needs to be on a separate router to avoid /api/v2 prefix
discovery_router = APIRouter(tags=["A2A Discovery"])


@discovery_router.get("/.well-known/agent.json", response_model=AgentDiscoveryResponse)
async def agent_discovery() -> AgentDiscoveryResponse:
    """
    A2A Protocol Discovery Endpoint.
    
    Standard endpoint for agent discovery following the
    Google A2A protocol specification.
    
    Clients can call this endpoint to discover:
    - Available agents and their capabilities
    - Supported protocols and content types
    - How to interact with each agent
    """
    orchestrator = get_orchestrator()
    cards = orchestrator.get_agent_cards()
    
    # Convert agent cards to discovery format
    agents_data = []
    for card in cards:
        agents_data.append({
            "name": card.name,
            "description": card.description,
            "version": card.version,
            "skills": [skill.dict() for skill in card.skills] if card.skills else [],
            "capabilities": [cap.value for cap in card.capabilities] if card.capabilities else [],
            "endpoints": {
                "execute": f"/api/v2/agents/{card.name.lower().replace(' ', '_')}/execute",
                "info": f"/api/v2/agents/{card.name.lower().replace(' ', '_')}"
            }
        })
    
    return AgentDiscoveryResponse(
        agents=agents_data,
        protocol_version="1.0",
        capabilities=[
            "course_generation",
            "streaming",
            "multi_agent_orchestration",
            "visual_generation",
            "voice_generation",
            "quality_assurance"
        ],
        supported_content_types=[
            "application/json",
            "text/event-stream"
        ]
    )


# ============================================================
# HEALTH & INFO ENDPOINTS
# ============================================================

@router.get("/a2a/health")
async def a2a_health_check() -> Dict[str, Any]:
    """
    A2A pipeline health check.
    
    Returns status of:
    - Orchestrator availability
    - Agent availability
    - Model backend connectivity
    """
    orchestrator = get_orchestrator()
    cards = orchestrator.get_agent_cards()
    
    return {
        "status": "healthy",
        "orchestrator": "available",
        "agents": {
            card.name: "available" for card in cards
        },
        "agent_count": len(cards),
        "streaming_enabled": True
    }


@router.get("/a2a/info")
async def a2a_info() -> Dict[str, Any]:
    """
    Get information about the A2A pipeline.
    """
    return {
        "name": "Lyo A2A Course Generation Pipeline",
        "version": "1.0.0",
        "protocol": "Google A2A",
        "description": "Multi-agent pipeline for generating cinematic educational courses",
        "phases": [
            "initialization",
            "pedagogy",
            "cinematic",
            "visual",
            "voice",
            "qa_check",
            "assembly",
            "finalization"
        ],
        "agents": [
            {
                "name": "PedagogyAgent",
                "role": "Learning science expert"
            },
            {
                "name": "CinematicDirectorAgent", 
                "role": "Story and scene design"
            },
            {
                "name": "VisualDirectorAgent",
                "role": "Image and diagram generation"
            },
            {
                "name": "VoiceAgent",
                "role": "Audio and narration scripts"
            },
            {
                "name": "QACheckerAgent",
                "role": "Quality validation"
            }
        ],
        "quality_tiers": {
            "quick": "Fast generation, basic quality",
            "standard": "Balanced speed and quality",
            "premium": "Maximum quality, longer generation"
        },
        "typical_duration_seconds": {
            "quick": 30,
            "standard": 90,
            "premium": 180
        }
    }


# ============================================================
# INDIVIDUAL AGENT EXECUTION (Advanced)
# ============================================================

@router.post("/agents/{agent_name}/execute")
async def execute_agent(
    agent_name: str,
    user_message: str = Query(..., description="User input/request"),
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute a single agent directly (advanced use).
    
    This bypasses the orchestrator and runs a specific agent.
    Useful for testing or when you only need one agent's output.
    
    Note: For full course generation, use /courses/generate-a2a instead.
    """
    orchestrator = get_orchestrator()
    
    # Map agent name to agent
    agent_map = {
        "pedagogy": orchestrator.pedagogy_agent,
        "cinematic_director": orchestrator.cinematic_agent,
        "visual_director": orchestrator.visual_agent,
        "voice_agent": orchestrator.voice_agent,
        "qa_checker": orchestrator.qa_agent,
    }
    
    agent = agent_map.get(agent_name.lower())
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found. Available: {list(agent_map.keys())}"
        )
    
    from .schemas import TaskInput
    
    task_input = TaskInput(
        task_id=f"direct_{agent_name}",
        requesting_agent="api",
        user_message=user_message,
        context=context
    )
    
    try:
        output = await agent.execute(task_input)
        return {
            "agent": agent_name,
            "status": "completed",
            "output": output.dict() if hasattr(output, 'dict') else output
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}"
        )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def include_a2a_routes(app):
    """
    Helper to include all A2A routes in a FastAPI app.
    
    Usage:
        from lyo_app.ai_agents.a2a.routes import include_a2a_routes
        include_a2a_routes(app)
    """
    app.include_router(router)
    app.include_router(discovery_router)
