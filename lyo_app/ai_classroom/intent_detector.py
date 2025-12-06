"""
Intent Detection System for Lyo's AI Classroom

Intelligently determines user intent from chat messages:
- Simple explanations → Quick inline response
- Full course requests → Multi-agent course generation
- Questions → Interactive Q&A
- Practice requests → Quiz/exercise generation

This is the "magic" that makes conversations feel natural
while triggering powerful features behind the scenes.
"""

import re
import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """Types of user intents in the AI classroom"""
    
    # Quick responses (stay in chat)
    QUICK_EXPLANATION = "quick_explanation"  # "What is X?"
    DEFINITION = "definition"                 # "Define X"
    SIMPLE_QUESTION = "simple_question"       # Yes/no, short answers
    
    # Learning content (may trigger generation)
    DEEP_DIVE = "deep_dive"                   # "Explain X in detail"
    LEARN_TOPIC = "learn_topic"               # "I want to learn X"
    FULL_COURSE = "full_course"               # "Create a course on X"
    TUTORIAL = "tutorial"                     # "Show me how to X"
    
    # Practice & Assessment
    QUIZ_REQUEST = "quiz_request"             # "Quiz me on X"
    PRACTICE = "practice"                     # "Give me exercises"
    CHALLENGE = "challenge"                   # "Challenge me"
    
    # Interactive
    CONTINUE = "continue"                     # "Keep going", "More"
    CLARIFY = "clarify"                       # "What do you mean by..."
    EXAMPLE = "example"                       # "Give me an example"
    
    # Meta
    FEEDBACK = "feedback"                     # Positive/negative reactions
    HELP = "help"                             # "What can you do?"
    UNKNOWN = "unknown"                       # Can't determine


class ConfidenceLevel(str, Enum):
    """Confidence in intent detection"""
    HIGH = "high"       # > 0.85
    MEDIUM = "medium"   # 0.6 - 0.85
    LOW = "low"         # < 0.6


@dataclass
class ChatIntent:
    """Detected intent from a user message"""
    intent_type: IntentType
    confidence: float
    confidence_level: ConfidenceLevel
    topic: Optional[str] = None
    subtopics: List[str] = field(default_factory=list)
    complexity_hint: str = "medium"  # simple, medium, complex
    requires_generation: bool = False
    suggested_response_type: str = "text"  # text, course, quiz, audio, mixed
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_type": self.intent_type.value,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "topic": self.topic,
            "subtopics": self.subtopics,
            "complexity_hint": self.complexity_hint,
            "requires_generation": self.requires_generation,
            "suggested_response_type": self.suggested_response_type,
            "extracted_entities": self.extracted_entities,
            "reasoning": self.reasoning
        }


