"""
Lyo AI Classroom - Server-Driven UI (SDUI) Component Registry v1
===============================================================

Production-ready Pydantic models for the "Living Classroom" real-time scene architecture.
Maps educational interactions to strict component contracts for iOS rendering.

Architecture: Event-driven scenes → Classroom Director → SDUI Components → iOS Renderer
"""

from datetime import datetime
from enum import Enum
from typing import List, Literal, Union, Optional, Dict, Any
from uuid import uuid4, UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎭 CORE ENUMS & BASE MODELS
# ═══════════════════════════════════════════════════════════════════════════════════

class ComponentType(str, Enum):
    """Strict registry of allowed UI components"""
    TEACHER_MESSAGE = "TeacherMessage"
    STUDENT_PROMPT = "StudentPrompt"
    QUIZ_CARD = "QuizCard"
    CTA_BUTTON = "CTAButton"
    TEXT_BLOCK = "TextBlock"
    CHAT_BUBBLE = "ChatBubble"
    INPUT_FIELD = "InputField"
    PROGRESS_BAR = "ProgressBar"
    CELEBRATION = "Celebration"
    TYPING_INDICATOR = "TypingIndicator"
    REFLECTION_PROMPT = "ReflectionPrompt"
    EXAMPLE_BLOCK = "ExampleBlock"


class AnimationType(str, Enum):
    """Animation presets for component entrance"""
    FADE_IN = "fade_in"
    SLIDE_UP = "slide_up"
    SLIDE_DOWN = "slide_down"
    BOUNCE = "bounce"
    TYPING = "typing"
    NONE = "none"


class AudioMood(str, Enum):
    """TTS voice mood selection"""
    ENCOURAGING = "encouraging"    # nova - energetic
    CALM = "calm"                 # echo - warm storytelling
    AUTHORITATIVE = "authoritative" # alloy - clear teaching
    GENTLE = "gentle"             # shimmer - supportive


class ActionIntent(str, Enum):
    """User action intents that trigger scene transitions"""
    REQUEST_HINT = "request_hint"
    CONTINUE = "continue"
    RETRY = "retry"
    SUBMIT_ANSWER = "submit_answer"
    ASK_QUESTION = "ask_question"
    REQUEST_EXAMPLE = "request_example"
    SKIP_AHEAD = "skip_ahead"


class ValidationLevel(str, Enum):
    """Input validation strictness"""
    STRICT = "strict"      # Exact match required
    LENIENT = "lenient"    # Close match acceptable
    OPEN = "open"          # Any input accepted


# ═══════════════════════════════════════════════════════════════════════════════════
# 🧩 COMPONENT BASE CLASS
# ═══════════════════════════════════════════════════════════════════════════════════

class ComponentBase(BaseModel):
    """Base class for all SDUI components with common functionality"""

    component_id: str = Field(default_factory=lambda: str(uuid4()))
    type: ComponentType
    priority: int = Field(default=0, ge=0, le=10, description="Render priority (0=highest)")
    animation: AnimationType = Field(default=AnimationType.FADE_IN)
    delay_ms: int = Field(default=0, ge=0, le=5000, description="Delay before showing")
    duration_ms: Optional[int] = Field(default=None, ge=100, description="Auto-hide after duration")

    # Accessibility & Internationalization
    accessibility_label: Optional[str] = None
    language_code: str = Field(default="en-US")

    # Conditional rendering
    show_if: Optional[Dict[str, Any]] = Field(default=None, description="Conditional rendering rules")

    class Config:
        use_enum_values = True


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎓 TEACHING COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════════

