"""
A2UI Component Generator for Lyo Backend
Generates server-driven UI components for iOS Swift renderer
"""

import json
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import uuid


class UIValueType(Enum):
    STRING = "string"
    INT = "int"
    DOUBLE = "double"
    BOOL = "bool"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


@dataclass
class UIValue:
    """Type-safe value wrapper for A2UI properties"""
    value: Any
    type: UIValueType

    @classmethod
    def string(cls, value: str) -> 'UIValue':
        return cls(value, UIValueType.STRING)

    @classmethod
    def int(cls, value: int) -> 'UIValue':
        return cls(value, UIValueType.INT)

    @classmethod
    def double(cls, value: float) -> 'UIValue':
        return cls(value, UIValueType.DOUBLE)

    @classmethod
    def bool(cls, value: bool) -> 'UIValue':
        return cls(value, UIValueType.BOOL)

    @classmethod
    def array(cls, value: List[Any]) -> 'UIValue':
        return cls(value, UIValueType.ARRAY)

    @classmethod
    def object(cls, value: Dict[str, Any]) -> 'UIValue':
        return cls(value, UIValueType.OBJECT)

    @classmethod
    def null(cls) -> 'UIValue':
        return cls(None, UIValueType.NULL)

    def to_dict(self) -> Any:
        """Convert to dictionary format for JSON serialization"""
        return self.value


@dataclass
class A2UIComponent:
    """A2UI Component with props and children"""
    id: str
    type: str
    props: Optional[Dict[str, UIValue]] = None
    children: Optional[List['A2UIComponent']] = None

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "id": self.id,
            "type": self.type
        }

        if self.props:
            result["props"] = {k: v.to_dict() for k, v in self.props.items()}

        if self.children:
            result["children"] = [child.to_dict() for child in self.children]

        return result

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)


