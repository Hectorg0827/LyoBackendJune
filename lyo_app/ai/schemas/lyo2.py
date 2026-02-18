from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class InputModality(str, Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"


class Intent(str, Enum):
    EXPLAIN = "EXPLAIN"
    COURSE = "COURSE"  # "teach me X", "create a course", "learn about X"
    QUIZ = "QUIZ"
    FLASHCARDS = "FLASHCARDS"
    STUDY_PLAN = "STUDY_PLAN"
    SUMMARIZE_NOTES = "SUMMARIZE_NOTES"
    SCHEDULE_REMINDERS = "SCHEDULE_REMINDERS"
    COMMUNITY = "COMMUNITY"
    MODIFY_ARTIFACT = "MODIFY_ARTIFACT"
    GREETING = "GREETING"
    CHAT = "CHAT"
    HELP = "HELP"
    GENERAL = "GENERAL"
    UNKNOWN = "UNKNOWN"


class ArtifactType(str, Enum):
    QUIZ = "QUIZ"
    STUDY_PLAN = "STUDY_PLAN"
    FLASHCARDS = "FLASHCARDS"


class MediaRef(BaseModel):
    """Reference to uploaded media stored in GCS / Firebase Storage."""
    model_config = ConfigDict(extra="forbid")
    modality: InputModality
    uri: str  # gs://... or https://...
    mime_type: Optional[str] = None
    duration_ms: Optional[int] = None


class ActiveArtifactContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: str
    artifact_type: ArtifactType
    artifact_version: int


class RouterEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subject: Optional[str] = None
    topic: Optional[str] = None
    grade_level: Optional[str] = None
    test_date: Optional[str] = None  # ISO date when extracted reliably
    extracted_from: List[InputModality] = Field(default_factory=list)
    image_context: Optional[str] = None  # short description: "graph of parabola y=x^2"
    audio_signals: Optional[Dict[str, Any]] = None  # e.g. {"stress":0.7,"urgency":0.8}


class RouterDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    entities: RouterEntity = Field(default_factory=RouterEntity)

    # Follow-up / mutation routing
    is_reply_to_artifact: bool = False
    artifact: Optional[ActiveArtifactContext] = None

    # Clarification gating
    needs_clarification: bool = False
    clarification_question: Optional[str] = None

    # Cost controls
    suggested_tier: Literal["TINY", "MEDIUM", "LARGE"] = "TINY"

    @field_validator("suggested_tier", mode="before")
    @classmethod
    def normalize_tier(cls, v: Any) -> str:
        """Gemini sometimes returns non-standard tier names like LOW, HIGH, SMALL."""
        if isinstance(v, str):
            v_upper = v.upper().strip()
            mapping = {
                "LOW": "TINY", "SMALL": "TINY", "MINI": "TINY",
                "MED": "MEDIUM", "STANDARD": "MEDIUM", "NORMAL": "MEDIUM",
                "HIGH": "LARGE", "BIG": "LARGE", "COMPLEX": "LARGE",
            }
            return mapping.get(v_upper, v_upper)
        return v


class ConversationTurn(BaseModel):
    """A single turn in conversation history for multi-turn context."""
    model_config = ConfigDict(extra="ignore")
    role: str  # "user" or "assistant"
    content: str


class RouterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    text: Optional[str] = None
    media: List[MediaRef] = Field(default_factory=list)
    active_artifact: Optional[ActiveArtifactContext] = None
    state_summary: Dict[str, Any] = Field(default_factory=dict)  # curated learning state head
    conversation_history: List[ConversationTurn] = Field(
        default_factory=list,
        description="Recent conversation turns for multi-turn context continuity"
    )


class RouterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: RouterDecision
    trace_id: str


# --- Layer B: Planner Schemas ---

class ActionType(str, Enum):
    RAG_RETRIEVE = "RAG_RETRIEVE"
    CREATE_ARTIFACT = "CREATE_ARTIFACT"
    UPDATE_ARTIFACT = "UPDATE_ARTIFACT"
    CALENDAR_SYNC = "CALENDAR_SYNC"
    SEARCH_WEB = "SEARCH_WEB"
    GENERATE_TEXT = "GENERATE_TEXT"
    GENERATE_AUDIO = "GENERATE_AUDIO"
    GENERATE_A2UI = "GENERATE_A2UI"


class PlannedAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action_type: ActionType
    parameters: Dict[str, Any] = Field(default_factory=dict)
    description: str


class LyoPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    steps: List[PlannedAction] = Field(default_factory=list)
    artifacts_to_create: List[ArtifactType] = Field(default_factory=list)
    safety_constraints: List[str] = Field(default_factory=list)
    grounding_required: bool = True
    suggested_model: str = "gemini-2.0-flash"


# --- Layer C: Executor / UI Block Schemas ---

class UIBlockType(str, Enum):
    TUTOR_MESSAGE = "TutorMessageBlock"
    QUIZ = "QuizBlock"
    STUDY_PLAN = "StudyPlanBlock"
    FLASHCARDS = "FlashcardsBlock"
    CTA_ROW = "CTARow"
    SKELETON = "Skeleton"
    OPEN_CLASSROOM = "OpenClassroomBlock"
    A2UI_COMPONENT = "A2UIComponent"


class UIBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: UIBlockType
    content: Dict[str, Any]
    version_id: Optional[str] = None


class UnifiedChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer_block: UIBlock  # TutorMessage
    artifact_block: Optional[UIBlock] = None
    next_actions: List[UIBlock] = Field(default_factory=list)  # CTA Row
    a2ui_blocks: List[UIBlock] = Field(default_factory=list)  # A2UI component blocks
    open_classroom_payload: Optional[Dict[str, Any]] = None  # Course creation trigger
    audio_summary_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