class TeacherMessage(ComponentBase):
    """Primary teaching content from Lio, the AI teacher"""

    type: Literal[ComponentType.TEACHER_MESSAGE] = ComponentType.TEACHER_MESSAGE
    text: str = Field(..., min_length=1, max_length=2000)

    # Personality & Voice
    emotion: Literal["neutral", "encouraging", "thinking", "excited", "concerned"] = "neutral"
    audio_mood: AudioMood = AudioMood.CALM
    audio_url: Optional[str] = None  # Pre-generated TTS URL

    # Visual enhancements
    avatar_expression: Optional[str] = None  # "thinking", "smiling", etc.
    background_color: Optional[str] = Field(default="#F8F9FA", pattern=r"^#[0-9A-F]{6}$")

    # Educational context
    concept_tags: List[str] = Field(default_factory=list, max_items=5)
    difficulty_level: Literal["beginner", "intermediate", "advanced"] = "beginner"

    @field_validator('text')
    @classmethod
    def validate_educational_content(cls, v):
        """Ensure content follows educational best practices"""
        if len(v.split()) < 3:
            raise ValueError("Teacher messages should be at least 3 words for clarity")
        return v


class StudentPrompt(ComponentBase):
    """AI peer student interaction for normalization and encouragement"""

    type: Literal[ComponentType.STUDENT_PROMPT] = ComponentType.STUDENT_PROMPT
    student_name: str = Field(..., min_length=1, max_length=20)
    text: str = Field(..., min_length=1, max_length=500)

    # Peer persona
    student_avatar: Optional[str] = None
    personality_trait: Literal["curious", "supportive", "analytical", "creative"] = "supportive"

    # Usage context (used sparingly per your architecture)
    purpose: Literal["normalize_error", "reinforce_concept", "ask_clarifying"] = "normalize_error"

    @field_validator('student_name')
    @classmethod
    def validate_student_name(cls, v):
        """Ensure appropriate student names"""
        forbidden = ["teacher", "lio", "instructor"]
        if v.lower() in forbidden:
            raise ValueError(f"Student name cannot be {v}")
        return v


class ExampleBlock(ComponentBase):
    """Concrete examples to illustrate concepts"""

    type: Literal[ComponentType.EXAMPLE_BLOCK] = ComponentType.EXAMPLE_BLOCK
    title: str = Field(..., max_length=100)
    content: str = Field(..., max_length=1500)

    # Example metadata
    example_type: Literal["code", "visual", "analogy", "real_world"] = "real_world"
    interactive: bool = Field(default=False, description="Can user interact with example")

    # Visual styling
    code_language: Optional[str] = None  # "python", "javascript", etc.
    syntax_highlighting: bool = Field(default=True)


class ReflectionPrompt(ComponentBase):
    """Metacognitive reflection questions"""

    type: Literal[ComponentType.REFLECTION_PROMPT] = ComponentType.REFLECTION_PROMPT
    question: str = Field(..., max_length=200)

    # Reflection context
    reflection_type: Literal["self_assessment", "connection", "application"] = "self_assessment"
    suggested_duration_seconds: int = Field(default=30, ge=10, le=300)


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 INTERACTION COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════════

class QuizOption(BaseModel):
    """Individual quiz option with comprehensive feedback"""

    id: str = Field(..., min_length=1, max_length=10)
    label: str = Field(..., min_length=1, max_length=300)
    is_correct: bool = False

    # Rich feedback system
    feedback_correct: Optional[str] = Field(None, max_length=200)
    feedback_incorrect: Optional[str] = Field(None, max_length=200)

    # Misconception detection
    misconception_tag: Optional[str] = None
    remediation_hint: Optional[str] = None

    # Visual styling
    icon: Optional[str] = None
    color_scheme: Optional[str] = None


class QuizCard(ComponentBase):
    """Interactive knowledge check with Bayesian mastery tracking"""

    type: Literal[ComponentType.QUIZ_CARD] = ComponentType.QUIZ_CARD
    question: str = Field(..., min_length=5, max_length=500)
    options: List[QuizOption] = Field(..., min_items=2, max_items=6)

    # Quiz behavior
    allow_multiple_attempts: bool = True
    show_explanation_after: bool = True
    time_limit_seconds: Optional[int] = Field(None, ge=10, le=300)

    # Educational metadata
    concept_id: Optional[str] = None  # For mastery tracking
    difficulty_weight: float = Field(default=1.0, ge=0.1, le=3.0)
    bloom_taxonomy_level: Optional[Literal["remember", "understand", "apply", "analyze"]] = None

    # Accessibility
    audio_question: Optional[str] = None

    @field_validator('options')
    @classmethod
    def validate_quiz_options(cls, v):
        """Ensure quiz has exactly one correct answer"""
        correct_count = sum(1 for option in v if option.is_correct)
        if correct_count != 1:
            raise ValueError(f"Quiz must have exactly 1 correct answer, found {correct_count}")
        return v


