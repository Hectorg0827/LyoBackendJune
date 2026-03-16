"""
LLM Structured-Output Schemas for Lyo2 v2 (22-primitive system).

These Pydantic models define the JSON Schema that is injected into the LLM
system prompt for structured output / tool-calling.  The LLM fills these
schemas; the backend validates + normalises; the iOS client renders.

Primitive taxonomy (22 types):
  Content   : text, media, divider
  Input     : input, button
  Layout    : container, card, list, nav
  Learning  : quiz, quizResult, course, flashcard, plan, tracker, assignment, document
  Engagement: progress, aiBubble, social, alert, skeleton
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Primitive enum (mirrors iOS LyoPrimitive)
# ---------------------------------------------------------------------------

class LyoPrimitive(str, Enum):
    """22-case primitive type system."""
    # Content
    text = "text"
    media = "media"
    divider = "divider"
    # Input
    input = "input"
    button = "button"
    # Layout
    container = "container"
    card = "card"
    list = "list"
    nav = "nav"
    # Learning
    quiz = "quiz"
    quiz_result = "quizResult"
    course = "course"
    flashcard = "flashcard"
    plan = "plan"
    tracker = "tracker"
    assignment = "assignment"
    document = "document"
    # Engagement
    progress = "progress"
    ai_bubble = "aiBubble"
    social = "social"
    alert = "alert"
    skeleton = "skeleton"


# ---------------------------------------------------------------------------
# Content & Style props  (client-hint, not prescriptive)
# ---------------------------------------------------------------------------

class ContentProps(BaseModel):
    """Universal content bag — use only the fields the primitive needs."""
    model_config = ConfigDict(extra="forbid")

    text: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    body: Optional[str] = None
    label: Optional[str] = None
    placeholder: Optional[str] = None
    hint: Optional[str] = None
    icon: Optional[str] = Field(None, description="SF Symbol name")
    image_url: Optional[str] = None
    media_url: Optional[str] = None
    alt_text: Optional[str] = None


class StyleProps(BaseModel):
    """Client-hint styling. The client may override any of these."""
    model_config = ConfigDict(extra="forbid")

    foreground: Optional[str] = Field(None, description="Hex color e.g. #FF5500")
    background: Optional[str] = None
    spacing: Optional[float] = None
    radius: Optional[float] = None
    axis: Optional[str] = Field(None, description="'horizontal' | 'vertical'")
    columns: Optional[int] = None
    font_size: Optional[float] = None
    font_weight: Optional[str] = Field(None, description="'regular' | 'medium' | 'semibold' | 'bold'")
    alignment: Optional[str] = Field(None, description="'leading' | 'center' | 'trailing'")
    opacity: Optional[float] = None


class MetaProps(BaseModel):
    """Analytics / debug metadata."""
    model_config = ConfigDict(extra="forbid")

    analytics_id: Optional[str] = None
    debug_label: Optional[str] = None
    speakable_text: Optional[str] = Field(None, description="TTS override text")
    accessibility_label: Optional[str] = None


# ---------------------------------------------------------------------------
# Action model
# ---------------------------------------------------------------------------

class UIAction(BaseModel):
    """A user-interaction action attached to a component."""
    model_config = ConfigDict(extra="forbid")

    trigger: str = Field("tap", description="'tap' | 'long_press' | 'swipe_left' | 'swipe_right'")
    type: str = Field(..., description="Action type e.g. 'navigate', 'submit', 'api_call', 'dismiss'")
    payload: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# LyoUIComponent (recursive)
# ---------------------------------------------------------------------------

class LyoUIComponentSchema(BaseModel):
    """
    A single UI component node in the v2 primitive tree.

    Rules for the LLM:
    - `type` must be one of the 22 LyoPrimitive values.
    - `variant` narrows the type (e.g. type=text variant=heading).
    - Use `content` for text/labels. Use `data` for domain payloads (quiz options, course modules).
    - Use `children` for layout composition. Only layout/card/list/container types should have children.
    - Keep the tree shallow (max 4 levels deep).

    Common variant cheat-sheet:
      text     → heading | paragraph | caption | code | markdown | label | latex
      media    → image | video | audio | chart | diagram | animation
      input    → text_field | text_area | slider | toggle | dropdown | date_picker
      button   → primary | secondary | outline | icon | destructive
      container→ stack | hstack | vstack | grid | scroll | carousel | tabs | accordion
      card     → default | stat | metric | info
      list     → ordered | unordered | checklist | timeline
      nav      → breadcrumb | tabs | steps | pagination
      quiz     → mcq | multi_select | true_false | fill_blank | matching | short_answer
      quizResult→ correct | incorrect | summary | explanation
      course   → overview | module | lesson | outline | roadmap
      flashcard→ single | deck
      plan     → overview | weekly | daily | session | goal
      tracker  → progress | mistakes | streaks | heatmap
      assignment→ card | detail | submission
      document → note | pdf | summary | definition | key_points
      progress → bar | badge | xp | level | streak | ring
      aiBubble → thinking | typing | suggestion | explanation | hint | correction
      alert    → error | warning | info | success
      skeleton → card | list | text | media
    """
    model_config = ConfigDict(extra="forbid")

    type: LyoPrimitive = Field(..., description="One of the 22 primitive types")
    variant: Optional[str] = Field(None, description="Sub-type selector narrowing the primitive")
    content: Optional[ContentProps] = None
    style: Optional[StyleProps] = None
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Domain-specific typed payload (quiz options, course modules, flashcard sides, etc.)"
    )
    children: Optional[List[LyoUIComponentSchema]] = Field(
        None,
        description="Child components (only for layout/container/card/list primitives)"
    )
    actions: Optional[List[UIAction]] = None
    meta: Optional[MetaProps] = None


# ---------------------------------------------------------------------------
# Command & Suggestion
# ---------------------------------------------------------------------------

class LyoCommandSchema(BaseModel):
    """A native command trigger (e.g. open_classroom, start_quiz)."""
    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., description="Command identifier e.g. 'open_classroom', 'start_quiz'")
    payload: Optional[Dict[str, Any]] = None


class LyoSuggestionSchema(BaseModel):
    """A context-aware suggestion chip."""
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Display label for the chip")
    action_id: Optional[str] = Field(None, description="Optional action identifier")
    icon: Optional[str] = Field(None, description="SF Symbol name")


# ---------------------------------------------------------------------------
# LyoResponse (top-level envelope)
# ---------------------------------------------------------------------------

class LyoResponseSchema(BaseModel):
    """
    The unified v2 response envelope.

    Rules for the LLM:
    - `message` is ALWAYS required — a plain-text AI response renderable even if `ui` is nil.
    - `ui` is optional — set it when the response benefits from structured UI.
    - `command` is for triggering native actions (e.g. opening the classroom viewer).
    - `suggestions` are context-aware follow-up chips.
    """
    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="2.0", description="Schema version")
    message: str = Field(..., description="Plain-text AI response (always renderable)")
    ui: Optional[LyoUIComponentSchema] = Field(
        None,
        description="Optional structured UI component tree"
    )
    command: Optional[LyoCommandSchema] = Field(
        None,
        description="Optional native command trigger"
    )
    suggestions: Optional[List[LyoSuggestionSchema]] = Field(
        None,
        description="Context-aware suggestion chips"
    )


# ---------------------------------------------------------------------------
# JSON Schema export (for LLM system prompts)
# ---------------------------------------------------------------------------

def get_lyo_response_json_schema() -> Dict[str, Any]:
    """Return the JSON Schema dict suitable for LLM structured output."""
    return LyoResponseSchema.model_json_schema()


def get_lyo_component_json_schema() -> Dict[str, Any]:
    """Return just the component schema (useful for partial / streaming)."""
    return LyoUIComponentSchema.model_json_schema()


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def validate_lyo_response(raw: Dict[str, Any]) -> LyoResponseSchema:
    """
    Validate + normalise a raw LLM output dict into a LyoResponseSchema.
    Raises ValidationError if the shape is invalid.
    """
    return LyoResponseSchema.model_validate(raw)


def validate_lyo_component(raw: Dict[str, Any]) -> LyoUIComponentSchema:
    """
    Validate + normalise a raw LLM component dict.
    Raises ValidationError if the shape is invalid.
    """
    return LyoUIComponentSchema.model_validate(raw)
