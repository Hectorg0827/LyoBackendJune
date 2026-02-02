from enum import Enum
from typing import List, Optional, Union, Literal, Annotated
from pydantic import BaseModel, Field, HttpUrl

# --- ENUMS ---
class BlockType(str, Enum):
    CONCEPT = "concept"
    QUIZ = "quiz"
    CODE = "code"
    REFLECTION = "reflection"
    IMAGE = "image"
    VIDEO = "video"
    HOOK = "hook"  # Added

class PresentationHint(str, Enum):
    INLINE = "inline"       # Chat bubble
    HERO = "hero"           # Large card
    CINEMATIC = "cinematic" # Full-screen immersive

class SemanticRole(str, Enum):
    NORMAL = "normal"
    HOOK = "hook"          # Cinematic opener
    CHAPTER = "chapter"
    CHECKPOINT = "checkpoint"
    REMEDIAL = "remedial"  # Injected correction
    ASSESSMENT = "assessment"

# --- CONTENT PAYLOADS ---
class ConceptPayload(BaseModel):
    kind: Literal["concept"] = "concept"
    markdown: str
    key_takeaway: Optional[str] = None

class QuizOption(BaseModel):
    id: str
    text: str

class QuizPayload(BaseModel):
    kind: Literal["quiz"] = "quiz"
    question: str
    options: List[QuizOption]
    correct_option_id: str
    explanation: Optional[str] = None

class ImagePayload(BaseModel):
    kind: Literal["image"] = "image"
    url: HttpUrl
    caption: Optional[str] = None

class A2UICinematic(BaseModel):
    kind: Literal["cinematic"] = "cinematic"
    title: str
    subtitle: Optional[str] = None
    mood: str
    videoUrl: Optional[str] = None

# Discriminated Union Container
BlockContent = Annotated[
    Union[ConceptPayload, QuizPayload, ImagePayload, A2UICinematic],
    Field(discriminator="kind")
]

# --- THE MASTER BLOCK ---
class LyoBlock(BaseModel):
    id: str
    type: BlockType
    role: SemanticRole = SemanticRole.NORMAL
    presentation_hint: PresentationHint = PresentationHint.INLINE
    
    content: BlockContent  # Polymorphic payload

    requires_interaction: bool = False
    interaction_id: Optional[str] = None
    
    # Cinematic Metadata
    mood: Optional[str] = "neutral"  # e.g., "mysterious", "playful"
