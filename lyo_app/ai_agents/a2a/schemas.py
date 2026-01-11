"""
A2A Protocol Schemas - Pydantic models for Agent-to-Agent communication.

Based on Google's A2A Protocol specification:
https://github.com/google/A2A

Key concepts:
- AgentCard: Self-describing agent capabilities (like OpenAPI for agents)
- Task: Unit of work with input/output
- Artifact: Reusable output between agents
- Message: Conversational history
- Streaming: Real-time updates via SSE

MIT Architecture Engineering - A2A Schema Definitions
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ============================================================
# ENUMS
# ============================================================

class TaskStatus(str, Enum):
    """Status of a task in the A2A pipeline"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_INPUT = "needs_input"  # Agent needs human input


class ArtifactType(str, Enum):
    """Types of artifacts produced by agents"""
    COURSE_INTENT = "course_intent"
    CURRICULUM_STRUCTURE = "curriculum_structure"
    LESSON_CONTENT = "lesson_content"
    CINEMATIC_SCENE = "cinematic_scene"
    QA_REPORT = "qa_report"
    VISUAL_PROMPT = "visual_prompt"
    VOICE_SCRIPT = "voice_script"
    IMAGE_URL = "image_url"
    AUDIO_URL = "audio_url"
    ASSESSMENT = "assessment"


class EventType(str, Enum):
    """Types of streaming events"""
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    ARTIFACT_CREATED = "artifact_created"
    AGENT_HANDOFF = "agent_handoff"
    CONTENT_CHUNK = "content_chunk"
    THINKING = "thinking"  # Agent reasoning (for transparency)


class MessageRole(str, Enum):
    """Role in conversation/task history"""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class AgentCapability(str, Enum):
    """Standard capabilities agents can advertise"""
    COURSE_DESIGN = "course_design"
    CONTENT_GENERATION = "content_generation"
    CURRICULUM_PLANNING = "curriculum_planning"
    CINEMATIC_DIRECTION = "cinematic_direction"
    QUALITY_ASSURANCE = "quality_assurance"
    VISUAL_DESIGN = "visual_design"
    VOICE_SYNTHESIS = "voice_synthesis"
    ASSESSMENT_CREATION = "assessment_creation"
    TUTORING = "tutoring"
    FACT_CHECKING = "fact_checking"


class ScenePacing(str, Enum):
    """Pacing for cinematic scenes"""
    SLOW = "slow"          # Reflective, deep learning moments
    MEDIUM = "medium"      # Standard explanation pace  
    FAST = "fast"          # Quick transitions, high energy
    DYNAMIC = "dynamic"    # Varies within scene


class EmotionalTone(str, Enum):
    """Emotional tone for scenes"""
    CURIOUS = "curious"           # Sparking interest
    EXCITED = "excited"           # High energy, celebration
    FOCUSED = "focused"           # Deep concentration
    REFLECTIVE = "reflective"     # Thoughtful, introspective
    TRIUMPHANT = "triumphant"     # Achievement, success
    ENCOURAGING = "encouraging"   # Supportive, motivating
    PLAYFUL = "playful"          # Light, fun learning
    SERIOUS = "serious"          # Important concepts


# ============================================================
# AGENT CARD (Self-Description per A2A Spec)
# ============================================================

class AgentSkill(BaseModel):
    """Individual skill/capability of an agent"""
    id: str = Field(..., description="Unique skill identifier")
    name: str = Field(..., description="Human-readable skill name")
    description: str = Field(..., description="What this skill does")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema for input")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema for output")
    examples: Optional[List[Dict[str, Any]]] = Field(None, description="Example input/output pairs")


