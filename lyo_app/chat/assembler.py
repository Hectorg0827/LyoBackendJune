"""
Chat Response Assembler

Handles post-processing of AI responses including:
- CTA de-duplication
- Length enforcement
- Response formatting
- Chip action generation
"""

import hashlib
import logging
from typing import List, Dict, Any, Optional, Set
from uuid import uuid4
from dataclasses import dataclass

from lyo_app.chat.models import ChatMode, CTAType
from lyo_app.chat.schemas import CTAItem, ChipActionItem

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
# SINGLETON INSTANCE
# =============================================================================

response_assembler = ResponseAssembler()
