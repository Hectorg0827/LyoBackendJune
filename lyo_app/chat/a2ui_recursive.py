from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal, Any, Dict
from enum import Enum
import uuid

# Base component with common properties
class UIComponentBase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str

# Layout Components (Containers)
class VStackComponent(UIComponentBase):
    type: Literal["vstack"] = "vstack"
    spacing: Optional[float] = 12.0
    alignment: Literal["leading", "center", "trailing"] = "leading"
    children: List["UIComponent"] = Field(default_factory=list)

class HStackComponent(UIComponentBase):
    type: Literal["hstack"] = "hstack"
    spacing: Optional[float] = 12.0
    alignment: Literal["top", "center", "bottom"] = "center"
    children: List["UIComponent"] = Field(default_factory=list)

class CardComponent(UIComponentBase):
    type: Literal["card"] = "card"
    title: Optional[str] = None
    subtitle: Optional[str] = None
    background_color: Optional[str] = None
    children: List["UIComponent"] = Field(default_factory=list)

# Content Components (Leaves)
class TextComponent(UIComponentBase):
    type: Literal["text"] = "text"
    content: str
    font_style: Literal["title", "headline", "body", "caption", "code"] = "body"
    color: Optional[str] = None
    alignment: Literal["leading", "center", "trailing"] = "leading"

class ButtonComponent(UIComponentBase):
    type: Literal["button"] = "button"
    label: str
    action_id: str
    variant: Literal["primary", "secondary", "destructive", "ghost"] = "primary"
    is_disabled: bool = False

class ImageComponent(UIComponentBase):
    type: Literal["image"] = "image"
    url: str
    alt_text: Optional[str] = None
    aspect_ratio: Optional[str] = "1:1"

class DividerComponent(UIComponentBase):
    type: Literal["divider"] = "divider"
    color: Optional[str] = None

class SpacerComponent(UIComponentBase):
    type: Literal["spacer"] = "spacer"
    height: Optional[float] = 16.0

# Legacy Components (for backward compatibility)
class QuizComponent(UIComponentBase):
    type: Literal["quiz"] = "quiz"
    question: str
    options: List[str]
    correct_index: Optional[int] = None
    explanation: Optional[str] = None

class CourseRoadmapComponent(UIComponentBase):
    type: Literal["course_roadmap"] = "course_roadmap"
    title: str
    modules: List[Dict[str, Any]]
    total_modules: int
    completed_modules: int

# AI Classroom Integration Components
class CoursePreviewComponent(UIComponentBase):
    type: Literal["course_preview"] = "course_preview"
    course_id: str
    title: str
    description: str
    subject: str
    grade_band: str
    estimated_minutes: int
    total_nodes: int
    thumbnail_url: Optional[str] = None
    start_action_id: str = "start_course"
    preview_action_id: str = "preview_course"

class LearningNodeComponent(UIComponentBase):
    type: Literal["learning_node"] = "learning_node"
    node_id: str
    title: str
    content: str
    node_type: str  # narrative, interaction, quiz, etc.
    is_completed: bool = False
    is_current: bool = False
    estimated_minutes: Optional[int] = None
    continue_action_id: str = "continue_node"

class ProgressTrackerComponent(UIComponentBase):
    type: Literal["progress_tracker"] = "progress_tracker"
    course_title: str
    current_node: int
    total_nodes: int
    completed_percentage: float
    current_node_title: Optional[str] = None
    next_node_title: Optional[str] = None
    continue_action_id: str = "continue_learning"

class InteractiveLessonComponent(UIComponentBase):
    type: Literal["interactive_lesson"] = "interactive_lesson"
    lesson_id: str
    title: str
    content: str
    lesson_type: str  # video, audio, text, interactive
    media_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    has_quiz: bool = False
    quiz_action_id: str = "take_quiz"
    continue_action_id: str = "continue_lesson"

# Import advanced components
try:
    from .advanced_a2ui_components import (
        VideoPlayerComponent, InteractiveVideoComponent, VideoPlaylistComponent,
        CodeSandboxComponent, CodeEditorComponent, CodeOutputComponent, CodeDiffComponent,
        CollaborationSpaceComponent, WhiteboardComponent, AnnotationComponent,
        PeerReviewComponent, SimulationComponent, VirtualLabComponent,
        GameBasedLearningComponent, AutoGradedAssignmentComponent, PortfolioComponent
    )
    ADVANCED_COMPONENTS_AVAILABLE = True