class AgentCard(BaseModel):
    """
    Self-describing agent card per A2A protocol.
    Exposed at /.well-known/agent.json for discovery.
    """
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="What this agent does")
    version: str = Field(default="1.0.0", description="Agent version")
    
    # Capabilities
    capabilities: List[AgentCapability] = Field(
        default_factory=list,
        description="List of agent capabilities"
    )
    skills: List[AgentSkill] = Field(
        default_factory=list,
        description="Detailed skill definitions"
    )
    
    # Model info
    model_name: Optional[str] = Field(None, description="Underlying AI model")
    model_provider: Optional[str] = Field(None, description="Model provider (google, openai, etc)")
    
    # Endpoints
    url: Optional[str] = Field(None, description="Agent's API endpoint")
    streaming_supported: bool = Field(default=True, description="Whether agent supports SSE")
    
    # Metadata
    author: str = Field(default="Lyo Team", description="Agent author")
    documentation_url: Optional[str] = Field(None, description="Link to docs")
    icon_url: Optional[str] = Field(None, description="Agent icon")
    
    # A2A Protocol
    a2a_version: str = Field(default="0.1.0", description="A2A protocol version")
    supports_push_notifications: bool = Field(default=False)
    authentication_required: bool = Field(default=True)
    
    def model_dump_for_discovery(self) -> Dict[str, Any]:
        """Format for /.well-known/agent.json"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.url,
            "capabilities": [c.value for c in self.capabilities],
            "skills": [s.model_dump() for s in self.skills],
            "a2a_version": self.a2a_version,
            "streaming_supported": self.streaming_supported,
            "authentication_required": self.authentication_required,
        }


# ============================================================
# TASK & MESSAGE SCHEMAS
# ============================================================

class A2AMessage(BaseModel):
    """Message in task conversation history"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None
    
    # For agent messages
    agent_name: Optional[str] = None
    thinking: Optional[str] = None  # Agent's reasoning (optional transparency)


class Artifact(BaseModel):
    """
    Reusable output from an agent.
    Artifacts can be passed between agents in the pipeline.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: ArtifactType
    name: str
    description: Optional[str] = None
    
    # Content (one of these should be set)
    data: Optional[Dict[str, Any]] = None  # Structured data
    text: Optional[str] = None  # Plain text
    url: Optional[str] = None  # URL reference
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(..., description="Agent that created this artifact")
    version: int = Field(default=1)
    
    # Quality info (from QA agent)
    quality_score: Optional[float] = Field(None, ge=0, le=100)
    quality_notes: Optional[str] = None
    
    def model_dump_compact(self) -> Dict[str, Any]:
        """Compact representation for streaming"""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "created_by": self.created_by,
        }


class TaskInput(BaseModel):
    """
    Input to an A2A task.
    Contains the request and any artifacts from previous agents.
    """
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    
    # User request
    user_message: str = Field(..., description="Original user request")
    conversation_history: List[A2AMessage] = Field(default_factory=list)
    
    # Artifacts from previous agents in pipeline
    input_artifacts: List[Artifact] = Field(default_factory=list)
    
    # Context
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    language: str = Field(default="en")
    
    # Configuration
    quality_tier: str = Field(default="recommended")  # economy, recommended, premium
    max_budget_usd: Optional[float] = None
    timeout_seconds: float = Field(default=300.0)
    
    # Options
    enable_streaming: bool = Field(default=True)
    include_thinking: bool = Field(default=False)  # Show agent reasoning
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None


class TaskOutput(BaseModel):
    """
    Output from an A2A task.
    Contains results, artifacts, and status.
    """
    task_id: str
    status: TaskStatus
    
    # Results
    response_message: Optional[str] = None  # Human-readable summary
    output_artifacts: List[Artifact] = Field(default_factory=list)
    
    # For streaming
    chunks_sent: int = Field(default=0)
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    # Cost tracking
    tokens_used: int = Field(default=0)
    estimated_cost_usd: float = Field(default=0.0)
    
    # Error info
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    
    # Pipeline info
    agents_involved: List[str] = Field(default_factory=list)
    
    # Quality summary
    overall_quality_score: Optional[float] = None


# ============================================================
# STREAMING EVENTS
# ============================================================

class StreamingEvent(BaseModel):
    """
    Real-time event for SSE streaming.
    Clients receive these as the pipeline progresses.
    """
    event_type: EventType
    task_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Event-specific data
    agent_name: Optional[str] = None
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    message: Optional[str] = None
    
    # Content chunk (for CONTENT_CHUNK events)
    chunk_content: Optional[str] = None
    chunk_index: Optional[int] = None
    
    # Artifact reference (for ARTIFACT_CREATED events)
    artifact: Optional[Artifact] = None
    
    # Thinking (for THINKING events)
    thinking_content: Optional[str] = None
    
    # Error (for TASK_FAILED events)
    error: Optional[str] = None
    
    def to_sse_data(self) -> str:
        """Format for Server-Sent Events"""
        import json
        return json.dumps(self.model_dump(mode='json', exclude_none=True))


# ============================================================
# PIPELINE CONFIGURATION
# ============================================================

class PipelineStage(BaseModel):
    """Configuration for a single stage in the pipeline"""
    agent_name: str
    required: bool = True
    timeout_seconds: float = 120.0
    retry_count: int = 2
    input_artifacts: List[ArtifactType] = Field(default_factory=list)
    output_artifacts: List[ArtifactType] = Field(default_factory=list)


class PipelineConfig(BaseModel):
    """Configuration for the entire A2A pipeline"""
    name: str
    description: str
    stages: List[PipelineStage]
    
    # Quality settings
    enable_qa: bool = True
    qa_strictness: str = Field(default="standard")  # lenient, standard, strict
    
    # Feature flags
    enable_visuals: bool = True
    enable_voice: bool = True
    enable_streaming: bool = True
    
    # Limits
    max_total_time_seconds: float = 600.0
    max_budget_usd: Optional[float] = None


# ============================================================
# CINEMATIC-SPECIFIC SCHEMAS
# ============================================================

class CinematicScene(BaseModel):
    """A scene in the cinematic course flow"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    scene_number: int
    scene_type: str  # intro, explanation, example, practice, transition, climax, outro
    
    # Content
    title: str
    narration: str  # What avatar says
    visual_description: str  # What's shown on screen
    
    # Emotional arc
    energy_level: int = Field(..., ge=1, le=10)  # 1=calm, 10=exciting
    emotion: str  # curious, excited, focused, reflective, triumphant
    
    # Timing
    duration_seconds: int
    pacing: str  # slow, medium, fast
    
    # Hooks
    hook_type: Optional[str] = None  # question, challenge, reveal, cliffhanger
    hook_content: Optional[str] = None
    
    # Transitions
    transition_in: Optional[str] = None
    transition_out: Optional[str] = None
    
    # Avatar
    avatar_state: str = Field(default="neutral")  # neutral, thinking, excited, explaining
    avatar_gesture: Optional[str] = None


