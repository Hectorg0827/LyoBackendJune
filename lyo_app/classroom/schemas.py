from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field

# =============================================================================
# BASE CLASSROOM CARD
# =============================================================================

class BaseLyoCard(BaseModel):
    """
    Base properties for all Lyo Classroom cards.
    """
    type: str = Field(..., description="The type of the card")
    voice_text: str = Field(..., description="The spoken narration for this card")
    audio_url: Optional[str] = Field(None, description="The URL to the synthesized narration audio file")


# =============================================================================
# THE 7 EXACT CARD TYPES
# =============================================================================

class ConceptCard(BaseLyoCard):
    """
    Explain a new concept.
    Visual: Animated mesh gradient background + kinetic typography.
    """
    type: Literal["concept_card"] = "concept_card"
    key_term: str = Field(..., description="The most important word or phrase (appears in kinetic typography)")
    body_text: str = Field(..., description="The explanation text that fades in after the key term")


class DiagramNode(BaseModel):
    id: str
    symbol_name: str = Field(..., description="An SF Symbol name (must be valid)")
    label: str
    color_hex: Optional[str] = None

class DiagramConnection(BaseModel):
    source_id: str
    target_id: str
    label: Optional[str] = None

class DiagramCard(BaseLyoCard):
    """
    Visualize a process or structure.
    Visual: SF Symbols composed by the AI + Canvas-drawn connectors.
    """
    type: Literal["diagram_card"] = "diagram_card"
    nodes: List[DiagramNode] = Field(..., description="The elements of the diagram")
    connections: List[DiagramConnection] = Field(..., description="How nodes connect to each other")


class AnalogyCard(BaseLyoCard):
    """
    Make abstract ideas concrete.
    Visual: Split layout — two contrasting gradient panels.
    """
    type: Literal["analogy_card"] = "analogy_card"
    concept_side: str = Field(..., description="The abstract concept being explained")
    analogy_side: str = Field(..., description="The concrete analogy it is compared to")


class QuizCard(BaseLyoCard):
    """
    Check understanding interactively.
    Visual: Clean question layout + animated answer reveal + particle burst on correct.
    """
    type: Literal["quiz_card"] = "quiz_card"
    question: str = Field(..., description="The question being asked")
    options: List[str] = Field(..., min_length=2, max_length=4, description="The answer choices")
    correct_option_index: int = Field(..., description="The 0-based index of the correct option")
    explanation: Optional[str] = Field(None, description="Why the answer is correct")


class ReflectCard(BaseLyoCard):
    """
    Promote deeper thinking.
    Visual: Minimal, contemplative design + large open text field.
    """
    type: Literal["reflect_card"] = "reflect_card"
    prompt: str = Field(..., description="A contemplative question for the student to reflect purely on")


class SummaryCard(BaseLyoCard):
    """
    Consolidate at lesson end.
    Visual: Key points appear one by one with staggered spring animation.
    """
    type: Literal["summary_card"] = "summary_card"
    title: str = Field("Summary", description="The title of the summary")
    key_points: List[str] = Field(..., description="List of the main takeaways")


class TransitionCard(BaseLyoCard):
    """
    Bridge between topics.
    Visual: Full-bleed color wash + Voice Orb prominent.
    """
    type: Literal["transition_card"] = "transition_card"
    title: str = Field(..., description="The large transition text")


# =============================================================================
# PAYLOAD TYPE
# =============================================================================

LyoCardType = Union[
    ConceptCard,
    DiagramCard,
    AnalogyCard,
    QuizCard,
    ReflectCard,
    SummaryCard,
    TransitionCard,
]

class LyoLessonPalette(BaseModel):
    """
    Adaptive Color Palette assigned by the Director Agent.
    """
    color1_hex: str = Field(..., description="Primary hex color")
    color2_hex: str = Field(..., description="Secondary hex color")
    color3_hex: str = Field(..., description="Accent hex color")

class LyoLessonMetadata(BaseModel):
    """
    Metadata for the entire lesson stream.
    """
    topic: str
    palette: LyoLessonPalette

class LyoStreamChunk(BaseModel):
    """
    Wrapper for streaming either metadata or individual cards to the iOS app.
    """
    metadata: Optional[LyoLessonMetadata] = None
    card: Optional[LyoCardType] = Field(None, discriminator="type")
    is_complete: bool = False