except ImportError:
    ADVANCED_COMPONENTS_AVAILABLE = False

# Union type for polymorphism
if ADVANCED_COMPONENTS_AVAILABLE:
    UIComponent = Union[
        VStackComponent, HStackComponent, CardComponent,
        TextComponent, ButtonComponent, ImageComponent,
        DividerComponent, SpacerComponent,
        QuizComponent, CourseRoadmapComponent,
        CoursePreviewComponent, LearningNodeComponent,
        ProgressTrackerComponent, InteractiveLessonComponent,
        # Advanced components
        VideoPlayerComponent, InteractiveVideoComponent, VideoPlaylistComponent,
        CodeSandboxComponent, CodeEditorComponent, CodeOutputComponent, CodeDiffComponent,
        CollaborationSpaceComponent, WhiteboardComponent, AnnotationComponent,
        PeerReviewComponent, SimulationComponent, VirtualLabComponent,
        GameBasedLearningComponent, AutoGradedAssignmentComponent, PortfolioComponent
    ]
else:
    UIComponent = Union[
        VStackComponent, HStackComponent, CardComponent,
        TextComponent, ButtonComponent, ImageComponent,
        DividerComponent, SpacerComponent,
        QuizComponent, CourseRoadmapComponent,
        CoursePreviewComponent, LearningNodeComponent,
        ProgressTrackerComponent, InteractiveLessonComponent
    ]

# Update forward references for recursion
VStackComponent.model_rebuild()
HStackComponent.model_rebuild()
CardComponent.model_rebuild()