class InputField(ComponentBase):
    """Free-form text input for open-ended questions"""

    type: Literal[ComponentType.INPUT_FIELD] = ComponentType.INPUT_FIELD
    placeholder: str = Field(..., max_length=100)

    # Input validation
    validation_level: ValidationLevel = ValidationLevel.LENIENT
    expected_keywords: List[str] = Field(default_factory=list, max_items=10)
    min_words: int = Field(default=1, ge=1, le=100)
    max_words: int = Field(default=50, ge=1, le=200)

    # Input behavior
    auto_capitalize: bool = True
    spell_check: bool = True
    multiline: bool = False


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎬 ACTION & NAVIGATION COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════════

class CTAButton(ComponentBase):
    """Call-to-action buttons that trigger scene transitions"""

    type: Literal[ComponentType.CTA_BUTTON] = ComponentType.CTA_BUTTON
    label: str = Field(..., min_length=1, max_length=50)
    action_intent: ActionIntent

    # Visual styling
    button_style: Literal["primary", "secondary", "outline", "text"] = "primary"
    icon: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-F]{6}$")

    # Behavioral
    disabled: bool = False
    requires_confirmation: bool = False
    cooldown_seconds: int = Field(default=0, ge=0, le=60)

    # Context payload
    action_payload: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ProgressBar(ComponentBase):
    """Visual progress indicator"""

    type: Literal[ComponentType.PROGRESS_BAR] = ComponentType.PROGRESS_BAR
    current: int = Field(..., ge=0)
    total: int = Field(..., ge=1)

    # Display options
    show_percentage: bool = True
    show_fraction: bool = False
    label: Optional[str] = None

    # Styling
    color_scheme: Literal["blue", "green", "purple", "orange"] = "blue"

    @field_validator('current')
    @classmethod
    def validate_progress(cls, v, info):
        """Ensure progress doesn't exceed total"""
        if 'total' in info.data and v > info.data['total']:
            raise ValueError(f"Progress {v} cannot exceed total {info.data['total']}")
        return v


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎉 FEEDBACK & CELEBRATION COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════════

class Celebration(ComponentBase):
    """Celebration animations for achievements"""

    type: Literal[ComponentType.CELEBRATION] = ComponentType.CELEBRATION
    message: str = Field(..., max_length=100)

    # Celebration intensity
    celebration_type: Literal["subtle", "standard", "epic"] = "standard"
    particle_effect: Literal["confetti", "stars", "sparkles", "none"] = "confetti"

    # Achievement context
    achievement_type: Optional[str] = None  # "first_correct", "streak", "mastery"
    points_earned: int = Field(default=0, ge=0)

    # Auto-dismiss
    auto_dismiss_ms: int = Field(default=3000, ge=1000, le=10000)


class TypingIndicator(ComponentBase):
    """Shows AI is thinking/typing"""

    type: Literal[ComponentType.TYPING_INDICATOR] = ComponentType.TYPING_INDICATOR
    agent_name: str = Field(default="Lio", max_length=20)

    # Indicator style
    indicator_style: Literal["dots", "pulse", "wave"] = "dots"
    estimated_duration_ms: int = Field(default=2000, ge=500, le=10000)


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎨 UTILITY COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════════

class TextBlock(ComponentBase):
    """Generic text content block"""

    type: Literal[ComponentType.TEXT_BLOCK] = ComponentType.TEXT_BLOCK
    content: str = Field(..., min_length=1, max_length=3000)

    # Formatting
    markdown_enabled: bool = False
    text_style: Literal["body", "caption", "heading", "subheading"] = "body"
    text_alignment: Literal["left", "center", "right"] = "left"


