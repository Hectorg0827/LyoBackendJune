"""
Smart Router for detecting user intent and routing to appropriate generation mode.
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass
import re


class IntentType(str, Enum):
    """Types of user intents"""
    FULL_COURSE = "full_course"  # Multi-lesson structured course
    QUICK_EXPLAINER = "quick_explainer"  # Single concept explanation
    QUIZ_ONLY = "quiz_only"  # Just generate quiz/assessment
    LESSON_SERIES = "lesson_series"  # Series of related lessons
    STUDY_GUIDE = "study_guide"  # Summary/study guide


@dataclass
class DetectedIntent:
    """Result of intent detection"""
    intent_type: IntentType
    confidence: float  # 0.0 - 1.0
    reasoning: str
    suggested_config: Dict[str, Any]


class SmartRouter:
    """
    Intelligently detect user intent and route to appropriate generation mode.
    
    Examples:
    - "Explain recursion" -> QUICK_EXPLAINER
    - "Create a Python course" -> FULL_COURSE
    - "Quiz me on calculus" -> QUIZ_ONLY
    """
    
    # Keywords that indicate full course
    COURSE_KEYWORDS = [
        "course", "class", "curriculum", "program", "training",
        "bootcamp", "masterclass", "certification", "learn from scratch",
        "complete guide", "step by step", "beginner to advanced"
    ]
    
    # Keywords that indicate quick explainer
    EXPLAINER_KEYWORDS = [
        "explain", "what is", "define", "how does", "introduction to",
        "overview of", "summary of", "eli5", "in simple terms"
    ]
    
    # Keywords that indicate quiz/assessment
    QUIZ_KEYWORDS = [
        "quiz", "test", "assessment", "exam", "questions",
        "practice problems", "exercises only"
    ]
    
    @classmethod
    def detect_intent(cls, user_request: str) -> DetectedIntent:
        """
        Detect what the user actually wants from their request.
        
        Args:
            user_request: The user's natural language request
            
        Returns:
            DetectedIntent with type, confidence, and suggested configuration
        """
        request_lower = user_request.lower()
        
        # Check for quick explainer indicators
        if any(kw in request_lower for kw in cls.EXPLAINER_KEYWORDS):
            # Additional check: is it asking for multi-step learning?
            if any(kw in request_lower for kw in ["step by step", "complete", "full"]):
                # Wants structured learning, not just explanation
                return cls._detect_full_course(user_request)
            
            return DetectedIntent(
                intent_type=IntentType.QUICK_EXPLAINER,
                confidence=0.85,
                reasoning="Request asks for explanation or definition of a concept",
                suggested_config={
                    "use_flash_model": True,  # Fast model sufficient
                    "skip_curriculum": True,
                    "single_response": True
                }
            )
        
        # Check for quiz-only
        if any(kw in request_lower for kw in cls.QUIZ_KEYWORDS):
            return DetectedIntent(
                intent_type=IntentType.QUIZ_ONLY,
                confidence=0.90,
                reasoning="Request specifically asks for quiz/assessment",
                suggested_config={
                    "skip_lessons": True,
                    "focus_on_assessments": True,
                    "assessment_count": cls._extract_number(request_lower, default=10)
                }
            )
        
        # Check for full course indicators
        if any(kw in request_lower for kw in cls.COURSE_KEYWORDS):
            return cls._detect_full_course(user_request)
        
        # Default heuristic: length and complexity
        word_count = len(user_request.split())
        
        if word_count < 10 and "?" in user_request:
            # Short question - probably wants quick explainer
            return DetectedIntent(
                intent_type=IntentType.QUICK_EXPLAINER,
                confidence=0.70,
                reasoning="Short question format suggests quick explanation needed",
                suggested_config={
                    "use_flash_model": True,
                    "single_response": True
                }
            )
        
        # Default to full course (safe default)
        return cls._detect_full_course(user_request)
    
    @classmethod
    def _detect_full_course(cls, user_request: str) -> DetectedIntent:
        """Helper to create full course intent"""
        request_lower = user_request.lower()
        
        # Detect level
        level = "intermediate"
        if "beginner" in request_lower or "basics" in request_lower:
            level = "beginner"
        elif "advanced" in request_lower or "expert" in request_lower:
            level = "advanced"
        
        # Detect if comprehensive
        is_comprehensive = any(
            kw in request_lower
            for kw in ["comprehensive", "complete", "full", "in-depth"]
        )
        
        return DetectedIntent(
            intent_type=IntentType.FULL_COURSE,
            confidence=0.90,
            reasoning="Request indicates desire for structured multi-lesson course",
            suggested_config={
                "quality_tier": "balanced",
                "estimated_lesson_count": 12 if is_comprehensive else 8,
                "level": level,
                "enable_all_features": True
            }
        )
    
    @classmethod
    def _extract_number(cls, text: str, default: int = 5) -> int:
        """Extract a number from text, return default if not found"""
        numbers = re.findall(r'\d+', text)
        return int(numbers[0]) if numbers else default


# Quick Explainer Mode (bypass full pipeline)
async def generate_quick_explainer(topic: str) -> Dict[str, Any]:
    """
    Generate a quick explanation without full course pipeline.
    
    Much faster and cheaper for simple concept explanations.
    """
    from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelManager
    
    # Use Flash model for speed
    model_config = ModelManager.get_model_config("quick_explainer")
    
    # Simple prompt for explanation
    prompt = f"""
    Provide a clear, concise explanation of: {topic}
    
    Format your response with:
    1. Brief definition (1-2 sentences)
    2. Key points (3-5 bullet points)
    3. Simple example
    4. Related concepts to explore
    
    Keep it accessible and engaging.
    """
    
    # Call Gemini directly (bypassing full pipeline)
    import google.generativeai as genai
    
    model = genai.GenerativeModel(
        model_name=model_config.model_name,
        generation_config={
            "temperature": 0.7,
            "max_output_tokens": 800
        }
    )
    
    response = await model.generate_content_async(prompt)
    
    return {
        "type": "quick_explainer",
        "topic": topic,
        "explanation": response.text,
        "model_used": model_config.model_name,
        "estimated_cost": 0.002  # Much cheaper than full course
    }