# Factory functions for easy creation
class A2UIFactory:
    @staticmethod
    def vstack(*children: UIComponent, spacing: float = 12.0, alignment: str = "leading") -> VStackComponent:
        return VStackComponent(spacing=spacing, alignment=alignment, children=list(children))

    @staticmethod
    def hstack(*children: UIComponent, spacing: float = 12.0, alignment: str = "center") -> HStackComponent:
        return HStackComponent(spacing=spacing, alignment=alignment, children=list(children))

    @staticmethod
    def card(*args, title: str = None, subtitle: str = None, **kwargs) -> CardComponent:
        """Create a card with optional title and subtitle"""
        # Handle legacy API: card(title, *children) or card(title, subtitle, *children)
        if args and isinstance(args[0], str) and (not title):
            if len(args) >= 2 and isinstance(args[1], str) and all(not isinstance(arg, str) for arg in args[2:]):
                # Pattern: card(title, subtitle, *children)
                return CardComponent(title=args[0], subtitle=args[1], children=list(args[2:]))
            else:
                # Pattern: card(title, *children)
                return CardComponent(title=args[0], subtitle=subtitle, children=list(args[1:]))
        else:
            # New API: card(*children, title=title, subtitle=subtitle)
            return CardComponent(title=title, subtitle=subtitle, children=list(args))

    @staticmethod
    def titled_card(title: str, *children: UIComponent, subtitle: str = None) -> CardComponent:
        """Create a card with a required title and optional subtitle"""
        return CardComponent(title=title, subtitle=subtitle, children=list(children))

    @staticmethod
    def text(content: str, style: str = "body", color: str = None, alignment: str = "leading") -> TextComponent:
        return TextComponent(content=content, font_style=style, color=color, alignment=alignment)

    @staticmethod
    def button(label: str, action_id: str, variant: str = "primary", disabled: bool = False) -> ButtonComponent:
        return ButtonComponent(label=label, action_id=action_id, variant=variant, is_disabled=disabled)

    @staticmethod
    def image(url: str, alt_text: str = None, aspect_ratio: str = "1:1") -> ImageComponent:
        return ImageComponent(url=url, alt_text=alt_text, aspect_ratio=aspect_ratio)

    @staticmethod
    def divider(color: str = None) -> DividerComponent:
        return DividerComponent(color=color)

    @staticmethod
    def spacer(height: float = 16.0) -> SpacerComponent:
        return SpacerComponent(height=height)

    @staticmethod
    def quiz(question: str, options: List[str], correct_index: int = None, explanation: str = None) -> QuizComponent:
        return QuizComponent(question=question, options=options, correct_index=correct_index, explanation=explanation)

    # AI Classroom Integration Factory Methods
    @staticmethod
    def course_preview(course_id: str, title: str, description: str, subject: str,
                      grade_band: str, estimated_minutes: int, total_nodes: int,
                      thumbnail_url: str = None) -> CoursePreviewComponent:
        """Create a course preview card for AI Classroom courses"""
        return CoursePreviewComponent(
            course_id=course_id, title=title, description=description,
            subject=subject, grade_band=grade_band, estimated_minutes=estimated_minutes,
            total_nodes=total_nodes, thumbnail_url=thumbnail_url
        )

    @staticmethod
    def learning_node(node_id: str, title: str, content: str, node_type: str,
                     is_completed: bool = False, is_current: bool = False,
                     estimated_minutes: int = None) -> LearningNodeComponent:
        """Create a learning node display for AI Classroom lessons"""
        return LearningNodeComponent(
            node_id=node_id, title=title, content=content, node_type=node_type,
            is_completed=is_completed, is_current=is_current, estimated_minutes=estimated_minutes
        )

    @staticmethod
    def progress_tracker(course_title: str, current_node: int, total_nodes: int,
                        current_node_title: str = None, next_node_title: str = None) -> ProgressTrackerComponent:
        """Create a progress tracker for AI Classroom courses"""
        completed_percentage = (current_node / total_nodes) * 100 if total_nodes > 0 else 0
        return ProgressTrackerComponent(
            course_title=course_title, current_node=current_node, total_nodes=total_nodes,
            completed_percentage=completed_percentage, current_node_title=current_node_title,
            next_node_title=next_node_title
        )

    @staticmethod
    def interactive_lesson(lesson_id: str, title: str, content: str, lesson_type: str,
                          media_url: str = None, duration_seconds: int = None,
                          has_quiz: bool = False) -> InteractiveLessonComponent:
        """Create an interactive lesson component for AI Classroom"""
        return InteractiveLessonComponent(
            lesson_id=lesson_id, title=title, content=content, lesson_type=lesson_type,
            media_url=media_url, duration_seconds=duration_seconds, has_quiz=has_quiz
        )

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> UIComponent:
        """Convert dictionary to UIComponent"""
        if not isinstance(data, dict):
            raise ValueError("Input must be a dictionary")

        component_type = data.get("type")
        if not component_type:
            raise ValueError("Component type is required")

        # Map component types to their classes
        type_mapping = {
            "vstack": VStackComponent,
            "hstack": HStackComponent,
            "card": CardComponent,
            "text": TextComponent,
            "button": ButtonComponent,
            "image": ImageComponent,
            "divider": DividerComponent,
            "spacer": SpacerComponent,
            "quiz": QuizComponent,
            "course_roadmap": CourseRoadmapComponent,
            "course_preview": CoursePreviewComponent,
            "learning_node": LearningNodeComponent,
            "progress_tracker": ProgressTrackerComponent,
            "interactive_lesson": InteractiveLessonComponent
        }

        # Add advanced component types if available
        if ADVANCED_COMPONENTS_AVAILABLE:
            type_mapping.update({
                "video_player": VideoPlayerComponent,
                "interactive_video": InteractiveVideoComponent,
                "video_playlist": VideoPlaylistComponent,
                "code_sandbox": CodeSandboxComponent,
                "code_editor": CodeEditorComponent,
                "code_output": CodeOutputComponent,
                "code_diff": CodeDiffComponent,
                "collaboration_space": CollaborationSpaceComponent,
                "whiteboard": WhiteboardComponent,
                "annotation": AnnotationComponent,
                "peer_review": PeerReviewComponent,
                "simulation": SimulationComponent,
                "virtual_lab": VirtualLabComponent,
                "game_based_learning": GameBasedLearningComponent,
                "auto_graded_assignment": AutoGradedAssignmentComponent,
                "portfolio": PortfolioComponent
            })

        component_class = type_mapping.get(component_type)
        if not component_class:
            raise ValueError(f"Unknown component type: {component_type}")

        try:
            return component_class(**data)
        except Exception as e:
            # Fallback to basic text component for invalid data
            return TextComponent(
                content=f"Error loading component: {component_type}",
                font_style="caption",
                color="red"
            )

    # Advanced component factory methods (only available if advanced components are imported)
    @staticmethod
    def video_player(video_url: str, title: str = None, **kwargs):
        """Create video player component"""
        if not ADVANCED_COMPONENTS_AVAILABLE:
            return A2UIFactory.text("Advanced video components not available", color="red")
        from .advanced_a2ui_components import AdvancedA2UIFactory
        return AdvancedA2UIFactory.video_player(video_url, title, **kwargs)

    @staticmethod
    def code_sandbox(language: str, title: str, initial_code: str = "", **kwargs):
        """Create code sandbox component"""
        if not ADVANCED_COMPONENTS_AVAILABLE:
            return A2UIFactory.text("Advanced coding components not available", color="red")
        from .advanced_a2ui_components import AdvancedA2UIFactory, CodeLanguage
        try:
            lang_enum = CodeLanguage(language)
            return AdvancedA2UIFactory.code_sandbox(lang_enum, title, initial_code, **kwargs)
        except ValueError:
            return A2UIFactory.text(f"Unsupported language: {language}", color="red")

    @staticmethod
    def collaboration_space(title: str, collaboration_types: List[str] = None, **kwargs):
        """Create collaboration space component"""
        if not ADVANCED_COMPONENTS_AVAILABLE:
            return A2UIFactory.text("Advanced collaboration components not available", color="red")
        from .advanced_a2ui_components import AdvancedA2UIFactory, CollaborationType
        try:
            collab_types = [CollaborationType(ct) for ct in (collaboration_types or ["real_time_editing"])]
            return AdvancedA2UIFactory.collaboration_space(title, collab_types, **kwargs)
        except ValueError as e:
            return A2UIFactory.text(f"Invalid collaboration type: {e}", color="red")

    @staticmethod
    def whiteboard(width: int = 1200, height: int = 800, **kwargs):
        """Create whiteboard component"""
        if not ADVANCED_COMPONENTS_AVAILABLE:
            return A2UIFactory.text("Advanced whiteboard components not available", color="red")
        from .advanced_a2ui_components import AdvancedA2UIFactory
        return AdvancedA2UIFactory.whiteboard(width, height, **kwargs)

    @staticmethod
    def simulation(simulation_type: str, title: str, initial_state: Dict[str, Any], **kwargs):
        """Create simulation component"""
        if not ADVANCED_COMPONENTS_AVAILABLE:
            return A2UIFactory.text("Advanced simulation components not available", color="red")
        from .advanced_a2ui_components import AdvancedA2UIFactory
        return AdvancedA2UIFactory.simulation(simulation_type, title, initial_state, **kwargs)

    @staticmethod
    def game_based_learning(game_type: str, title: str, learning_goals: List[str] = None, **kwargs):
        """Create game-based learning component"""
        if not ADVANCED_COMPONENTS_AVAILABLE:
            return A2UIFactory.text("Advanced gaming components not available", color="red")
        from .advanced_a2ui_components import AdvancedA2UIFactory
        return AdvancedA2UIFactory.game_based_learning(game_type, title, learning_goals, **kwargs)

