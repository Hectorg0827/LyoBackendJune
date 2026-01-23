"""
Chat Response Assembler

Handles post-processing of AI responses including:
- CTA de-duplication
- Length enforcement
- Response formatting
- Chip action generation
- Performance optimizations with caching and lazy loading
"""

import hashlib
import logging
import asyncio
from typing import List, Dict, Any, Optional, Set
from uuid import uuid4
from dataclasses import dataclass

from lyo_app.chat.models import ChatMode, CTAType
from lyo_app.chat.schemas import CTAItem, ChipActionItem
from lyo_app.chat.a2ui_recursive import A2UIFactory, UIComponent, ChatResponseV2, migrate_legacy_content_types
from lyo_app.cache.performance_cache import cache_result, CacheKeys, performance_monitor

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class AssemblerConfig:
    """Configuration for response assembler"""
    max_response_length: int = 4000  # Max characters in response
    max_ctas: int = 3  # Max CTAs to show
    max_chips: int = 4  # Max chip actions to show
    cta_dedup_window: int = 5  # Number of messages to check for CTA dedup
    min_response_length: int = 50  # Minimum meaningful response length
    truncation_suffix: str = "..."


DEFAULT_CONFIG = AssemblerConfig()


# =============================================================================
# CTA DEDUPLICATION
# =============================================================================

