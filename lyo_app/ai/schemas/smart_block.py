"""
SmartBlock Pydantic schemas for unified block vocabulary.

These models are the canonical definition of the SmartBlock format,
shared across chat, course generation, and classroom rendering.
The iOS client decodes these directly via SmartBlock.swift.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SmartBlock Type Enum
# ---------------------------------------------------------------------------

class SmartBlockType(str, Enum):
    """9+1 unified block types with subtypes."""
    text = "text"               # subtypes: heading, paragraph, summary, callout, hook, revelation
    code = "code"               # subtypes: snippet, playground, terminal
    quiz = "quiz"               # subtypes: mcq, trueFalse, fillBlank, poll
    flashcard = "flashcard"     # subtypes: single, deck
    data_viz = "dataViz"        # subtypes: chart, graph, diagram, math, table
    media = "media"             # subtypes: image, video, audio, animation
    progress = "progress"       # subtypes: checkpoint, celebration, divider, spacer, timeline
    interactive = "interactive" # subtypes: comparison, stepByStep, notes
    mastery_map = "masteryMap"
    unknown = "unknown"


# ---------------------------------------------------------------------------
# Content Payloads
# ---------------------------------------------------------------------------

class TextBlockContent(BaseModel):
    text: str
    style: Optional[str] = None

class CodeBlockContent(BaseModel):
    language: str = "plain"
    code: str
    is_runnable: Optional[bool] = None

class QuizOption(BaseModel):
    id: str
    text: str

class QuizBlockContent(BaseModel):
    question: str
    options: List[QuizOption]
    correct_index: int
    explanation: Optional[str] = None
    hint: Optional[str] = None

class FlashcardBlockContent(BaseModel):
    front: str
    back: str
    tags: Optional[str] = None

class DataVizBlockContent(BaseModel):
    format: str = "text"  # mermaid, chart, table, math
    source: str
    title: Optional[str] = None

class MediaBlockContent(BaseModel):
    url: str
    alt: Optional[str] = None
    caption: Optional[str] = None

class ProgressBlockContent(BaseModel):
    completed: int
    total: int
    label: Optional[str] = None

class InteractiveItem(BaseModel):
    label: str
    detail: str

class InteractiveBlockContent(BaseModel):
    items: List[InteractiveItem]
    title: Optional[str] = None

class MasteryNode(BaseModel):
    node_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:8])
    title: str
    status: str = "locked"
    mastery_level: Optional[float] = None

class MasteryMapBlockContent(BaseModel):
    title: str
    nodes: List[MasteryNode]


# ---------------------------------------------------------------------------
# SmartBlock (top-level)
# ---------------------------------------------------------------------------

class SmartBlock(BaseModel):
    """A single renderable content block with schema versioning."""
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])
    schema_version: int = 1
    type: SmartBlockType
    subtype: Optional[str] = None
    content: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def text(cls, text: str, subtype: str = "paragraph", **kwargs) -> "SmartBlock":
        return cls(type=SmartBlockType.text, subtype=subtype, content=TextBlockContent(text=text, **kwargs).model_dump())

    @classmethod
    def code(cls, code: str, language: str = "python", **kwargs) -> "SmartBlock":
        return cls(type=SmartBlockType.code, subtype="snippet", content=CodeBlockContent(code=code, language=language, **kwargs).model_dump())

    @classmethod
    def quiz(cls, question: str, options: List[QuizOption], correct_index: int, **kwargs) -> "SmartBlock":
        return cls(type=SmartBlockType.quiz, subtype="mcq", content=QuizBlockContent(question=question, options=options, correct_index=correct_index, **kwargs).model_dump())

    @classmethod
    def flashcard(cls, front: str, back: str, **kwargs) -> "SmartBlock":
        return cls(type=SmartBlockType.flashcard, subtype="single", content=FlashcardBlockContent(front=front, back=back, **kwargs).model_dump())

    @classmethod
    def data_viz(cls, source: str, fmt: str = "mermaid", **kwargs) -> "SmartBlock":
        return cls(type=SmartBlockType.data_viz, subtype="diagram", content=DataVizBlockContent(format=fmt, source=source, **kwargs).model_dump())

    @classmethod
    def mastery_map(cls, title: str, nodes: List[MasteryNode], **kwargs) -> "SmartBlock":
        return cls(type=SmartBlockType.mastery_map, content=MasteryMapBlockContent(title=title, nodes=nodes, **kwargs).model_dump())