class VoiceScript(BaseModel):
    """Script for TTS with emotion markers"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    scene_id: str
    
    # Text with markers
    ssml_text: str  # SSML-formatted text with emotion markers
    plain_text: str  # Plain text fallback
    
    # Voice settings
    voice_id: str = Field(default="alloy")
    speaking_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=1.0, ge=0.5, le=2.0)
    
    # Emotion
    base_emotion: str
    emotion_intensity: float = Field(default=0.5, ge=0, le=1)
    
    # Timing
    estimated_duration_seconds: float
    word_timestamps: Optional[List[Dict[str, Any]]] = None  # For lip sync


class VisualPrompt(BaseModel):
    """Prompt for image/diagram generation"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    scene_id: str
    
    # Generation info
    prompt: str  # Full prompt for image generation
    negative_prompt: Optional[str] = None
    style: str = Field(default="educational")  # educational, technical, artistic
    
    # Image specs
    aspect_ratio: str = Field(default="16:9")
    resolution: str = Field(default="1024x576")
    
    # Content description
    subject: str
    context: str
    mood: str
    
    # For diagrams
    diagram_type: Optional[str] = None  # flowchart, sequence, class, architecture
    diagram_elements: Optional[List[str]] = None


# ============================================================
# COURSE GENERATION REQUEST/RESPONSE
# ============================================================

class A2ACourseRequest(BaseModel):
    """Request to generate a course via A2A pipeline"""
    topic: str = Field(..., min_length=3, max_length=500)
    
    # Target
    difficulty: str = Field(default="intermediate")  # beginner, intermediate, advanced
    estimated_hours: Optional[int] = None  # Auto-detected if not specified
    
    # Style
    teaching_style: str = Field(default="cinematic")  # cinematic, traditional, interactive
    include_projects: bool = True
    include_quizzes: bool = True
    
    # Quality
    quality_tier: str = Field(default="recommended")
    
    # A2A options
    enable_streaming: bool = True
    include_thinking: bool = False
    
    # User context
    user_id: Optional[str] = None
    language: str = Field(default="en")
    
    # Limits
    max_budget_usd: Optional[float] = None


class A2ACourseResponse(BaseModel):
    """Response from A2A course generation"""
    task_id: str
    status: TaskStatus
    
    # Course data (when complete)
    course_id: Optional[str] = None
    course_title: Optional[str] = None
    course_description: Optional[str] = None
    
    # Artifacts produced
    artifacts: List[Artifact] = Field(default_factory=list)
    
    # Pipeline info
    stages_completed: List[str] = Field(default_factory=list)
    current_stage: Optional[str] = None
    progress_percent: int = Field(default=0)
    
    # Quality
    quality_score: Optional[float] = None
    quality_report: Optional[Dict[str, Any]] = None
    
    # Timing
    total_duration_seconds: Optional[float] = None
    
    # Cost
    total_tokens: int = Field(default=0)
    estimated_cost_usd: float = Field(default=0.0)
    
    # Errors
    error: Optional[str] = None
