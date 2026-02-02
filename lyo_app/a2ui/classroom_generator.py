"""
A2UI Classroom Generator
Generates server-driven UI components for immersive AI classroom experience
"""

from typing import List, Dict, Any, Optional
from lyo_app.a2ui.a2ui_generator import A2UIGenerator
from lyo_app.a2ui.models import A2UIComponent, A2UIElementType


class ClassroomA2UIGenerator:
    """Generate A2UI components specifically for classroom/lesson rendering"""
    
    def __init__(self):
        self.a2ui = A2UIGenerator()
    
    def generate_lesson_ui(
        self,
        lesson_title: str,
        lesson_content: str,
        module_title: str,
        lesson_number: int,
        total_lessons: int,
        has_next: bool = True,
        has_previous: bool = False,
        quiz_data: Optional[Dict[str, Any]] = None
    ) -> A2UIComponent:
        """
        Generate complete UI for a single lesson.
        
        Returns a scrollable container with:
        - Hero banner with lesson title
        - Progress bar
        - Parsed content blocks
        - Quiz (if provided)
        - Navigation footer
        """
        components = []
        
        # 1. Hero Banner
        components.append(self._create_hero_banner(
            title=lesson_title,
            subtitle=f"Module: {module_title}",
            lesson_number=lesson_number
        ))
        
        # 2. Progress Bar
        components.append(self.a2ui.vstack([
            self._create_progress_indicator(
                current=lesson_number,
                total=total_lessons,
                label=f"Lesson {lesson_number} of {total_lessons}"
            )
        ], spacing=0, padding_horizontal=16, padding_top=12))
        
        # 3. Parse lesson content into A2UI blocks
        content_blocks = self._parse_content_to_blocks(lesson_content)
        components.extend(content_blocks)
        
        # 4. Quiz section (if applicable)
        if quiz_data:
            components.append(self._create_quiz_section(quiz_data))
        
        # 5. Navigation footer
        components.append(self._create_navigation_footer(
            has_next=has_next,
            has_previous=has_previous,
            is_final=(not has_next)
        ))
        
        # Wrap in scrollable container
        return self.a2ui.scroll(
            children=components,
            direction="vertical"
        )
    
    def _create_hero_banner(
        self,
        title: str,
        subtitle: str,
        lesson_number: int
    ) -> A2UIComponent:
        """Create an attractive hero banner for the lesson"""
        return self.a2ui.vstack([
            # Lesson number badge
            self.a2ui.text(
                content=f"Lesson {lesson_number}",
                font="caption",
                color="#667eea",
                align="center"
            ),
            # Title
            self.a2ui.text(
                content=title,
                font="title",
                color="#FFFFFF",
                align="center"
            ),
            # Subtitle
            self.a2ui.text(
                content=subtitle,
                font="subheadline",
                color="#9CA3AF",
                align="center"
            )
        ], spacing=8, padding_horizontal=24, padding_vertical=32)
    
    def _create_progress_indicator(
        self,
        current: int,
        total: int,
        label: str
    ) -> A2UIComponent:
        """Create progress bar showing lesson progress"""
        progress_percent = (current / total) * 100 if total > 0 else 0
        
        return self.a2ui.vstack([
            self.a2ui.text(
                content=label,
                font="caption",
                color="#9CA3AF",
                align="leading"
            ),
            # Progress bar (using hstack with colored boxes)
            self.a2ui.hstack([
                self.a2ui.vstack([], spacing=0, padding_horizontal=0, padding_vertical=4, background_color="#667eea"),
                self.a2ui.vstack([], spacing=0, padding_horizontal=0, padding_vertical=4, background_color="#374151")
            ], spacing=0)
        ], spacing=4, align="leading")
    
    def _parse_content_to_blocks(self, content: str) -> List[A2UIComponent]:
        """
        Parse markdown-style content into A2UI components.
        Handles: headers, paragraphs, code blocks, lists
        """
        blocks = []
        paragraphs = content.split("\n\n")
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Detect headers (###, ##, #)
            if para.startswith("###"):
                blocks.append(self._create_heading(
                    text=para.replace("###", "").strip(),
                    level=3
                ))
            elif para.startswith("##"):
                blocks.append(self._create_heading(
                    text=para.replace("##", "").strip(),
                    level=2
                ))
            elif para.startswith("#"):
                blocks.append(self._create_heading(
                    text=para.replace("#", "").strip(),
                    level=1
                ))
            
            # Detect code blocks (```)
            elif "```" in para:
                code_content, language = self._extract_code_block(para)
                blocks.append(self._create_code_block(code_content, language))
            
            # Detect lists (-, •, 1.)
            elif para.startswith("-") or para.startswith("•") or para.startswith("1."):
                blocks.append(self._create_list(para))
            
            # Regular paragraph
            else:
                blocks.append(self.a2ui.vstack([
                    self.a2ui.text(
                        content=para,
                        font="body",
                        color="#E5E7EB",
                        align="leading"
                    )
                ], spacing=0, padding_horizontal=16, padding_vertical=12))
        
        return blocks
    
    def _create_heading(self, text: str, level: int) -> A2UIComponent:
        """Create styled heading"""
        font_map = {1: "largeTitle", 2: "title", 3: "headline"}
        color_map = {1: "#FFFFFF", 2: "#F3F4F6", 3: "#E5E7EB"}
        
        return self.a2ui.vstack([
            self.a2ui.text(
                content=text,
                font=font_map.get(level, "headline"),
                color=color_map.get(level, "#E5E7EB"),
                align="leading"
            )
        ], spacing=0, padding_horizontal=16, padding_top=20, padding_bottom=8)
    
    def _create_code_block(self, code: str, language: str) -> A2UIComponent:
        """Create syntax-highlighted code block"""
        return self.a2ui.vstack([
            # Language badge
            self.a2ui.text(
                content=language.upper(),
                font="caption",
                color="#667eea",
                align="trailing"
            ),
            # Code content (monospace)
            self.a2ui.text(
                content=code,
                font="body",  # iOS will use monospaced variant
                color="#F3F4F6",
                align="leading"
            )
        ], spacing=8, padding_horizontal=16, padding_vertical=12, background_color="#1F2937")
    
    def _extract_code_block(self, text: str) -> tuple[str, str]:
        """Extract code content and language from markdown code block"""
        lines = text.split("\n")
        language = "text"
        code_lines = []
        in_code = False
        
        for line in lines:
            if line.startswith("```"):
                if not in_code:
                    # Starting code block, extract language
                    lang_marker = line.replace("```", "").strip()
                    if lang_marker:
                        language = lang_marker
                    in_code = True
                else:
                    # Ending code block
                    in_code = False
            elif in_code:
                code_lines.append(line)
        
        return "\n".join(code_lines), language
    
    def _create_list(self, text: str) -> A2UIComponent:
        """Create bullet list"""
        lines = text.split("\n")
        list_items = []
        
        for line in lines:
            # Remove bullet markers
            cleaned = line.lstrip("- •").lstrip("0123456789.").strip()
            if cleaned:
                list_items.append(
                    self.a2ui.hstack([
                        self.a2ui.text(content="•", font="body", color="#667eea", align="center"),
                        self.a2ui.text(content=cleaned, font="body", color="#E5E7EB", align="leading")
                    ], spacing=8, align="top")
                )
        
        return self.a2ui.vstack(
            children=list_items,
            spacing=8,
            padding_horizontal=16,
            padding_vertical=12,
            align="leading"
        )
    
    def _create_quiz_section(self, quiz_data: Dict[str, Any]) -> A2UIComponent:
        """Create interactive quiz UI"""
        question = quiz_data.get("question", "Check your understanding")
        options = quiz_data.get("options", [])
        correct_index = quiz_data.get("correct_index", 0)
        explanation = quiz_data.get("explanation", "")
        
        quiz_components = [
            # Quiz header
            self.a2ui.text(
                content="✓ Quick Check",
                font="headline",
                color="#667eea",
                align="center"
            ),
            # Question
            self.a2ui.text(
                content=question,
                font="body",
                color="#FFFFFF",
                align="leading"
            )
        ]
        
        # Options as buttons
        for idx, option in enumerate(options):
            quiz_components.append(
                self.a2ui.button(
                    title=option,
                    action=f"quiz_answer_{idx}",
                    style="secondary" if idx != correct_index else "primary",
                    full_width=True
                )
            )
        
        return self.a2ui.vstack(
            children=quiz_components,
            spacing=12,
            padding_horizontal=16,
            padding_vertical=24,
            background_color="#1F2937"
        )
    
    def _create_navigation_footer(
        self,
        has_next: bool,
        has_previous: bool,
        is_final: bool
    ) -> A2UIComponent:
        """Create navigation buttons footer"""
        buttons = []
        
        if has_previous:
            buttons.append(
                self.a2ui.button(
                    title="← Previous",
                    action="load_previous_lesson",
                    style="ghost"
                )
            )
        
        # Spacer
        buttons.append(self.a2ui.vstack([], spacing=0))
        
        if has_next:
            buttons.append(
                self.a2ui.button(
                    title="Next Lesson →",
                    action="load_next_lesson",
                    style="primary"
                )
            )
        elif is_final:
            buttons.append(
                self.a2ui.button(
                    title="🎉 Complete Course",
                    action="complete_course",
                    style="primary"
                )
            )
        
        return self.a2ui.vstack([
            self.a2ui.hstack(
                children=buttons,
                spacing=12,
                align="center"
            )
        ], spacing=0, padding_horizontal=16, padding_vertical=20, background_color="#1F1F1F")


# Global instance
classroom_a2ui_generator = ClassroomA2UIGenerator()
