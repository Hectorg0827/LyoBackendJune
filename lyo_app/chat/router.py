"""
Chat Module Router

Intelligent routing to determine which agent path to use based on
user message, mode hints, and actions.
"""

import re
import logging
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from lyo_app.chat.models import ChatMode, ChipAction
from lyo_app.chat.templates import SYSTEM_PROMPTS, RouterTemplates

logger = logging.getLogger(__name__)


# =============================================================================
# ROUTING PATTERNS
# =============================================================================

@dataclass
class RoutePattern:
    """Pattern for routing detection"""
    mode: ChatMode
    patterns: List[str]
    keywords: List[str]
    weight: float = 1.0


# Patterns for detecting intent
ROUTE_PATTERNS = [
    RoutePattern(
        mode=ChatMode.QUICK_EXPLAINER,
        patterns=[
            r"\bwhat\s+is\b",
            r"\bexplain\b",
            r"\bdefine\b",
            r"\bwhat\s+does\b",
            r"\bhow\s+does\b",
            r"\bwhat\s+are\b",
            r"\bcan\s+you\s+explain\b",
            r"\btell\s+me\s+about\b",
            r"\bwhat\'s\b",
        ],
        keywords=["explain", "define", "meaning", "concept", "understand", "clarify"],
        weight=1.0
    ),
    RoutePattern(
        mode=ChatMode.COURSE_PLANNER,
        patterns=[
            r"\bcreate\s+(?:a\s+)?course\b",
            r"\blearning\s+path\b",
            r"\bteach\s+me\b",
            r"\bcurriculum\b",
            r"\bstudy\s+plan\b",
            r"\blearn(?:ing)?\s+(?:about|plan)\b",
            r"\bcourse\s+(?:on|about|for)\b",
            r"\bstructured\s+learning\b",
            r"\bmaster\b",
        ],
        keywords=["course", "curriculum", "learning path", "study plan", "roadmap", "syllabus"],
        weight=1.2  # Slightly higher weight for explicit course requests
    ),
    RoutePattern(
        mode=ChatMode.PRACTICE,
        patterns=[
            r"\bquiz\s+me\b",
            r"\btest\s+me\b",
            r"\bpractice\b",
            r"\bexercise\b",
            r"\bquestions?\b.*\b(?:on|about)\b",
            r"\bchallenge\b",
            r"\bassessment\b",
        ],
        keywords=["quiz", "test me", "practice", "exercise", "flashcard"],
        weight=1.2
    ),
    RoutePattern(
        mode=ChatMode.TEST_PREP,
        patterns=[], # No specific patterns provided in the instruction, so keeping it empty for now.
        keywords=["test", "exam", "midterm", "final", "study for", "prepare for"],
        weight=1.5
    ),
    RoutePattern(
        mode=ChatMode.NOTE_TAKER,
        patterns=[
            r"\bsave\s+(?:this|note)\b",
            r"\btake\s+(?:a\s+)?note\b",
            r"\bremember\s+this\b",
            r"\bnote\s+(?:this|down)\b",
            r"\bsummarize\s+(?:and\s+)?save\b",
            r"\bkeep\s+(?:a\s+)?record\b",
        ],
        keywords=["note", "save", "remember", "record", "bookmark"],
        weight=1.0
    ),
]

# Action to mode mapping
ACTION_MODE_MAP = {
    ChipAction.PRACTICE: ChatMode.PRACTICE,
    ChipAction.TAKE_NOTE: ChatMode.NOTE_TAKER,
    ChipAction.EXPLAIN_MORE: ChatMode.QUICK_EXPLAINER,
    ChipAction.QUIZ_ME: ChatMode.PRACTICE,
    ChipAction.CREATE_COURSE: ChatMode.COURSE_PLANNER,
    ChipAction.SUMMARIZE: ChatMode.NOTE_TAKER,
}


# =============================================================================
# ROUTER CLASS
# =============================================================================