# Intent pattern matching rules
INTENT_PATTERNS = {
    IntentType.FULL_COURSE: [
        r"(?:create|make|build|generate|design)\s+(?:a\s+)?(?:full\s+)?course\s+(?:on|about|for)\s+(.+)",
        r"(?:teach|learn|study)\s+(.+)\s+(?:from\s+scratch|completely|fully|in-depth)",
        r"(?:i\s+want|need)\s+(?:a\s+)?(?:complete|full|comprehensive)\s+course\s+(?:on|about)\s+(.+)",
        r"(?:course|curriculum)\s+(?:on|for|about)\s+(.+)",
    ],
    
    IntentType.LEARN_TOPIC: [
        r"(?:i\s+want\s+to\s+learn|teach\s+me|help\s+me\s+learn)\s+(.+)",
        r"(?:learn|study|master|understand)\s+(.+)",
        r"(?:how\s+do\s+i|how\s+can\s+i)\s+(?:learn|master|understand)\s+(.+)",
    ],
    
    IntentType.DEEP_DIVE: [
        r"(?:explain|tell\s+me\s+about)\s+(.+)\s+(?:in\s+detail|thoroughly|completely|deeply)",
        r"(?:deep\s+dive|go\s+deeper|elaborate)\s+(?:on|into|about)?\s*(.+)?",
        r"(?:i\s+want\s+to|let's)\s+(?:explore|dive\s+into)\s+(.+)",
    ],
    
    IntentType.TUTORIAL: [
        r"(?:show|teach)\s+me\s+(?:how\s+to)\s+(.+)",
        r"(?:tutorial|guide|walkthrough)\s+(?:on|for|about)\s+(.+)",
        r"(?:step\s+by\s+step|steps\s+to)\s+(.+)",
        r"(?:how\s+do\s+i|how\s+to)\s+(.+)",
    ],
    
    IntentType.QUICK_EXPLANATION: [
        r"(?:what\s+is|what's|whats|what\s+are)\s+(.+)",
        r"(?:explain|describe)\s+(.+)",
        r"(?:tell\s+me\s+about)\s+(.+)",
    ],
    
    IntentType.DEFINITION: [
        r"(?:define|definition\s+of)\s+(.+)",
        r"(?:meaning\s+of)\s+(.+)",
        r"(?:what\s+does)\s+(.+)\s+(?:mean)",
    ],
    
    IntentType.QUIZ_REQUEST: [
        r"(?:quiz|test)\s+me\s+(?:on|about)?\s*(.+)?",
        r"(?:give\s+me\s+a\s+quiz|create\s+a\s+quiz)\s+(?:on|about)?\s*(.+)?",
        r"(?:check\s+my\s+understanding|assess\s+me)\s+(?:on)?\s*(.+)?",
    ],
    
    IntentType.PRACTICE: [
        r"(?:practice|exercise|drill)\s+(?:problems?|questions?)?\s*(?:on|for|about)?\s*(.+)?",
        r"(?:give\s+me\s+exercises|more\s+practice)\s+(?:on|for)?\s*(.+)?",
        r"(?:i\s+want\s+to\s+practice)\s+(.+)",
    ],
    
    IntentType.EXAMPLE: [
        r"(?:give\s+me\s+an?\s+)?example(?:s)?\s+(?:of)?\s*(.+)?",
        r"(?:show\s+me)\s+(?:an?\s+)?example\s+(?:of)?\s*(.+)?",
        r"(?:for\s+example|like\s+what)",
    ],
    
    IntentType.CONTINUE: [
        r"(?:continue|keep\s+going|go\s+on|more|next)",
        r"(?:what's\s+next|then\s+what|and\s+then)",
        r"(?:tell\s+me\s+more|elaborate)",
    ],
    
    IntentType.CLARIFY: [
        r"(?:what\s+do\s+you\s+mean|i\s+don't\s+understand)",
        r"(?:clarify|can\s+you\s+explain)\s+(.+)?",
        r"(?:i'm\s+confused|that's\s+confusing)",
    ],
    
    IntentType.HELP: [
        r"(?:help|what\s+can\s+you\s+do)",
        r"(?:how\s+does\s+this\s+work|features)",
        r"(?:commands|options|menu)",
    ],
    
    IntentType.FEEDBACK: [
        r"(?:thanks|thank\s+you|great|awesome|perfect|good|nice)",
        r"(?:that's\s+wrong|incorrect|not\s+right|bad)",
        r"(?:i\s+liked|i\s+didn't\s+like|helpful|not\s+helpful)",
    ],
}

# Keywords that indicate course-level complexity
COURSE_KEYWORDS = {
    "comprehensive", "complete", "full", "from scratch", "in-depth",
    "start to finish", "everything about", "mastery", "certification",
    "professional", "expert level", "curriculum", "syllabus"
}

# Keywords that indicate quick response is sufficient
QUICK_KEYWORDS = {
    "briefly", "quick", "simple", "short", "basically", "in a nutshell",
    "just", "only", "simply", "fast"
}