class ChatBubble(ComponentBase):
    """Chat-style message bubble"""

    type: Literal[ComponentType.CHAT_BUBBLE] = ComponentType.CHAT_BUBBLE
    sender: str = Field(..., max_length=50)
    message: str = Field(..., max_length=1000)

    # Chat styling
    sender_type: Literal["teacher", "student", "system"] = "teacher"
    timestamp: Optional[datetime] = None
    avatar_url: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════════
# 🚀 SCENE & PAYLOAD MODELS
# ═══════════════════════════════════════════════════════════════════════════════════

# Master Component Union - THIS IS THE KEY CONTRACT
Component = Union[
    TeacherMessage,
    StudentPrompt,
    QuizCard,
    CTAButton,
    TextBlock,
    ChatBubble,
    InputField,
    ProgressBar,
    Celebration,
    TypingIndicator,
    ReflectionPrompt,
    ExampleBlock
]


class SceneType(str, Enum):
    """Scene classification for the Scene Lifecycle Engine"""
    INSTRUCTION = "instruction"      # Teaching new concepts
    CHALLENGE = "challenge"          # Testing understanding
    CORRECTION = "correction"        # Addressing misconceptions
    CELEBRATION = "celebration"      # Celebrating achievements
    REFLECTION = "reflection"        # Metacognitive thinking
    TRANSITION = "transition"        # Bridging between topics


