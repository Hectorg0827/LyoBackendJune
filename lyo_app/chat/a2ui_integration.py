"""
A2UI Integration for Chat Module
Provides A2UI component generation for chat responses
"""

import json
import logging
from typing import Dict, Any, List, Optional
from lyo_app.a2ui.a2ui_generator import a2ui, A2UIComponent
from lyo_app.chat.models import ChatMode, ChipAction

logger = logging.getLogger(__name__)


class ChatA2UIService:
    """Service for generating A2UI components in chat responses"""

    def __init__(self):
        self.generator = a2ui

    def generate_welcome_ui(self, user_name: str = "there") -> A2UIComponent:
        """Generate welcome/dashboard A2UI component"""
        return self.generator.vstack([
            # Welcome header
            self.generator.text(
                f"👋 Welcome back, {user_name}!",
                font="title2",
                color="#007AFF"
            ),

            self.generator.text(
                "What would you like to explore today?",
                font="subheadline",
                color="#666666"
            ),

            # Quick action cards
            self.generator.grid([
                self._create_feature_card(
                    "📚", "Quick Learn",
                    "Get explanations on any topic",
                    "quick_learn"
                ),
                self._create_feature_card(
                    "🎓", "Create Course",
                    "Build a complete learning path",
                    "create_course"
                ),
                self._create_feature_card(
                    "❓", "Practice Quiz",
                    "Test your knowledge",
                    "practice_quiz"
                ),
                self._create_feature_card(
                    "💻", "Code Help",
                    "Programming assistance",
                    "code_help"
                )
            ], columns=2, spacing=12),

        ], spacing=20, padding=16)

    def generate_course_creation_ui(self, course_data: Dict[str, Any]) -> A2UIComponent:
        """Generate course creation A2UI component"""
        lessons = course_data.get("lessons", [])

        children = [
            # Course header
            self.generator.text(
                f"📚 {course_data.get('title', 'Your Course')}",
                font="title"
            ),

            self.generator.text(
                course_data.get("description", "A comprehensive learning experience"),
                font="body",
                color="#666666",
                padding=8
            ),

            # Course stats
            self.generator.hstack([
                self._create_stat_pill(
                    str(len(lessons)), "Lessons", "book.fill"
                ),
                self._create_stat_pill(
                    course_data.get("estimated_duration", "2-3 hours"),
                    "Duration", "clock.fill"
                ),
                self._create_stat_pill(
                    course_data.get("difficulty", "Intermediate"),
                    "Level", "star.fill"
                )
            ], spacing=8),

            # Lessons list
            self.generator.text("Course Outline", font="headline"),
        ]

        # Add lesson cards
        for i, lesson in enumerate(lessons[:5]):  # Show first 5 lessons
            lesson_card = self.generator.lesson_card(
                title=f"Lesson {i+1}: {lesson.get('title', 'Untitled')}",
                description=lesson.get('description', ''),
                lesson_type=lesson.get('type', 'reading'),
                duration=lesson.get('duration', '10 min'),
                completed=False,
                action=f"start_lesson_{i}"
            )
            children.append(lesson_card)

        # Action buttons
        action_buttons = self.generator.hstack([
            self.generator.button("Start Course", "start_course", style="primary"),
            self.generator.button("Customize", "customize_course", style="outline")
        ], spacing=12)
        children.append(action_buttons)

        return self.generator.vstack(children, spacing=16, padding=16)

    def generate_quiz_ui(self, quiz_data: Dict[str, Any]) -> A2UIComponent:
        """Generate quiz A2UI component"""
        current_q = quiz_data.get("current_question", 1)
        total_q = quiz_data.get("total_questions", 1)
        question_data = quiz_data.get("question", {})

        return self.generator.vstack([
            # Quiz header
            self.generator.text(
                f"🧠 {quiz_data.get('title', 'Knowledge Check')}",
                font="title2"
            ),

            self.generator.text(
                f"Question {current_q} of {total_q}",
                font="subheadline",
                color="#666666"
            ),

            # Progress bar
            self.generator.progress_bar(
                (current_q / total_q) * 100,
                color="#34C759"
            ),

            # Quiz question
            self.generator.quiz(
                question=question_data.get("question", ""),
                options=question_data.get("options", []),
                correct_answer=question_data.get("correct_answer", 0),
                selected_answer=question_data.get("selected_answer"),
                action="quiz_answer"
            ),

            # Navigation
            self.generator.hstack([
                self.generator.button("Previous", "quiz_previous", style="outline")
                if current_q > 1 else self.generator.spacer(),

                self.generator.button(
                    "Next" if current_q < total_q else "Finish",
                    "quiz_next",
                    style="primary"
                )
            ], spacing=12)

        ], spacing=20, padding=16)

    def generate_explanation_ui(self, content: str, topic: str) -> A2UIComponent:
        """Generate explanation A2UI component"""
        return self.generator.vstack([
            # Topic header
            self.generator.text(
                f"💡 {topic}",
                font="title2",
                color="#007AFF"
            ),

            # Content
            self.generator.text(
                content,
                font="body",
                padding=16,
                background_color="#F8F9FA",
                corner_radius=12
            ),

            # Action suggestions
            self.generator.text("What's next?", font="headline"),

            self.generator.hstack([
                self.generator.button("Create Course", "create_course_from_topic", style="outline"),
                self.generator.button("Practice Quiz", "quiz_on_topic", style="outline"),
                self.generator.button("Deep Dive", "explain_more", style="primary")
            ], spacing=8)

        ], spacing=16, padding=16)

    def generate_note_ui(self, note_data: Dict[str, Any]) -> A2UIComponent:
        """Generate note-taking A2UI component"""
        return self.generator.vstack([
            # Note header
            self.generator.text(
                f"📝 {note_data.get('title', 'Your Note')}",
                font="title2"
            ),

            # Note content
            self.generator.text(
                note_data.get("content", ""),
                font="body",
                padding=16,
                background_color="#FFFBF0",
                corner_radius=12,
                border_width=1,
                border_color="#FFE4B5"
            ),

            # Tags if available
            self._generate_tags_ui(note_data.get("tags", [])),

            # Note actions
            self.generator.hstack([
                self.generator.button("Edit Note", "edit_note", style="outline"),
                self.generator.button("Share", "share_note", style="outline"),
                self.generator.button("Quiz from Note", "quiz_from_note", style="primary")
            ], spacing=8)

        ], spacing=16, padding=16)

    def generate_course_progress_ui(self, course_data: Dict[str, Any]) -> A2UIComponent:
        """Generate course progress A2UI component"""
        progress = course_data.get("progress", 0)
        current_lesson = course_data.get("current_lesson", {})

        return self.generator.vstack([
            # Course header with progress
            self.generator.text(
                course_data.get("title", "Course"),
                font="title"
            ),

            self.generator.progress_bar(progress, color="#007AFF"),

            self.generator.text(
                f"{int(progress)}% Complete",
                font="caption",
                color="#666666"
            ),

            # Current lesson
            self.generator.lesson_card(
                title=f"Current: {current_lesson.get('title', 'Complete!')}" if current_lesson else "Course Complete! 🎉",
                description=current_lesson.get('description', 'Congratulations!') if current_lesson else "You've finished this course",
                lesson_type=current_lesson.get('type', 'reading') if current_lesson else 'completed',
                duration=current_lesson.get('duration', '10 min') if current_lesson else 'N/A',
                completed=not bool(current_lesson),
                action="continue_lesson" if current_lesson else "course_complete"
            ),

            # Course actions
            self.generator.hstack([
                self.generator.button("View All Lessons", "view_lessons", style="outline"),
                self.generator.button("Take Quiz", "course_quiz", style="primary")
            ], spacing=12)

        ], spacing=16, padding=16)

    def generate_chat_suggestions_ui(self, suggestions: List[str]) -> A2UIComponent:
        """Generate chat suggestions A2UI component"""
        if not suggestions:
            return None

        suggestion_buttons = [
            self.generator.button(
                suggestion,
                f"suggestion_{i}",
                style="outline",
                corner_radius=16,
                padding=8
            ) for i, suggestion in enumerate(suggestions[:4])  # Max 4 suggestions
        ]

        return self.generator.vstack([
            self.generator.text(
                "💭 Try asking:",
                font="caption",
                color="#666666"
            ),

            self.generator.hstack(suggestion_buttons, spacing=8)
        ], spacing=8)

    def generate_error_ui(self, error_message: str) -> A2UIComponent:
        """Generate error A2UI component"""
        return self.generator.vstack([
            self.generator.image(
                system_name="exclamationmark.triangle",
                color="#FF9500"
            ),

            self.generator.text(
                "Something went wrong",
                font="headline"
            ),

            self.generator.text(
                error_message,
                font="body",
                color="#666666"
            ),

            self.generator.button("Try Again", "retry", style="primary")

        ], spacing=12, padding=16)

    def generate_loading_ui(self, message: str = "Thinking...") -> A2UIComponent:
        """Generate loading state A2UI component"""
        return self.generator.vstack([
            self.generator.text(message, font="body", color="#666666"),

            # Placeholder for loading animation - would be handled by iOS
            self.generator.text("⏳", font="title")

        ], spacing=8, padding=16)

    # Helper methods

    def _create_feature_card(self, icon: str, title: str, description: str, action: str) -> A2UIComponent:
        """Create a feature card component"""
        return self.generator.button(
            title="",  # Title handled by children
            action=action,
            style="outline",
            padding=16,
            corner_radius=12,
            children=[
                self.generator.vstack([
                    self.generator.text(icon, font="title"),
                    self.generator.text(title, font="headline"),
                    self.generator.text(
                        description,
                        font="caption",
                        color="#666666",
                        line_limit=2
                    )
                ], spacing=8, align="center")
            ]
        )

    def _create_stat_pill(self, value: str, label: str, icon: str) -> A2UIComponent:
        """Create a stat pill component"""
        return self.generator.hstack([
            self.generator.image(system_name=icon, color="#007AFF"),
            self.generator.vstack([
                self.generator.text(value, font="caption", color="#666666"),
                self.generator.text(label, font="caption2", color="#666666")
            ], spacing=2, align="leading")
        ], spacing=4, padding=8, background_color="#F8F9FA", corner_radius=8)

    def _generate_tags_ui(self, tags: List[str]) -> A2UIComponent:
        """Generate tags UI component"""
        if not tags:
            return self.generator.spacer(height=0)

        tag_components = [
            self.generator.text(
                f"#{tag}",
                font="caption",
                padding=6,
                background_color="#E3F2FD",
                color="#007AFF",
                corner_radius=8
            ) for tag in tags[:5]  # Max 5 tags
        ]

        return self.generator.hstack(tag_components, spacing=6)

    def mode_to_ui_component(self, mode: ChatMode, data: Dict[str, Any],
                            content: str = "") -> Optional[A2UIComponent]:
        """Convert chat mode and data to appropriate A2UI component"""
        try:
            if mode == ChatMode.QUICK_EXPLAINER:
                topic = data.get("topic", "Topic")
                return self.generate_explanation_ui(content, topic)

            elif mode == ChatMode.COURSE_PLANNER:
                return self.generate_course_creation_ui(data)

            elif mode == ChatMode.PRACTICE:
                return self.generate_quiz_ui(data)

            elif mode == ChatMode.NOTE_TAKER:
                return self.generate_note_ui(data)

            else:
                # Default to explanation UI
                return self.generate_explanation_ui(content, "Response")

        except Exception as e:
            logger.error(f"Failed to generate A2UI component: {e}")
            return self.generate_error_ui(str(e))


# Singleton instance
chat_a2ui_service = ChatA2UIService()