class ChatRouter:
    """
    Intelligent router for determining the appropriate agent path.
    
    Uses a combination of:
    1. Explicit mode hints from client
    2. Explicit actions (chip clicks)
    3. Pattern matching on message content
    4. Keyword detection
    5. Context from conversation history
    """
    
    def __init__(self):
        self.patterns = ROUTE_PATTERNS
        self._compiled_patterns: Dict[ChatMode, List[re.Pattern]] = {}
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for efficiency"""
        for route in self.patterns:
            self._compiled_patterns[route.mode] = [
                re.compile(p, re.IGNORECASE) for p in route.patterns
            ]
    
    async def route(
        self,
        message: str,
        mode_hint: Optional[str] = None,
        action: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Tuple[ChatMode, float, str]:
        """
        Determine the appropriate mode for handling this message.
        
        Returns:
            Tuple of (mode, confidence, reasoning)
        """
        # 1. Check explicit action first (highest priority like button clicks)
        if action:
            try:
                chip_action = ChipAction(action)
                if chip_action in ACTION_MODE_MAP:
                    mode = ACTION_MODE_MAP[chip_action]
                    return mode, 1.0, f"Explicit action: {action}"
            except ValueError:
                logger.warning(f"Unknown action: {action}")
        
        # 2. Check mode hint (high priority)
        if mode_hint:
            try:
                mode = ChatMode(mode_hint)
                return mode, 0.95, f"Mode hint: {mode_hint}"
            except ValueError:
                logger.warning(f"Unknown mode hint: {mode_hint}")
        
        # 3. Pattern matching (Fast Pass)
        scores = self._calculate_scores(message)
        
        if scores:
            best_mode = max(scores, key=scores.get)
            best_score = scores[best_mode]
            
            # If regex is very confident (e.g. "Quiz me"), use it.
            if best_score > 0.6: 
                return best_mode, min(best_score, 0.99), f"Strong pattern match: {best_mode.value}"
        
        # 4. Semantic Routing (Smart Pass)
        # If pattern matching was weak or inconclusive, ask the AI.
        # This provides the "Superior" understanding the user requested.
        try:
            semantic_mode, reasoning = await self._semantic_route(message, conversation_history, context=context)
            if semantic_mode:
                 return semantic_mode, 0.9, f"Semantic routing: {reasoning}"
        except Exception as e:
            logger.error(f"Semantic routing failed: {e}")
        
        # 5. Context-aware routing (Fallback)
        if conversation_history:
            context_mode = self._infer_from_history(conversation_history, message)
            if context_mode:
                return context_mode, 0.7, "Inferred from conversation context"
        
        # 6. Default to general
        return ChatMode.GENERAL, 0.5, "Default routing"
    
    async def _semantic_route(
        self, 
        message: str, 
        history: Optional[List[Dict]],
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[ChatMode], str]:
        """
        Use a fast LLM to semantically classify the user's intent.
        """
        from lyo_app.core.ai_resilience import ai_resilience_manager
        
        # Enhanced Prompt for Ambiguity & Context
        system_prompt = """
        You are the Intent Router for an AI Education App.
        Classify the user's message into one of these modes:
        
        1. QUICK_EXPLAINER: Asking for a definition, concept explanation, "what is", or expressing confusion ("I don't get it").
        2. COURSE_PLANNER: Wants to learn a broad topic, create a syllabus, plan a study path, or "teach me about X".
        3. PRACTICE: Wants a quiz, exercise, or to be challenged. Also handles "next question" or "another one" if previously practicing.
        4. TEST_PREP: Wants to study for a specific upcoming test, exam, midterm, or final.
        5. NOTE_TAKER: Wants to save, summarize, or record information.
        6. GENERAL: Casual chat, greetings, or unclear intent.
        
        CRITICAL: 
        - If the user says "Next", "Another one", or "More", look at the HISTORY. If they were quizzing, choose PRACTICE. If explaining, choose QUICK_EXPLAINER.
        - If the user says "I'm confused" or "Simpler", choose QUICK_EXPLAINER.
        
        Output valid JSON only: {"mode": "MODE_NAME", "reasoning": "brief reason"}
        """
        
        # Build strict context
        messages = [{"role": "system", "content": system_prompt}]
        
        # Inject Learner Context if available
        if context and context.get("learner_context"):
            messages.append({
                "role": "system", 
                "content": f"Learner Context: {context['learner_context']}"
            })
        
        # Add deeper history for context (Last 6 messages)
        if history:
            for msg in history[-6:]:
                content = msg.get("content", "")
                # No truncation - model needs full context for "explain *that*"
                messages.append({"role": msg.get("role", "user"), "content": content})
        
        messages.append({"role": "user", "content": message})
        
        try:
            response = await ai_resilience_manager.chat_completion(
                messages=messages,
                temperature=0.0,
                max_tokens=60, # Increased slightly for reasoning
                provider_order=["gemini-2.0-flash", "gpt-4o-mini"] # Speed is key
            )
            
            content = response.get("content", "")
            
            # Simple parsing
            import json
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0:
                data = json.loads(content[start:end])
                mode_str = data.get("mode").upper()
                reasoning = data.get("reasoning", "")
                
                # Map to ChatMode
                if mode_str == "QUICK_EXPLAINER": return ChatMode.QUICK_EXPLAINER, reasoning
                if mode_str == "COURSE_PLANNER": return ChatMode.COURSE_PLANNER, reasoning
                if mode_str == "PRACTICE": return ChatMode.PRACTICE, reasoning
                if mode_str == "TEST_PREP": return ChatMode.TEST_PREP, reasoning
                if mode_str == "NOTE_TAKER": return ChatMode.NOTE_TAKER, reasoning
                if mode_str == "GENERAL": return ChatMode.GENERAL, reasoning
                
        except Exception as e:
            logger.warning(f"Router LLM failed: {e}")
            
        return None, "Failed"

    def _calculate_scores(self, message: str) -> Dict[ChatMode, float]:
        """Calculate routing scores for each mode"""
        message_lower = message.lower()
        scores: Dict[ChatMode, float] = {}
        
        for route in self.patterns:
            score = 0.0
            
            # Pattern matching
            pattern_matches = 0
            for pattern in self._compiled_patterns[route.mode]:
                if pattern.search(message):
                    pattern_matches += 1
            
            if pattern_matches > 0:
                score += 0.4 * min(pattern_matches, 3) / 3  # Max 0.4 from patterns
            
            # Keyword matching
            keyword_matches = sum(1 for kw in route.keywords if kw.lower() in message_lower)
            if keyword_matches > 0:
                score += 0.3 * min(keyword_matches, 3) / 3  # Max 0.3 from keywords
            
            # Apply weight
            score *= route.weight
            
            if score > 0:
                scores[route.mode] = score
        
        return scores
    
    def _infer_from_history(
        self,
        history: List[Dict],
        current_message: str
    ) -> Optional[ChatMode]:
        """Infer mode from conversation history"""
        if not history:
            return None
        
        # Check recent messages for context
        recent_modes = []
        for msg in history[-5:]:  # Look at last 5 messages
            if "mode_used" in msg:
                try:
                    recent_modes.append(ChatMode(msg["mode_used"]))
                except ValueError:
                    pass
        
        if not recent_modes:
            return None
        
        # If discussing a course, continue in course mode
        if ChatMode.COURSE_PLANNER in recent_modes:
            course_keywords = ["module", "lesson", "next", "start", "begin"]
            if any(kw in current_message.lower() for kw in course_keywords):
                return ChatMode.COURSE_PLANNER
        
        # If practicing, continue practice
        if ChatMode.PRACTICE in recent_modes:
            practice_keywords = ["answer", "next question", "another", "check"]
            if any(kw in current_message.lower() for kw in practice_keywords):
                return ChatMode.PRACTICE
        
        return None
    
    def get_system_prompt(self, mode: ChatMode) -> str:
        """Get the system prompt for a given mode"""
        return SYSTEM_PROMPTS.get(mode.value, SYSTEM_PROMPTS["general"])
    
    def should_suggest_mode_switch(
        self,
        current_mode: ChatMode,
        message: str
    ) -> Optional[ChatMode]:
        """Check if we should suggest switching modes"""
        scores = self._calculate_scores(message)
        
        if scores:
            best_mode = max(scores, key=scores.get)
            if best_mode != current_mode and scores[best_mode] > 0.6:
                return best_mode
        
        return None


# =============================================================================
# MODE TRANSITION MANAGER
# =============================================================================

class ModeTransitionManager:
    """Manages smooth transitions between modes"""
    
    # Allowed transitions and their context requirements
    TRANSITIONS = {
        (ChatMode.QUICK_EXPLAINER, ChatMode.COURSE_PLANNER): "Creating a learning path based on your question",
        (ChatMode.QUICK_EXPLAINER, ChatMode.PRACTICE): "Testing your understanding",
        (ChatMode.QUICK_EXPLAINER, ChatMode.NOTE_TAKER): "Saving this explanation",
        (ChatMode.COURSE_PLANNER, ChatMode.PRACTICE): "Practice for your course",
        (ChatMode.COURSE_PLANNER, ChatMode.QUICK_EXPLAINER): "Explaining a course concept",
        (ChatMode.PRACTICE, ChatMode.QUICK_EXPLAINER): "Explaining the answer",
        (ChatMode.PRACTICE, ChatMode.NOTE_TAKER): "Saving this practice session",
        (ChatMode.NOTE_TAKER, ChatMode.QUICK_EXPLAINER): "Explaining your notes",
        (ChatMode.NOTE_TAKER, ChatMode.PRACTICE): "Practicing from your notes",
    }
    
    @classmethod
    def get_transition_context(
        cls,
        from_mode: ChatMode,
        to_mode: ChatMode
    ) -> Optional[str]:
        """Get context message for mode transition"""
        return cls.TRANSITIONS.get((from_mode, to_mode))
    
    @classmethod
    def is_valid_transition(
        cls,
        from_mode: ChatMode,
        to_mode: ChatMode
    ) -> bool:
        """Check if a transition is allowed"""
        if from_mode == to_mode:
            return True
        
        # All modes can transition to GENERAL
        if to_mode == ChatMode.GENERAL:
            return True
        
        # GENERAL can transition to any mode
        if from_mode == ChatMode.GENERAL:
            return True
        
        return (from_mode, to_mode) in cls.TRANSITIONS


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

chat_router = ChatRouter()
mode_transition_manager = ModeTransitionManager()