class IntentDetector:
    """
    AI Classroom Intent Detection Engine
    
    Analyzes user messages to determine:
    1. What type of learning experience they want
    2. The topic they're interested in
    3. The complexity level needed
    4. Whether to trigger course generation
    """
    
    def __init__(self):
        self._conversation_context: Dict[str, List[Dict]] = {}
        
    def detect(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        user_preferences: Optional[Dict[str, Any]] = None
    ) -> ChatIntent:
        """
        Detect intent from a user message
        
        Args:
            message: The user's message
            conversation_history: Previous messages for context
            user_preferences: User's learning preferences
            
        Returns:
            ChatIntent with detected intent and metadata
        """
        message_lower = message.lower().strip()
        
        # Check for pattern matches
        intent_type, topic, confidence = self._match_patterns(message_lower)
        
        # Analyze complexity
        complexity = self._analyze_complexity(message_lower, conversation_history)
        
        # Determine if generation is needed
        requires_generation = self._should_generate(intent_type, complexity, message_lower)
        
        # Suggest response type
        response_type = self._suggest_response_type(intent_type, requires_generation)
        
        # Extract additional entities
        entities = self._extract_entities(message, topic)
        
        # Build reasoning
        reasoning = self._build_reasoning(intent_type, topic, complexity, requires_generation)
        
        # Calculate confidence level
        if confidence >= 0.85:
            confidence_level = ConfidenceLevel.HIGH
        elif confidence >= 0.6:
            confidence_level = ConfidenceLevel.MEDIUM
        else:
            confidence_level = ConfidenceLevel.LOW
            
        return ChatIntent(
            intent_type=intent_type,
            confidence=confidence,
            confidence_level=confidence_level,
            topic=topic,
            subtopics=entities.get("subtopics", []),
            complexity_hint=complexity,
            requires_generation=requires_generation,
            suggested_response_type=response_type,
            extracted_entities=entities,
            reasoning=reasoning
        )
        
    def _match_patterns(self, message: str) -> Tuple[IntentType, Optional[str], float]:
        """Match message against intent patterns"""
        best_match = (IntentType.UNKNOWN, None, 0.3)
        
        for intent_type, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    topic = match.group(1) if match.groups() else None
                    if topic:
                        topic = topic.strip().rstrip("?.!")
                    
                    # Higher confidence for longer, more specific patterns
                    confidence = 0.7 + (len(pattern) / 200)
                    confidence = min(confidence, 0.95)
                    
                    if confidence > best_match[2]:
                        best_match = (intent_type, topic, confidence)
                        
        return best_match
        
    def _analyze_complexity(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Analyze the complexity level needed"""
        
        # Check for complexity indicators
        if any(kw in message for kw in COURSE_KEYWORDS):
            return "complex"
        if any(kw in message for kw in QUICK_KEYWORDS):
            return "simple"
            
        # Longer messages often indicate more complex requests
        word_count = len(message.split())
        if word_count > 20:
            return "complex"
        elif word_count < 8:
            return "simple"
            
        return "medium"
        
    def _should_generate(
        self,
        intent_type: IntentType,
        complexity: str,
        message: str
    ) -> bool:
        """Determine if full content generation is needed"""
        
        # Always generate for these intents
        always_generate = {
            IntentType.FULL_COURSE,
            IntentType.QUIZ_REQUEST,
            IntentType.PRACTICE
        }
        
        if intent_type in always_generate:
            return True
            
        # Generate for deep dives and tutorials if complex
        if intent_type in {IntentType.DEEP_DIVE, IntentType.TUTORIAL}:
            if complexity in {"complex", "medium"}:
                return True
                
        # Generate for learning topics with course keywords
        if intent_type == IntentType.LEARN_TOPIC:
            if any(kw in message for kw in COURSE_KEYWORDS):
                return True
                
        return False
        
    def _suggest_response_type(
        self,
        intent_type: IntentType,
        requires_generation: bool
    ) -> str:
        """Suggest the best response format"""
        
        if intent_type == IntentType.FULL_COURSE:
            return "course"
        if intent_type in {IntentType.QUIZ_REQUEST, IntentType.PRACTICE}:
            return "quiz"
        if requires_generation:
            return "mixed"  # Text + media
        return "text"
        
    def _extract_entities(
        self,
        message: str,
        topic: Optional[str]
    ) -> Dict[str, Any]:
        """Extract additional entities from the message"""
        entities = {}
        
        # Extract time constraints
        time_patterns = [
            (r"(\d+)\s*(?:hour|hr)s?", "hours"),
            (r"(\d+)\s*(?:minute|min)s?", "minutes"),
            (r"(\d+)\s*(?:week|wk)s?", "weeks"),
            (r"(\d+)\s*(?:day)s?", "days"),
        ]
        
        for pattern, unit in time_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                entities["time_constraint"] = {
                    "value": int(match.group(1)),
                    "unit": unit
                }
                break
                
        # Extract level preferences
        level_patterns = [
            (r"(?:beginner|basics?|intro(?:duction)?)", "beginner"),
            (r"(?:intermediate|mid-level)", "intermediate"),
            (r"(?:advanced|expert|professional)", "advanced"),
        ]
        
        for pattern, level in level_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                entities["level"] = level
                break
                
        # Try to extract subtopics
        if topic:
            subtopic_patterns = [
                r"(?:especially|particularly|focusing on|including)\s+(.+?)(?:\.|$)",
                r"(?:like|such as)\s+(.+?)(?:\.|$)",
            ]
            
            for pattern in subtopic_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    subtopics_text = match.group(1)
                    # Split by common delimiters
                    subtopics = re.split(r"[,;]|\s+and\s+", subtopics_text)
                    entities["subtopics"] = [s.strip() for s in subtopics if s.strip()]
                    break
                    
        return entities
        
    def _build_reasoning(
        self,
        intent_type: IntentType,
        topic: Optional[str],
        complexity: str,
        requires_generation: bool
    ) -> str:
        """Build a human-readable reasoning string"""
        parts = []
        
        if intent_type == IntentType.FULL_COURSE:
            parts.append("User explicitly requested a full course")
        elif intent_type == IntentType.LEARN_TOPIC:
            parts.append("User wants to learn a topic")
        elif intent_type == IntentType.QUICK_EXPLANATION:
            parts.append("User wants a quick explanation")
        elif intent_type == IntentType.QUIZ_REQUEST:
            parts.append("User wants to be quizzed")
        else:
            parts.append(f"Detected intent: {intent_type.value}")
            
        if topic:
            parts.append(f"Topic: {topic}")
            
        parts.append(f"Complexity: {complexity}")
        
        if requires_generation:
            parts.append("Full content generation recommended")
        else:
            parts.append("Quick response sufficient")
            
        return ". ".join(parts)
        
    def should_trigger_course_generation(self, intent: ChatIntent) -> bool:
        """
        Convenience method to check if course generation should be triggered
        
        Use this to decide between quick chat response and full course pipeline
        """
        return (
            intent.intent_type == IntentType.FULL_COURSE or
            (intent.requires_generation and intent.complexity_hint == "complex")
        )
        
    def get_response_strategy(self, intent: ChatIntent) -> Dict[str, Any]:
        """
        Get recommended response strategy based on intent
        
        Returns configuration for the response handler
        """
        strategy = {
            "use_streaming": True,
            "include_audio": False,
            "include_images": False,
            "generate_quiz": False,
            "response_length": "medium"
        }
        
        if intent.intent_type == IntentType.FULL_COURSE:
            strategy.update({
                "use_streaming": True,
                "include_audio": True,
                "include_images": True,
                "generate_quiz": True,
                "response_length": "full_course"
            })
        elif intent.intent_type == IntentType.DEEP_DIVE:
            strategy.update({
                "include_images": True,
                "response_length": "long"
            })
        elif intent.intent_type == IntentType.QUICK_EXPLANATION:
            strategy.update({
                "response_length": "short"
            })
        elif intent.intent_type in {IntentType.QUIZ_REQUEST, IntentType.PRACTICE}:
            strategy.update({
                "generate_quiz": True,
                "response_length": "quiz"
            })
            
        return strategy


# Singleton instance
_intent_detector: Optional[IntentDetector] = None


def get_intent_detector() -> IntentDetector:
    """Get or create the intent detector singleton"""
    global _intent_detector
    if _intent_detector is None:
        _intent_detector = IntentDetector()
    return _intent_detector