# Updated Chat Response Schema
class ChatResponseV2(BaseModel):
    response: str
    ui_layout: Optional[UIComponent] = None
    # Keep existing fields for compatibility
    content_types: Optional[List[Dict[str, Any]]] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    response_mode: Optional[str] = None
    quick_explainer: Optional[Dict[str, Any]] = None
    course_proposal: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    suggestions: Optional[List[str]] = None

# Migration helper for backward compatibility
def migrate_legacy_content_types(content_types: List[Dict[str, Any]]) -> Optional[UIComponent]:
    """Convert legacy content_types to recursive A2UI components"""
    if not content_types:
        return None

    components = []
    for ct in content_types:
        content_type = ct.get('type', '')
        data = ct.get('data', ct)  # Handle both formats

        if content_type == 'quiz':
            components.append(QuizComponent(
                question=data.get('question', ''),
                options=data.get('options', []),
                correct_index=data.get('correctIndex'),
                explanation=data.get('explanation')
            ))
        elif content_type == 'course_roadmap' or content_type == 'courseRoadmap':
            components.append(CourseRoadmapComponent(
                title=data.get('title', ''),
                modules=data.get('modules', []),
                total_modules=data.get('totalModules', 0),
                completed_modules=data.get('completedModules', 0)
            ))
        elif content_type == 'text':
            components.append(A2UIFactory.text(
                content=data.get('content', data.get('text', '')),
                style=data.get('style', 'body')
            ))
        # Add more legacy type conversions as needed

    if len(components) == 1:
        return components[0]
    elif len(components) > 1:
        return A2UIFactory.vstack(*components)
    else:
        return None