class CTADeduplicator:
    """
    Handles CTA de-duplication across conversation.
    Prevents showing the same CTA repeatedly.
    """
    
    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self._recent_ctas: List[Set[str]] = []
    
    def deduplicate(
        self,
        ctas: List[Dict[str, Any]],
        recent_ctas: Optional[List[List[Dict]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Remove CTAs that were shown recently.
        
        Args:
            ctas: List of CTAs to filter
            recent_ctas: CTAs from recent messages for deduplication
            
        Returns:
            Deduplicated list of CTAs
        """
        if not ctas:
            return []
        
        # Build set of recently shown CTA types
        recent_types: Set[str] = set()
        
        if recent_ctas:
            for msg_ctas in recent_ctas[-self.window_size:]:
                for cta in msg_ctas:
                    cta_type = cta.get("type") or cta.get("action", "")
                    recent_types.add(cta_type)
        
        # Filter out recently shown CTAs
        filtered = []
        seen_types: Set[str] = set()
        
        for cta in ctas:
            cta_type = cta.get("type") or cta.get("action", "")
            
            # Skip if shown recently (unless it's been a while)
            if cta_type in recent_types:
                continue
            
            # Skip duplicates within current batch
            if cta_type in seen_types:
                continue
            
            seen_types.add(cta_type)
            filtered.append(cta)
        
        return filtered
    
    def generate_cta_id(self, cta_type: str, context: Optional[str] = None) -> str:
        """Generate unique CTA ID"""
        data = f"{cta_type}:{context or ''}:{uuid4().hex[:8]}"
        return hashlib.md5(data.encode()).hexdigest()[:12]
    
    def prioritize_ctas(
        self,
        ctas: List[Dict[str, Any]],
        mode: ChatMode,
        max_ctas: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Prioritize CTAs based on mode and relevance.
        """
        if not ctas:
            return []
        
        # Mode-specific priority boosts
        mode_priorities = {
            ChatMode.QUICK_EXPLAINER: ["practice_now", "take_note", "explain_more"],
            ChatMode.COURSE_PLANNER: ["start_course", "customize", "practice_now"],
            ChatMode.PRACTICE: ["review_answers", "continue_learning", "take_note"],
            ChatMode.NOTE_TAKER: ["view_notes", "practice", "share"],
            ChatMode.GENERAL: ["explain_more", "practice", "create_course"],
        }
        
        priority_list = mode_priorities.get(mode, [])
        
        def get_priority(cta: Dict) -> int:
            cta_type = cta.get("type", "")
            # Explicit priority if set
            explicit = cta.get("priority", 5)
            
            # Boost based on mode
            if cta_type in priority_list:
                return priority_list.index(cta_type)
            
            return explicit + 10  # Lower priority for non-mode-specific
        
        # Sort by priority and take top N
        sorted_ctas = sorted(ctas, key=get_priority)
        
        # Add IDs if missing
        for cta in sorted_ctas:
            if "id" not in cta:
                cta["id"] = self.generate_cta_id(cta.get("type", "unknown"))
        
        return sorted_ctas[:max_ctas]


# =============================================================================
# LENGTH ENFORCEMENT
# =============================================================================

class LengthEnforcer:
    """
    Enforces response length limits with intelligent truncation.
    """
    
    def __init__(self, config: AssemblerConfig = DEFAULT_CONFIG):
        self.config = config
    
    def enforce(
        self,
        response: str,
        max_length: Optional[int] = None
    ) -> str:
        """
        Enforce length limit on response.
        
        Attempts to truncate at natural break points (sentences, paragraphs).
        """
        max_len = max_length or self.config.max_response_length
        
        if len(response) <= max_len:
            return response
        
        # Try to find a good truncation point
        truncated = self._smart_truncate(response, max_len)
        
        return truncated
    
    def _smart_truncate(self, text: str, max_length: int) -> str:
        """Truncate at natural break points"""
        suffix = self.config.truncation_suffix
        target_length = max_length - len(suffix)
        
        if target_length <= 0:
            return text[:max_length]
        
        # First, try paragraph break
        truncated = text[:target_length]
        
        # Find last paragraph break
        last_para = truncated.rfind("\n\n")
        if last_para > target_length * 0.6:  # At least 60% of content
            return truncated[:last_para].strip() + suffix
        
        # Find last sentence break
        sentence_endings = [". ", "! ", "? ", ".\n", "!\n", "?\n"]
        last_sentence = -1
        
        for ending in sentence_endings:
            pos = truncated.rfind(ending)
            if pos > last_sentence:
                last_sentence = pos + len(ending) - 1
        
        if last_sentence > target_length * 0.5:  # At least 50% of content
            return truncated[:last_sentence + 1].strip() + suffix
        
        # Fallback: truncate at word boundary
        last_space = truncated.rfind(" ")
        if last_space > target_length * 0.4:
            return truncated[:last_space].strip() + suffix
        
        # Last resort: hard truncate
        return truncated.strip() + suffix
    
    def validate_minimum(self, response: str) -> bool:
        """Check if response meets minimum length"""
        return len(response.strip()) >= self.config.min_response_length


# =============================================================================
# CHIP ACTION GENERATOR
# =============================================================================

class ChipActionGenerator:
    """Generates contextual chip actions based on response and mode"""
    
    def generate(
        self,
        mode: ChatMode,
        response: str,
        context: Optional[Dict[str, Any]] = None,
        max_chips: int = 4
    ) -> List[ChipActionItem]:
        """Generate chip actions for the response"""
        chips = []
        
        # Mode-specific chips
        mode_chips = self._get_mode_chips(mode)
        chips.extend(mode_chips)
        
        # Context-specific chips
        if context:
            context_chips = self._get_context_chips(context)
            chips.extend(context_chips)
        
        # Content-specific chips based on response
        content_chips = self._analyze_response_for_chips(response, mode)
        chips.extend(content_chips)
        
        # Deduplicate and limit
        seen_actions = set()
        unique_chips = []
        
        for chip in chips:
            if chip.action not in seen_actions:
                seen_actions.add(chip.action)
                unique_chips.append(chip)
        
        return unique_chips[:max_chips]
    
    def _get_mode_chips(self, mode: ChatMode) -> List[ChipActionItem]:
        """Get standard chips for a mode"""
        mode_chips = {
            ChatMode.QUICK_EXPLAINER: [
                ChipActionItem(id=str(uuid4())[:8], action="explain_more", label="Explain More", icon="expand"),
                ChipActionItem(id=str(uuid4())[:8], action="practice", label="Practice", icon="quiz"),
                ChipActionItem(id=str(uuid4())[:8], action="take_note", label="Take Note", icon="note"),
            ],
            ChatMode.COURSE_PLANNER: [
                ChipActionItem(id=str(uuid4())[:8], action="practice", label="Quiz Me", icon="quiz"),
                ChipActionItem(id=str(uuid4())[:8], action="take_note", label="Save Plan", icon="note"),
            ],
            ChatMode.PRACTICE: [
                ChipActionItem(id=str(uuid4())[:8], action="explain_more", label="Explain Answer", icon="explain"),
                ChipActionItem(id=str(uuid4())[:8], action="practice", label="More Questions", icon="quiz"),
            ],
            ChatMode.NOTE_TAKER: [
                ChipActionItem(id=str(uuid4())[:8], action="practice", label="Practice", icon="quiz"),
                ChipActionItem(id=str(uuid4())[:8], action="explain_more", label="Expand", icon="expand"),
            ],
            ChatMode.GENERAL: [
                ChipActionItem(id=str(uuid4())[:8], action="explain_more", label="Tell Me More", icon="expand"),
                ChipActionItem(id=str(uuid4())[:8], action="practice", label="Quiz Me", icon="quiz"),
                ChipActionItem(id=str(uuid4())[:8], action="take_note", label="Take Note", icon="note"),
            ],
        }
        
        return mode_chips.get(mode, mode_chips[ChatMode.GENERAL])
    
    def _get_context_chips(self, context: Dict[str, Any]) -> List[ChipActionItem]:
        """Get chips based on context"""
        chips = []
        
        # If there's a course in context, add course-related chips
        if context.get("course_id"):
            chips.append(ChipActionItem(
                id=str(uuid4())[:8],
                action="continue_course",
                label="Continue Course",
                icon="course"
            ))
        
        # If there are notes in context
        if context.get("has_notes"):
            chips.append(ChipActionItem(
                id=str(uuid4())[:8],
                action="review_notes",
                label="Review Notes",
                icon="notes"
            ))
        
        return chips
    
    def _analyze_response_for_chips(
        self,
        response: str,
        mode: ChatMode
    ) -> List[ChipActionItem]:
        """Analyze response content to suggest relevant chips"""
        chips = []
        response_lower = response.lower()
        
        # If response mentions examples or practice
        if "example" in response_lower or "practice" in response_lower:
            chips.append(ChipActionItem(
                id=str(uuid4())[:8],
                action="practice",
                label="Try Examples",
                icon="practice"
            ))
        
        # If response is educational content
        if mode in [ChatMode.QUICK_EXPLAINER, ChatMode.GENERAL]:
            if any(word in response_lower for word in ["concept", "understand", "learn"]):
                chips.append(ChipActionItem(
                    id=str(uuid4())[:8],
                    action="create_course",
                    label="Create Course",
                    icon="course"
                ))
        
        return chips


# =============================================================================
# RESPONSE ASSEMBLER
# =============================================================================

class ResponseAssembler:
    """
    Main class for assembling final chat responses.
    Handles all post-processing including deduplication and length enforcement.
    """
    
    def __init__(self, config: AssemblerConfig = DEFAULT_CONFIG):
        self.config = config
        self.cta_deduplicator = CTADeduplicator(config.cta_dedup_window)
        self.length_enforcer = LengthEnforcer(config)
        self.chip_generator = ChipActionGenerator()
    
    def assemble(
        self,
        response: str,
        mode: ChatMode,
        ctas: Optional[List[Dict[str, Any]]] = None,
        chips: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
        recent_ctas: Optional[List[List[Dict]]] = None,
        max_length: Optional[int] = None,
        include_ctas: bool = True,
        include_chips: bool = True
    ) -> Dict[str, Any]:
        """
        Assemble the final response with all post-processing.
        
        Args:
            response: Raw AI response
            mode: Chat mode used
            ctas: Raw CTAs to process
            chips: Raw chip actions
            context: Conversation context
            recent_ctas: CTAs from recent messages for deduplication
            max_length: Override max response length
            include_ctas: Whether to include CTAs
            include_chips: Whether to include chip actions
            
        Returns:
            Assembled response with processed CTAs and chips
        """
        # 1. Enforce length on response
        processed_response = self.length_enforcer.enforce(response, max_length)
        
        # 2. Process CTAs
        processed_ctas: List[CTAItem] = []
        if include_ctas and ctas:
            # Deduplicate
            deduped_ctas = self.cta_deduplicator.deduplicate(ctas, recent_ctas)
            
            # Prioritize and limit
            prioritized_ctas = self.cta_deduplicator.prioritize_ctas(
                deduped_ctas, mode, self.config.max_ctas
            )
            
            # Convert to CTAItem
            for cta in prioritized_ctas:
                processed_ctas.append(CTAItem(
                    id=cta.get("id", str(uuid4())[:12]),
                    type=cta.get("type", "action"),
                    label=cta.get("label", "Action"),
                    action=cta.get("action", ""),
                    data=cta.get("data"),
                    priority=cta.get("priority", 0)
                ))
        
        # 3. Process chip actions
        processed_chips: List[ChipActionItem] = []
        if include_chips:
            if chips:
                # Use provided chips
                for chip in chips[:self.config.max_chips]:
                    processed_chips.append(ChipActionItem(
                        id=chip.get("id", str(uuid4())[:8]),
                        action=chip.get("action", ""),
                        label=chip.get("label", ""),
                        icon=chip.get("icon")
                    ))
            else:
                # Generate chips based on mode and context
                processed_chips = self.chip_generator.generate(
                    mode, processed_response, context, self.config.max_chips
                )
        
        return {
            "response": processed_response,
            "ctas": processed_ctas,
            "chip_actions": processed_chips,
            "was_truncated": len(response) != len(processed_response),
            "original_length": len(response),
            "processed_length": len(processed_response)
        }
    
    def validate_response(self, response: str) -> Dict[str, Any]:
        """Validate a response meets quality requirements"""
        issues = []

        # Check minimum length
        if not self.length_enforcer.validate_minimum(response):
            issues.append("Response too short")

        # Check for common issues
        if response.strip().startswith("I apologize") or response.strip().startswith("I'm sorry"):
            issues.append("Response appears to be an error message")

        # Check for incomplete JSON (if response should be structured)
        if "{" in response and "}" not in response:
            issues.append("Incomplete JSON structure")

        return {
            "is_valid": len(issues) == 0,
            "issues": issues
        }

    # =============================================================================
    # A2UI FACTORY METHODS
    # =============================================================================

    def create_weather_ui(self, weather_data: Dict[str, Any]) -> UIComponent:
        """Create a comprehensive weather display using recursive A2UI"""
        return A2UIFactory.card(
            A2UIFactory.text(f"{weather_data.get('location', 'Unknown Location')}", style="headline"),
            A2UIFactory.hstack(
                A2UIFactory.text(f"{weather_data.get('temp', 'N/A')}°F", style="title"),
                A2UIFactory.vstack(
                    A2UIFactory.text(weather_data.get('condition', 'Unknown'), style="body"),
                    A2UIFactory.text(f"Feels like {weather_data.get('feels_like', 'N/A')}°F", style="caption")
                )
            ),
            A2UIFactory.divider(),
            A2UIFactory.hstack(
                A2UIFactory.text(f"Humidity: {weather_data.get('humidity', 'N/A')}%", style="caption"),
                A2UIFactory.text(f"Wind: {weather_data.get('wind_speed', 'N/A')} mph", style="caption")
            ),
            A2UIFactory.button("Refresh Weather", "refresh_weather", variant="primary"),
            A2UIFactory.spacer(height=8),
            A2UIFactory.text("Last updated: Just now", style="caption", alignment="center"),
            title="Current Weather"
        )

    def create_course_overview_ui(self, course_data: Dict[str, Any]) -> UIComponent:
        """Create a comprehensive course overview with nested components"""
        modules = []
        for i, module in enumerate(course_data.get('modules', [])):
            module_card = A2UIFactory.card(
                A2UIFactory.text(module.get('description', 'No description available'), style="body"),
                A2UIFactory.spacer(height=8),
                A2UIFactory.hstack(
                    A2UIFactory.text(f"{module.get('lessons', 0)} lessons", style="caption"),
                    A2UIFactory.text("•", style="caption"),
                    A2UIFactory.text(f"{module.get('duration', 0)} mins", style="caption")
                ),
                A2UIFactory.spacer(height=12),
                A2UIFactory.button(
                    "Start Module" if module.get('status') != 'completed' else "Review Module",
                    f"start_module_{module.get('id', i)}",
                    variant="primary" if module.get('status') != 'completed' else "secondary"
                ),
                title=module.get('title', f'Module {i+1}')
            )
            modules.append(module_card)

        return A2UIFactory.vstack(
            A2UIFactory.text(course_data.get('title', 'Course'), style="title", alignment="center"),
            A2UIFactory.text(course_data.get('description', 'Learn new skills'), style="body", alignment="center"),
            A2UIFactory.spacer(height=16),
            A2UIFactory.hstack(
                A2UIFactory.text(f"{course_data.get('total_modules', 0)} modules", style="caption"),
                A2UIFactory.text("•", style="caption"),
                A2UIFactory.text(f"{course_data.get('estimated_time', 0)} hours", style="caption")
            ),
            A2UIFactory.divider(),
            *modules,
            A2UIFactory.spacer(height=16),
            A2UIFactory.button("Save to My Courses", "save_course", variant="ghost"),
            spacing=16.0
        )

    def create_quiz_results_ui(self, quiz_data: Dict[str, Any]) -> UIComponent:
        """Create an interactive quiz results display"""
        score = quiz_data.get('score', 0)
        total = quiz_data.get('total_questions', 0)
        percentage = int((score / total) * 100) if total > 0 else 0

        # Create question cards
        question_cards = []
        for i, question in enumerate(quiz_data.get('questions', [])):
            is_correct = question.get('user_correct', False)
            card = A2UIFactory.card(
                A2UIFactory.text(question.get('question', ''), style="body"),
                A2UIFactory.spacer(height=8),
                A2UIFactory.hstack(
                    A2UIFactory.text("✓" if is_correct else "✗", style="headline",
                                   color="#22c55e" if is_correct else "#ef4444"),
                    A2UIFactory.text(
                        question.get('user_answer', 'No answer'),
                        style="body",
                        color="#22c55e" if is_correct else "#ef4444"
                    )
                ),
                A2UIFactory.text(f"Correct answer: {question.get('correct_answer', '')}", style="caption"),
                A2UIFactory.text(question.get('explanation', ''), style="caption") if question.get('explanation') else A2UIFactory.spacer(height=0),
                title=f"Question {i+1}"
            )
            question_cards.append(card)

        return A2UIFactory.vstack(
            A2UIFactory.text("Quiz Results", style="title", alignment="center"),
            A2UIFactory.spacer(height=16),
            A2UIFactory.card(
                A2UIFactory.text(f"{score}/{total}", style="title", alignment="center",
                               color="#22c55e" if percentage >= 70 else "#ef4444"),
                A2UIFactory.text(f"{percentage}%", style="headline", alignment="center",
                               color="#22c55e" if percentage >= 70 else "#ef4444"),
                A2UIFactory.text(
                    "Great job!" if percentage >= 70 else "Keep practicing!",
                    style="body", alignment="center"
                ),
                title="Your Score"
            ),
            A2UIFactory.divider(),
            *question_cards,
            A2UIFactory.spacer(height=16),
            A2UIFactory.hstack(
                A2UIFactory.button("Retake Quiz", "retake_quiz", variant="secondary"),
                A2UIFactory.button("Continue Learning", "continue_learning", variant="primary")
            ),
            spacing=16.0
        )

    def create_study_plan_ui(self, plan_data: Dict[str, Any]) -> UIComponent:
        """Create a personalized study plan interface"""
        topics = []
        for topic in plan_data.get('topics', []):
            difficulty = topic.get('difficulty', 'medium')
            difficulty_color = {
                'easy': '#22c55e',
                'medium': '#f59e0b',
                'hard': '#ef4444'
            }.get(difficulty, '#6b7280')

            topic_card = A2UIFactory.card(
                A2UIFactory.hstack(
                    A2UIFactory.vstack(
                        A2UIFactory.text(topic.get('title', 'Topic'), style="headline"),
                        A2UIFactory.text(f"{topic.get('estimated_time', 0)} minutes", style="caption")
                    ),
                    A2UIFactory.text(difficulty.title(), style="caption", color=difficulty_color)
                ),
                A2UIFactory.text(topic.get('description', ''), style="body"),
                A2UIFactory.spacer(height=12),
                A2UIFactory.button(
                    f"Start {topic.get('title', 'Topic')}",
                    f"start_topic_{topic.get('id', '')}",
                    variant="primary"
                )
            )
            topics.append(topic_card)

        return A2UIFactory.vstack(
            A2UIFactory.text("Your Personalized Study Plan", style="title", alignment="center"),
            A2UIFactory.text(plan_data.get('description', 'Tailored to your learning goals'),
                           style="body", alignment="center"),
            A2UIFactory.spacer(height=16),
            A2UIFactory.card(
                A2UIFactory.hstack(
                    A2UIFactory.vstack(
                        A2UIFactory.text(str(len(plan_data.get('topics', []))), style="title", alignment="center"),
                        A2UIFactory.text("Topics", style="caption", alignment="center")
                    ),
                    A2UIFactory.vstack(
                        A2UIFactory.text(f"{plan_data.get('total_time', 0)}", style="title", alignment="center"),
                        A2UIFactory.text("Minutes", style="caption", alignment="center")
                    ),
                    A2UIFactory.vstack(
                        A2UIFactory.text(f"{plan_data.get('difficulty_level', 'Mixed')}", style="title", alignment="center"),
                        A2UIFactory.text("Level", style="caption", alignment="center")
                    )
                ),
                title="Study Overview"
            ),
            A2UIFactory.divider(),
            *topics,
            A2UIFactory.spacer(height=16),
            A2UIFactory.button("Customize Plan", "customize_plan", variant="ghost"),
            spacing=16.0
        )

    def create_course_preview_ui(self, course_data: Dict[str, Any]) -> UIComponent:
        """Create a course preview UI using AI Classroom data"""
        return A2UIFactory.vstack(
            A2UIFactory.text("🎓 Course Available", style="headline", alignment="center"),
            A2UIFactory.spacer(height=8),

            A2UIFactory.course_preview(
                course_id=course_data.get('id', ''),
                title=course_data.get('title', 'Untitled Course'),
                description=course_data.get('description', 'No description available'),
                subject=course_data.get('subject', 'General'),
                grade_band=course_data.get('grade_band', 'All Levels'),
                estimated_minutes=course_data.get('estimated_minutes', 60),
                total_nodes=course_data.get('total_nodes', 10),
                thumbnail_url=course_data.get('thumbnail_url')
            ),

            A2UIFactory.text("Ready to start learning?", style="body", alignment="center"),

            A2UIFactory.hstack(
                A2UIFactory.button("Preview Course", "preview_course", variant="secondary"),
                A2UIFactory.button("Start Learning", "start_course", variant="primary")
            ),

            spacing=16.0,
            alignment="center"
        )

    def create_learning_progress_ui(self, progress_data: Dict[str, Any]) -> UIComponent:
        """Create a learning progress display using AI Classroom data"""
        current_node = progress_data.get('current_node', 0)
        total_nodes = progress_data.get('total_nodes', 1)

        return A2UIFactory.vstack(
            A2UIFactory.progress_tracker(
                course_title=progress_data.get('course_title', 'Your Course'),
                current_node=current_node,
                total_nodes=total_nodes,
                current_node_title=progress_data.get('current_node_title'),
                next_node_title=progress_data.get('next_node_title')
            ),

            A2UIFactory.card(
                A2UIFactory.text("Keep Learning", style="headline"),
                A2UIFactory.text(
                    progress_data.get('motivation_message',
                    f"You're making great progress! {current_node} of {total_nodes} lessons completed."),
                    style="body"
                ),
                A2UIFactory.spacer(height=12),
                A2UIFactory.button("Continue Learning", "continue_learning", variant="primary"),
                title="Your Progress"
            ),

            spacing=16.0
        )

    def create_interactive_lesson_ui(self, lesson_data: Dict[str, Any]) -> UIComponent:
        """Create an interactive lesson UI using AI Classroom data"""
        lesson_components = [
            A2UIFactory.text(lesson_data.get('title', 'Lesson'), style="title", alignment="center"),
            A2UIFactory.spacer(height=12)
        ]

        # Add the main lesson component
        lesson_components.append(
            A2UIFactory.interactive_lesson(
                lesson_id=lesson_data.get('id', ''),
                title=lesson_data.get('title', 'Lesson'),
                content=lesson_data.get('content', 'No content available'),
                lesson_type=lesson_data.get('type', 'text'),
                media_url=lesson_data.get('media_url'),
                duration_seconds=lesson_data.get('duration_seconds'),
                has_quiz=lesson_data.get('has_quiz', False)
            )
        )

        # Add action buttons
        action_buttons = []
        if lesson_data.get('has_quiz', False):
            action_buttons.append(A2UIFactory.button("Take Quiz", "take_quiz", variant="primary"))

        action_buttons.append(A2UIFactory.button("Continue", "continue_lesson", variant="secondary"))

        if action_buttons:
            lesson_components.append(A2UIFactory.spacer(height=16))
            lesson_components.append(A2UIFactory.hstack(*action_buttons))

        return A2UIFactory.vstack(*lesson_components, spacing=16.0, alignment="center")

    def create_course_completion_ui(self, completion_data: Dict[str, Any]) -> UIComponent:
        """Create a course completion celebration UI"""
        return A2UIFactory.vstack(
            A2UIFactory.text("🎉 Congratulations!", style="title", alignment="center"),
            A2UIFactory.spacer(height=8),

            A2UIFactory.card(
                A2UIFactory.text(f"You completed: {completion_data.get('course_title', 'the course')}", style="headline"),
                A2UIFactory.divider(),
                A2UIFactory.hstack(
                    A2UIFactory.vstack(
                        A2UIFactory.text(f"{completion_data.get('total_nodes', 0)}", style="title", alignment="center"),
                        A2UIFactory.text("Lessons", style="caption", alignment="center")
                    ),
                    A2UIFactory.vstack(
                        A2UIFactory.text(f"{completion_data.get('time_spent', 0)}m", style="title", alignment="center"),
                        A2UIFactory.text("Time", style="caption", alignment="center")
                    ),
                    A2UIFactory.vstack(
                        A2UIFactory.text(f"{completion_data.get('score', 100)}%", style="title", alignment="center"),
                        A2UIFactory.text("Score", style="caption", alignment="center")
                    )
                ),
                title="Course Complete!"
            ),

            A2UIFactory.text("What would you like to do next?", style="body", alignment="center"),

            A2UIFactory.hstack(
                A2UIFactory.button("View Certificate", "view_certificate", variant="secondary"),
                A2UIFactory.button("Find More Courses", "explore_courses", variant="primary")
            ),

            spacing=16.0,
            alignment="center"
        )

    # =============================================================================
    # PERFORMANCE-ENHANCED METHODS
    # =============================================================================

    @cache_result(CacheKeys.UI_LAYOUT, ttl=1800)  # Cache for 30 minutes
    async def create_course_preview_ui_cached(self, course_data: Dict[str, Any]) -> UIComponent:
        """Create course preview UI with caching"""
        performance_monitor.start_timing("course_preview_ui", course_data.get("course_id", "unknown"))

        try:
            # Import here to avoid circular imports
            from lyo_app.cache.lazy_components import component_loader

            # Use lazy loading for course data
            course_id = course_data.get("course_id")
            if course_id:
                optimized_course = await component_loader.load_course_preview_lazy(course_id, **course_data)
                ui_component = A2UIFactory.from_dict(optimized_course) if isinstance(optimized_course, dict) else optimized_course
            else:
                ui_component = self.create_course_preview_ui(course_data)

            duration = performance_monitor.end_timing("course_preview_ui", course_data.get("course_id", "unknown"))
            logger.debug(f"Course preview UI created in {duration:.3f}s")

            return ui_component

        except Exception as e:
            logger.error(f"Course preview UI creation failed: {e}")
            return self._create_fallback_ui("course_preview")

    @cache_result(CacheKeys.UI_LAYOUT, ttl=300)  # Cache for 5 minutes (shorter for progress)
    async def create_learning_progress_ui_cached(self, progress_data: Dict[str, Any]) -> UIComponent:
        """Create learning progress UI with caching"""
        user_id = progress_data.get("user_id", "unknown")
        course_id = progress_data.get("course_id", "unknown")

        performance_monitor.start_timing("progress_ui", f"{user_id}:{course_id}")

        try:
            # Import here to avoid circular imports
            from lyo_app.cache.lazy_components import component_loader

            # Use lazy loading for progress data
            optimized_progress = await component_loader.load_learning_progress_lazy(user_id, course_id)
            ui_component = A2UIFactory.from_dict(optimized_progress) if isinstance(optimized_progress, dict) else optimized_progress

            duration = performance_monitor.end_timing("progress_ui", f"{user_id}:{course_id}")
            logger.debug(f"Progress UI created in {duration:.3f}s")

            return ui_component

        except Exception as e:
            logger.error(f"Progress UI creation failed: {e}")
            return self._create_fallback_ui("progress_tracker")

    async def create_interactive_lesson_ui_cached(self, lesson_data: Dict[str, Any]) -> UIComponent:
        """Create interactive lesson UI with lazy loading"""
        lesson_id = lesson_data.get("lesson_id", "unknown")

        performance_monitor.start_timing("lesson_ui", lesson_id)

        try:
            # Import here to avoid circular imports
            from lyo_app.cache.lazy_components import component_loader

            # Use lazy loading with prefetching
            optimized_lesson = await component_loader.load_interactive_lesson_lazy(lesson_id, **lesson_data)
            ui_component = A2UIFactory.from_dict(optimized_lesson) if isinstance(optimized_lesson, dict) else optimized_lesson

            duration = performance_monitor.end_timing("lesson_ui", lesson_id)
            logger.debug(f"Lesson UI created in {duration:.3f}s")

            return ui_component

        except Exception as e:
            logger.error(f"Lesson UI creation failed: {e}")
            return self._create_fallback_ui("interactive_lesson")

    async def assemble_response_with_progressive_rendering(
        self,
        response: str,
        ui_layout: Optional[UIComponent] = None,
        **kwargs
    ) -> ChatResponseV2:
        """Assemble response with progressive rendering optimizations"""
        performance_monitor.start_timing("response_assembly", "progressive")

        try:
            # Import here to avoid circular imports
            from lyo_app.cache.lazy_components import progressive_renderer

            # Apply progressive rendering if UI layout is complex
            if ui_layout and self._is_complex_layout(ui_layout):
                optimized_layout = await progressive_renderer.render_progressive(
                    ui_layout.model_dump() if hasattr(ui_layout, 'model_dump') else ui_layout
                )
                ui_layout = A2UIFactory.from_dict(optimized_layout)

            # Standard assembly with optimized components
            assembled_response = ChatResponseV2(
                response=response,
                ui_layout=ui_layout,
                session_id=kwargs.get('session_id'),
                conversation_id=kwargs.get('conversation_id'),
                response_mode=kwargs.get('response_mode', 'standard')
            )

            duration = performance_monitor.end_timing("response_assembly", "progressive")
            logger.debug(f"Progressive response assembly completed in {duration:.3f}s")

            return assembled_response

        except Exception as e:
            logger.error(f"Progressive response assembly failed: {e}")
            # Fallback to standard assembly
            return ChatResponseV2(
                response=response,
                ui_layout=ui_layout,
                **kwargs
            )

    async def batch_create_ui_components(
        self,
        component_specs: List[Dict[str, Any]],
        max_concurrent: int = 3
    ) -> List[UIComponent]:
        """Create multiple UI components concurrently"""
        performance_monitor.start_timing("batch_ui_creation", f"batch_{len(component_specs)}")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def create_component(spec: Dict[str, Any]) -> UIComponent:
            async with semaphore:
                component_type = spec.get("type")

                if component_type == "course_preview":
                    return await self.create_course_preview_ui_cached(spec)
                elif component_type == "progress_tracker":
                    return await self.create_learning_progress_ui_cached(spec)
                elif component_type == "interactive_lesson":
                    return await self.create_interactive_lesson_ui_cached(spec)
                else:
                    # Use factory for simple components
                    return A2UIFactory.from_dict(spec)

        try:
            # Execute all component creation tasks concurrently
            components = await asyncio.gather(
                *[create_component(spec) for spec in component_specs],
                return_exceptions=True
            )

            # Handle exceptions and provide fallbacks
            result_components = []
            for i, component in enumerate(components):
                if isinstance(component, Exception):
                    logger.error(f"Component creation failed for spec {i}: {component}")
                    result_components.append(self._create_fallback_ui("error"))
                else:
                    result_components.append(component)

            duration = performance_monitor.end_timing("batch_ui_creation", f"batch_{len(component_specs)}")
            logger.debug(f"Batch UI creation completed in {duration:.3f}s")

            return result_components

        except Exception as e:
            logger.error(f"Batch UI creation failed: {e}")
            return [self._create_fallback_ui("error") for _ in component_specs]

    def _is_complex_layout(self, ui_layout: UIComponent) -> bool:
        """Determine if layout is complex enough to benefit from progressive rendering"""
        if not ui_layout:
            return False

        # Check if layout has nested children beyond a threshold
        def count_nested_components(component, depth=0):
            if depth > 3:  # Arbitrary complexity threshold
                return True

            if hasattr(component, 'children') and component.children:
                for child in component.children:
                    if count_nested_components(child, depth + 1):
                        return True

            return False

        return count_nested_components(ui_layout)

    def _create_fallback_ui(self, component_type: str) -> UIComponent:
        """Create fallback UI component for errors"""
        return A2UIFactory.card(
            A2UIFactory.text(
                f"Content temporarily unavailable",
                style="body",
                alignment="center",
                color="gray"
            ),
            A2UIFactory.button(
                "Retry",
                f"retry_{component_type}",
                variant="secondary"
            ),
            title="Loading Error"
        )

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        return performance_monitor.get_performance_report()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

response_assembler = ResponseAssembler()