class A2UIGenerator:
    """Main A2UI component generator"""

    # Brand colors for Lyo
    COLORS = {
        "primary": "#007AFF",
        "secondary": "#5856D6",
        "success": "#34C759",
        "warning": "#FFCC00",
        "error": "#FF3B30",
        "background": "#F8F9FA",
        "text_primary": "#000000",
        "text_secondary": "#666666"
    }

    def __init__(self):
        self.component_id_counter = 0

    def _generate_id(self) -> str:
        """Generate unique component ID"""
        self.component_id_counter += 1
        return f"component_{self.component_id_counter}"

    # MARK: - Layout Components

    def vstack(self, children: List[A2UIComponent], spacing: float = 8,
               align: str = "center", **kwargs) -> A2UIComponent:
        """Create vertical stack component"""
        props = {
            "spacing": UIValue.double(spacing),
            "align": UIValue.string(align)
        }
        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="vstack",
            props=props,
            children=children
        )

    def hstack(self, children: List[A2UIComponent], spacing: float = 8,
               align: str = "center", **kwargs) -> A2UIComponent:
        """Create horizontal stack component"""
        props = {
            "spacing": UIValue.double(spacing),
            "align": UIValue.string(align)
        }
        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="hstack",
            props=props,
            children=children
        )

    def scroll(self, children: List[A2UIComponent], direction: str = "vertical",
               show_indicators: bool = True, **kwargs) -> A2UIComponent:
        """Create scroll view component"""
        props = {
            "direction": UIValue.string(direction),
            "showIndicators": UIValue.bool(show_indicators)
        }
        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="scroll",
            props=props,
            children=children
        )

    def grid(self, children: List[A2UIComponent], columns: int = 2,
             spacing: float = 8, **kwargs) -> A2UIComponent:
        """Create grid layout component"""
        props = {
            "columns": UIValue.int(columns),
            "spacing": UIValue.double(spacing)
        }
        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="grid",
            props=props,
            children=children
        )

    # MARK: - Content Components

    def text(self, content: str, font: str = "body", color: Optional[str] = None,
             align: str = "center", line_limit: Optional[int] = None, **kwargs) -> A2UIComponent:
        """Create text component"""
        props = {
            "text": UIValue.string(content),
            "font": UIValue.string(font),
            "textAlign": UIValue.string(align)
        }

        if color:
            props["color"] = UIValue.string(color)
        if line_limit:
            props["lineLimit"] = UIValue.int(line_limit)

        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="text",
            props=props
        )

    def button(self, title: str, action: str, style: str = "primary",
               full_width: bool = False, disabled: bool = False, **kwargs) -> A2UIComponent:
        """Create button component"""
        props = {
            "title": UIValue.string(title),
            "action": UIValue.string(action),
            "style": UIValue.string(style),
            "fullWidth": UIValue.bool(full_width),
            "disabled": UIValue.bool(disabled)
        }
        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="button",
            props=props
        )

    def image(self, url: Optional[str] = None, system_name: Optional[str] = None,
              width: Optional[float] = None, height: Optional[float] = None,
              aspect_ratio: str = "fit", **kwargs) -> A2UIComponent:
        """Create image component"""
        props = {
            "aspectRatio": UIValue.string(aspect_ratio)
        }

        if url:
            props["url"] = UIValue.string(url)
        if system_name:
            props["systemName"] = UIValue.string(system_name)
        if width:
            props["width"] = UIValue.double(width)
        if height:
            props["height"] = UIValue.double(height)

        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="image",
            props=props
        )

    # MARK: - Business Components

    def course_card(self, title: str, description: str, progress: float = 0,
                   difficulty: str = "Beginner", duration: str = "1 hour",
                   image_url: Optional[str] = None, action: str = "course_tap", **kwargs) -> A2UIComponent:
        """Create course card component"""
        props = {
            "title": UIValue.string(title),
            "description": UIValue.string(description),
            "progress": UIValue.double(progress),
            "difficulty": UIValue.string(difficulty),
            "duration": UIValue.string(duration),
            "action": UIValue.string(action)
        }

        if image_url:
            props["imageUrl"] = UIValue.string(image_url)

        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="coursecard",
            props=props
        )

    def lesson_card(self, title: str, description: str, lesson_type: str = "video",
                   duration: str = "10 min", completed: bool = False,
                   action: str = "lesson_tap", **kwargs) -> A2UIComponent:
        """Create lesson card component"""
        props = {
            "title": UIValue.string(title),
            "description": UIValue.string(description),
            "type": UIValue.string(lesson_type),
            "duration": UIValue.string(duration),
            "completed": UIValue.bool(completed),
            "action": UIValue.string(action)
        }
        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="lessoncard",
            props=props
        )

    def quiz(self, question: str, options: List[str], correct_answer: int,
            selected_answer: Optional[int] = None, action: str = "quiz_answer", **kwargs) -> A2UIComponent:
        """Create quiz component"""
        props = {
            "question": UIValue.string(question),
            "options": UIValue.array(options),
            "correctAnswer": UIValue.int(correct_answer),
            "action": UIValue.string(action)
        }

        if selected_answer is not None:
            props["selectedAnswer"] = UIValue.int(selected_answer)
        else:
            props["selectedAnswer"] = UIValue.null()

        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="quiz",
            props=props
        )

    def progress_bar(self, progress: float, color: str = "#007AFF", **kwargs) -> A2UIComponent:
        """Create progress bar component"""
        props = {
            "progress": UIValue.double(progress),
            "color": UIValue.string(color)
        }
        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="progressbar",
            props=props
        )

    # MARK: - Interactive Components

    def toggle(self, label: str, value: bool = False, action: str = "toggle", **kwargs) -> A2UIComponent:
        """Create toggle component"""
        props = {
            "label": UIValue.string(label),
            "value": UIValue.bool(value),
            "action": UIValue.string(action)
        }
        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="toggle",
            props=props
        )

    def text_field(self, placeholder: str, secure: bool = False,
                  action: str = "text_input", **kwargs) -> A2UIComponent:
        """Create text field component"""
        props = {
            "placeholder": UIValue.string(placeholder),
            "secure": UIValue.bool(secure),
            "action": UIValue.string(action)
        }
        props.update(self._parse_common_props(**kwargs))

        return A2UIComponent(
            id=self._generate_id(),
            type="textfield",
            props=props
        )

    def spacer(self, height: Optional[float] = None) -> A2UIComponent:
        """Create spacer component"""
        props = {}
        if height:
            props["height"] = UIValue.double(height)

        return A2UIComponent(
            id=self._generate_id(),
            type="spacer",
            props=props if props else None
        )

    def divider(self, color: Optional[str] = None) -> A2UIComponent:
        """Create divider component"""
        props = {}
        if color:
            props["color"] = UIValue.string(color)

        return A2UIComponent(
            id=self._generate_id(),
            type="separator",
            props=props if props else None
        )

    # MARK: - Helper Methods

    def _parse_common_props(self, **kwargs) -> Dict[str, UIValue]:
        """Parse common component properties"""
        props = {}

        # Styling properties
        if "padding" in kwargs:
            props["padding"] = UIValue.double(kwargs["padding"])
        if "margin" in kwargs:
            props["margin"] = UIValue.double(kwargs["margin"])
        if "background_color" in kwargs:
            props["backgroundColor"] = UIValue.string(kwargs["background_color"])
        if "corner_radius" in kwargs:
            props["cornerRadius"] = UIValue.double(kwargs["corner_radius"])
        if "border_width" in kwargs:
            props["borderWidth"] = UIValue.double(kwargs["border_width"])
        if "border_color" in kwargs:
            props["borderColor"] = UIValue.string(kwargs["border_color"])
        if "opacity" in kwargs:
            props["opacity"] = UIValue.double(kwargs["opacity"])
        if "hidden" in kwargs:
            props["hidden"] = UIValue.bool(kwargs["hidden"])
        if "width" in kwargs:
            props["width"] = UIValue.double(kwargs["width"])
        if "height" in kwargs:
            props["height"] = UIValue.double(kwargs["height"])
        if "max_width" in kwargs:
            props["maxWidth"] = UIValue.string(str(kwargs["max_width"]))

        return props

    # MARK: - Pre-built Templates

    def learning_dashboard(self, user_name: str, stats: Dict[str, Any],
                          courses: List[Dict[str, Any]]) -> A2UIComponent:
        """Generate complete learning dashboard"""
        children = []

        # Header
        welcome_text = self.text(
            f"Welcome back, {user_name}! 👋",
            font="title",
            color=self.COLORS["primary"]
        )
        children.append(welcome_text)

        subtitle = self.text(
            "Ready to continue your learning journey?",
            font="subheadline",
            color=self.COLORS["text_secondary"]
        )
        children.append(subtitle)

        # Stats cards
        stats_cards = []
        for key, value in stats.items():
            icon_map = {
                "courses": "book.fill",
                "progress": "chart.line.uptrend.xyaxis",
                "streak": "flame.fill"
            }

            stats_card = self.vstack([
                self.image(system_name=icon_map.get(key, "circle.fill"),
                          color=self.COLORS["primary"]),
                self.text(str(value), font="title2"),
                self.text(key.title(), font="caption", color=self.COLORS["text_secondary"])
            ], spacing=8, padding=16, background_color=self.COLORS["background"],
               corner_radius=12)

            stats_cards.append(stats_card)

        stats_row = self.hstack(stats_cards, spacing=12)
        children.append(stats_row)

        # Courses section
        children.append(self.text("Continue Learning", font="headline"))

        for course in courses:
            course_card = self.course_card(
                title=course.get("title", "Unknown Course"),
                description=course.get("description", ""),
                progress=course.get("progress", 0),
                difficulty=course.get("difficulty", "Beginner"),
                duration=course.get("duration", "1 hour"),
                image_url=course.get("image_url"),
                action=f"continue_course_{course.get('id', 'unknown')}"
            )
            children.append(course_card)

        return self.scroll([
            self.vstack(children, spacing=20, padding=16)
        ])

    def quiz_session(self, question_data: Dict[str, Any],
                    current_question: int, total_questions: int) -> A2UIComponent:
        """Generate quiz session UI"""
        progress_percent = (current_question / total_questions) * 100

        children = [
            # Header
            self.text("Knowledge Check", font="title2"),
            self.text(f"Question {current_question} of {total_questions}",
                     font="subheadline", color=self.COLORS["text_secondary"]),

            # Progress
            self.progress_bar(progress_percent, color=self.COLORS["success"]),

            # Quiz component
            self.quiz(
                question=question_data.get("question", ""),
                options=question_data.get("options", []),
                correct_answer=question_data.get("correct_answer", 0),
                selected_answer=question_data.get("selected_answer"),
                action="quiz_answer"
            ),

            # Navigation
            self.hstack([
                self.button("Previous", "quiz_previous", style="outline") if current_question > 1 else self.spacer(),
                self.button("Next Question" if current_question < total_questions else "Finish Quiz",
                           "quiz_next", style="primary")
            ], spacing=12)
        ]

        return self.vstack(children, spacing=20, padding=16)

    def course_content(self, course_data: Dict[str, Any],
                      lesson_data: Dict[str, Any]) -> A2UIComponent:
        """Generate course content view"""
        children = [
            # Course header
            self.text(course_data.get("title", "Course"), font="title"),
            self.text(f"Chapter {lesson_data.get('chapter', 1)}: {lesson_data.get('title', 'Lesson')}",
                     font="headline", color=self.COLORS["primary"]),

            # Progress
            self.progress_bar(course_data.get("progress", 0), color=self.COLORS["primary"]),

            # Video or content
            self.vstack([
                self.image(url=lesson_data.get("video_thumbnail"),
                          width=300, height=200),
                self.text(lesson_data.get("description", ""), font="caption",
                         color=self.COLORS["text_secondary"])
            ], spacing=8),

            # Interactive elements
            self.button("Continue Lesson", "continue_lesson", style="primary", full_width=True)
        ]

        if lesson_data.get("next_lesson"):
            next_lesson = self.lesson_card(
                title=lesson_data["next_lesson"]["title"],
                description=lesson_data["next_lesson"]["description"],
                lesson_type=lesson_data["next_lesson"].get("type", "video"),
                duration=lesson_data["next_lesson"].get("duration", "10 min"),
                action=f"start_lesson_{lesson_data['next_lesson']['id']}"
            )
            children.append(next_lesson)

        return self.vstack(children, spacing=16, padding=16)

    def chat_interface(self, messages: List[Dict[str, Any]],
                      suggestions: List[str] = None) -> A2UIComponent:
        """Generate chat interface with A2UI"""
        children = []

        # Chat messages
        message_components = []
        for message in messages:
            is_user = message.get("is_user", False)

            # Create message bubble
            message_component = self.text(
                message.get("content", ""),
                font="body",
                padding=12,
                background_color="#F0F0F0" if not is_user else self.COLORS["primary"],
                color="#000000" if not is_user else "#FFFFFF",
                corner_radius=16
            )

            # Add A2UI component if present
            if message.get("ui_component"):
                ui_data = message["ui_component"]
                # This would be the parsed A2UI component from the message
                pass

            message_components.append(message_component)

        if message_components:
            messages_scroll = self.scroll(message_components, direction="vertical")
            children.append(messages_scroll)

        # Suggestions
        if suggestions:
            suggestion_buttons = [
                self.button(suggestion, f"suggestion_{i}", style="outline")
                for i, suggestion in enumerate(suggestions)
            ]
            suggestions_row = self.scroll([
                self.hstack(suggestion_buttons, spacing=8)
            ], direction="horizontal")
            children.append(suggestions_row)

        # Input area
        input_row = self.hstack([
            self.text_field("Type your message...", action="chat_input"),
            self.button("Send", "send_message", style="primary")
        ], spacing=12)
        children.append(input_row)

        return self.vstack(children, spacing=16, padding=16)


# Singleton instance for easy access
a2ui = A2UIGenerator()