class SceneState(str, Enum):
    """Scene execution state"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class SceneMetadata(BaseModel):
    """Rich metadata for scene analytics and adaptation"""

    # Educational context
    concept_tags: List[str] = Field(default_factory=list)
    difficulty_level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    estimated_duration_seconds: int = Field(default=30, ge=5, le=600)

    # Mastery tracking
    prerequisite_concepts: List[str] = Field(default_factory=list)
    target_concepts: List[str] = Field(default_factory=list)

    # Adaptive parameters
    user_mastery_context: Optional[Dict[str, float]] = None
    frustration_level: float = Field(default=0.0, ge=0.0, le=1.0)

    # Analytics
    scene_source: Literal["ai_generated", "template", "fallback"] = "ai_generated"
    creation_timestamp: datetime = Field(default_factory=datetime.utcnow)


class Scene(BaseModel):
    """A complete educational micro-interaction"""

    scene_id: str = Field(default_factory=lambda: str(uuid4()))
    scene_type: SceneType
    components: List[Component] = Field(..., min_items=1, max_items=10)

    # Scene lifecycle
    state: SceneState = SceneState.PENDING
    metadata: SceneMetadata = Field(default_factory=SceneMetadata)

    # Context & conditions
    trigger_conditions: Optional[Dict[str, Any]] = None
    success_conditions: Optional[Dict[str, Any]] = None
    failure_conditions: Optional[Dict[str, Any]] = None

    # Scene sequencing
    next_scene_id: Optional[str] = None
    fallback_scene_id: Optional[str] = None

    @field_validator('components')
    @classmethod
    def validate_scene_coherence(cls, v, info):
        """Ensure scene components make educational sense together"""
        scene_type = info.data.get('scene_type')

        if scene_type == SceneType.CHALLENGE:
            # Challenge scenes must have at least one interaction component
            interaction_types = [ComponentType.QUIZ_CARD, ComponentType.INPUT_FIELD]
            has_interaction = any(comp.type in interaction_types for comp in v)
            if not has_interaction:
                raise ValueError("Challenge scenes require at least one interactive component")

        return v


# ═══════════════════════════════════════════════════════════════════════════════════
# 📡 WEBSOCKET STREAMING PAYLOADS
# ═══════════════════════════════════════════════════════════════════════════════════

class WebSocketEventType(str, Enum):
    """WebSocket event types for real-time streaming"""
    SCENE_START = "scene_start"
    SCENE_UPDATE = "scene_update"
    SCENE_COMPLETE = "scene_complete"
    COMPONENT_RENDER = "component_render"
    USER_ACTION = "user_action"
    SYSTEM_STATE = "system_state"
    ERROR = "error"


class WebSocketPayload(BaseModel):
    """Base WebSocket message structure"""

    event_type: WebSocketEventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    user_id: Optional[str] = None

    # Event data
    data: Dict[str, Any] = Field(default_factory=dict)

    # Message routing
    room_id: Optional[str] = None  # For future multi-user features
    priority: int = Field(default=0, ge=0, le=10)

    class Config:
        use_enum_values = True


class SceneStreamPayload(WebSocketPayload):
    """Specialized payload for scene streaming"""

    event_type: Literal[WebSocketEventType.SCENE_START, WebSocketEventType.SCENE_UPDATE] = WebSocketEventType.SCENE_START
    scene: Scene

    # Streaming metadata
    is_final: bool = Field(default=True, description="False for partial/progressive updates")
    component_count: int = Field(..., ge=1)

    # Pre-fetching hints for client
    prefetch_assets: List[str] = Field(default_factory=list)
    next_scene_preview: Optional[str] = None


class ComponentRenderPayload(WebSocketPayload):
    """Individual component rendering instruction"""

    event_type: Literal[WebSocketEventType.COMPONENT_RENDER] = WebSocketEventType.COMPONENT_RENDER
    component: Component

    # Render timing
    render_immediately: bool = True
    delay_after_previous_ms: int = Field(default=0, ge=0, le=5000)

    # Animation overrides
    animation_override: Optional[AnimationType] = None
    transition_duration_ms: int = Field(default=300, ge=0, le=2000)


class UserActionPayload(WebSocketPayload):
    """User interaction data flowing back to backend"""

    event_type: Literal[WebSocketEventType.USER_ACTION] = WebSocketEventType.USER_ACTION
    action_intent: ActionIntent
    component_id: str

    # Action data
    answer_data: Optional[Dict[str, Any]] = None
    interaction_context: Optional[Dict[str, Any]] = None

    # Performance tracking
    response_time_ms: Optional[int] = None
    attempts_made: int = Field(default=1, ge=1)


class SystemStatePayload(WebSocketPayload):
    """System state updates (progress, mastery, achievements)"""

    event_type: Literal[WebSocketEventType.SYSTEM_STATE] = WebSocketEventType.SYSTEM_STATE

    # State updates
    progress_update: Optional[Dict[str, Any]] = None
    mastery_update: Optional[Dict[str, float]] = None
    achievement_unlocked: Optional[Dict[str, Any]] = None

    # UI state changes
    navigation_state: Optional[Dict[str, Any]] = None
    ui_mode: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 VERSION & COMPATIBILITY
# ═══════════════════════════════════════════════════════════════════════════════════

class SDUIVersion(BaseModel):
    """Version information for backward compatibility"""

    major: int = 1
    minor: int = 0
    patch: int = 0

    # Compatibility matrix
    min_ios_version: str = "1.0.0"
    min_backend_version: str = "1.0.0"

    # Feature flags
    supported_features: List[str] = Field(default_factory=lambda: [
        "basic_components",
        "scene_streaming",
        "mastery_tracking",
        "real_time_adaptation"
    ])

    def is_compatible_with(self, client_version: str) -> bool:
        """Check if client version is compatible"""
        # Implement semver compatibility logic
        return True  # Simplified for now


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎪 MASTER EXPORT
# ═══════════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Core Types
    "Component", "ComponentType", "Scene", "SceneType",

    # Teaching Components
    "TeacherMessage", "StudentPrompt", "ExampleBlock", "ReflectionPrompt",

    # Interaction Components
    "QuizCard", "QuizOption", "InputField", "CTAButton",

    # UI Components
    "TextBlock", "ChatBubble", "ProgressBar", "Celebration", "TypingIndicator",

    # Streaming Payloads
    "WebSocketPayload", "SceneStreamPayload", "ComponentRenderPayload",
    "UserActionPayload", "SystemStatePayload",

    # Infrastructure
    "SDUIVersion", "SceneMetadata", "AnimationType", "ActionIntent"
]