"""
AI Tutor Agent - Context-Aware Teaching Assistant

MIT Architecture Engineering - Personalized Learning Support

This agent provides intelligent tutoring capabilities:
- Context-aware responses based on current lesson/course
- Adaptive teaching style based on user preferences
- Progressive hint system
- Personalized explanations
"""

import logging
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
import google.generativeai as genai

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)


class TutorPersonality(str, Enum):
    """Teaching personality styles"""
    ENCOURAGING = "encouraging"
    SOCRATIC = "socratic"
    DIRECT = "direct"
    PATIENT = "patient"
    CHALLENGING = "challenging"


class ExplanationStyle(str, Enum):
    """Explanation approach styles"""
    VISUAL = "visual"
    ANALOGICAL = "analogical"
    STEP_BY_STEP = "step_by_step"
    EXAMPLE_BASED = "example_based"
    THEORETICAL = "theoretical"


class UserContext(BaseModel):
    """User learning context for personalization"""
    user_id: str
    course_id: Optional[str] = None
    lesson_id: Optional[str] = None
    current_topic: Optional[str] = None
    completed_lessons: List[str] = Field(default_factory=list)
    quiz_scores: Dict[str, float] = Field(default_factory=dict)
    struggle_topics: List[str] = Field(default_factory=list)
    preferred_style: ExplanationStyle = ExplanationStyle.EXAMPLE_BASED
    skill_level: str = "beginner"


class TutorMessage(BaseModel):
    """A message in the tutor conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TutorSession(BaseModel):
    """A tutoring session with history"""
    session_id: str
    user_context: UserContext
    messages: List[TutorMessage] = Field(default_factory=list)
    personality: TutorPersonality = TutorPersonality.ENCOURAGING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HintLevel(str, Enum):
    """Progressive hint levels"""
    SUBTLE = "subtle"      # Just a nudge in the right direction
    MODERATE = "moderate"  # More specific guidance
    DETAILED = "detailed"  # Near-complete solution explanation


class TutorResponse(BaseModel):
    """Response from the tutor"""
    message: str
    suggestions: List[str] = Field(default_factory=list)
    related_concepts: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    follow_up_questions: List[str] = Field(default_factory=list)


class HintResponse(BaseModel):
    """Progressive hint response"""
    hint: str
    hint_level: HintLevel
    remaining_hints: int
    encouragement: str


class TutorExplanation(BaseModel):
    """Detailed explanation response"""
    explanation: str
    examples: List[str] = Field(default_factory=list)
    analogies: List[str] = Field(default_factory=list)
    key_points: List[str] = Field(default_factory=list)
    practice_suggestions: List[str] = Field(default_factory=list)


class TutorAgent:
    """
    AI Tutor Agent for personalized learning support.
    
    Features:
    - Context-aware responses based on current lesson
    - Adaptive teaching style
    - Progressive hint system
    - Personalized explanations
    """
    
    def __init__(self):
        self.name = "tutor_agent"
        self.model_name = "gemini-2.0-flash"
        self.temperature = 0.7
        self._available = False
        self.model = None
        
        # Initialize Gemini
        api_key = getattr(settings, 'google_api_key', None) or getattr(settings, 'gemini_api_key', None)
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(
                    self.model_name,
                    generation_config={
                        "temperature": self.temperature,
                        "max_output_tokens": 2048,
                    }
                )
                self._available = True
                logger.info("TutorAgent initialized successfully")
            except Exception as e:
                logger.warning(f"TutorAgent: Failed to initialize Gemini: {e}")
        else:
            logger.warning("TutorAgent: No API key found")
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    def _build_system_prompt(
        self,
        context: UserContext,
        personality: TutorPersonality
    ) -> str:
        """Build a context-aware system prompt"""
        
        personality_traits = {
            TutorPersonality.ENCOURAGING: "warm, supportive, and always finding something positive to say",
            TutorPersonality.SOCRATIC: "guiding through questions rather than direct answers",
            TutorPersonality.DIRECT: "clear, concise, and straight to the point",
            TutorPersonality.PATIENT: "taking time to explain, never rushing, very thorough",
            TutorPersonality.CHALLENGING: "pushing the student to think deeper, asking probing questions"
        }
        
        style_instructions = {
            ExplanationStyle.VISUAL: "Use diagrams, charts, and visual descriptions",
            ExplanationStyle.ANALOGICAL: "Use real-world analogies and comparisons",
            ExplanationStyle.STEP_BY_STEP: "Break everything down into numbered steps",
            ExplanationStyle.EXAMPLE_BASED: "Provide concrete examples for every concept",
            ExplanationStyle.THEORETICAL: "Focus on underlying principles and theory"
        }
        
        prompt = f"""You are an expert AI tutor named Lyo. You are {personality_traits[personality]}.

## Student Context
- Skill Level: {context.skill_level}
- Current Topic: {context.current_topic or 'General learning'}
- Completed Lessons: {len(context.completed_lessons)} lessons
- Struggle Areas: {', '.join(context.struggle_topics) if context.struggle_topics else 'None identified yet'}

## Teaching Style
{style_instructions[context.preferred_style]}

## Guidelines
1. Always be helpful and educational
2. Adapt to the student's level
3. Provide examples when helpful
4. Encourage questions and exploration
5. If unsure, acknowledge it honestly
6. Keep responses focused and relevant
7. End with a follow-up question or suggestion when appropriate

Remember: Your goal is to help the student truly understand, not just give answers."""
        
        return prompt
    
    async def chat(
        self,
        user_message: str,
        context: UserContext,
        conversation_history: List[TutorMessage] = None,
        personality: TutorPersonality = TutorPersonality.ENCOURAGING
    ) -> TutorResponse:
        """
        Handle a chat message from the user with full context awareness.
        """
        if not self._available:
            return TutorResponse(
                message="I'm sorry, but I'm temporarily unavailable. Please try again later.",
                confidence=0.0
            )
        
        try:
            system_prompt = self._build_system_prompt(context, personality)
            
            # Build conversation history
            messages = []
            if conversation_history:
                for msg in conversation_history[-10:]:  # Last 10 messages
                    messages.append({
                        "role": "user" if msg.role == "user" else "model",
                        "parts": [msg.content]
                    })
            
            # Add current message
            messages.append({
                "role": "user",
                "parts": [user_message]
            })
            
            # Create chat session
            chat = self.model.start_chat(history=messages[:-1] if messages else [])
            
            # Generate response
            full_prompt = f"{system_prompt}\n\nStudent question: {user_message}"
            response = chat.send_message(full_prompt)
            
            response_text = response.text
            
            # Generate follow-up suggestions
            suggestions = []
            if context.current_topic:
                suggestions = [
                    f"Would you like to practice {context.current_topic} with an exercise?",
                    f"Shall I explain {context.current_topic} differently?",
                    "Do you have any other questions about this topic?"
                ]
            
            return TutorResponse(
                message=response_text,
                suggestions=suggestions[:2],
                related_concepts=[],
                confidence=0.9,
                follow_up_questions=[]
            )
            
        except Exception as e:
            logger.error(f"TutorAgent chat error: {e}")
            return TutorResponse(
                message="I encountered an issue processing your question. Could you please rephrase it?",
                confidence=0.0
            )
    
    async def get_hint(
        self,
        exercise_description: str,
        user_attempt: Optional[str],
        hint_level: HintLevel,
        context: UserContext
    ) -> HintResponse:
        """
        Provide a progressive hint for an exercise.
        """
        if not self._available:
            return HintResponse(
                hint="Hints are temporarily unavailable.",
                hint_level=hint_level,
                remaining_hints=0,
                encouragement="Keep trying!"
            )
        
        try:
            level_instructions = {
                HintLevel.SUBTLE: "Give a very subtle hint - just point them in the right direction without revealing the answer",
                HintLevel.MODERATE: "Give a moderate hint - provide more specific guidance but don't give the full solution",
                HintLevel.DETAILED: "Give a detailed hint - walk through the approach step by step, stopping just short of the complete answer"
            }
            
            prompt = f"""You are a helpful tutor providing a hint for an exercise.

Exercise: {exercise_description}

Student's attempt: {user_attempt or 'No attempt yet'}

Hint level: {hint_level.value}
Instructions: {level_instructions[hint_level]}

Provide:
1. A hint at the appropriate level
2. An encouraging message

Keep the hint concise and helpful."""

            response = self.model.generate_content(prompt)
            
            remaining = {"subtle": 2, "moderate": 1, "detailed": 0}[hint_level.value]
            
            return HintResponse(
                hint=response.text,
                hint_level=hint_level,
                remaining_hints=remaining,
                encouragement="You're making progress! Keep going!"
            )
            
        except Exception as e:
            logger.error(f"TutorAgent hint error: {e}")
            return HintResponse(
                hint="Think about what you've learned so far.",
                hint_level=hint_level,
                remaining_hints=0,
                encouragement="Keep trying!"
            )
    
    async def explain_concept(
        self,
        concept: str,
        context: UserContext,
        style: Optional[ExplanationStyle] = None
    ) -> TutorExplanation:
        """
        Provide a detailed explanation of a concept.
        """
        if not self._available:
            return TutorExplanation(
                explanation="Explanations are temporarily unavailable.",
                examples=[],
                analogies=[],
                key_points=[],
                practice_suggestions=[]
            )
        
        try:
            use_style = style or context.preferred_style
            
            style_prompts = {
                ExplanationStyle.VISUAL: "Include descriptions of diagrams or visual representations",
                ExplanationStyle.ANALOGICAL: "Use real-world analogies to explain the concept",
                ExplanationStyle.STEP_BY_STEP: "Break down the explanation into clear numbered steps",
                ExplanationStyle.EXAMPLE_BASED: "Provide multiple concrete examples",
                ExplanationStyle.THEORETICAL: "Focus on the underlying theory and principles"
            }
            
            prompt = f"""Explain the concept: {concept}

Student level: {context.skill_level}
Explanation style: {style_prompts[use_style]}

Provide:
1. A clear explanation (2-3 paragraphs)
2. 2-3 examples
3. 1-2 real-world analogies
4. 3-4 key points to remember
5. 2 practice suggestions

Format your response clearly with these sections."""

            response = self.model.generate_content(prompt)
            
            # Parse response (simplified - in production, use structured output)
            return TutorExplanation(
                explanation=response.text,
                examples=["Example from the explanation above"],
                analogies=["Analogy from the explanation above"],
                key_points=["Key point from the explanation above"],
                practice_suggestions=["Try practicing with simple examples"]
            )
            
        except Exception as e:
            logger.error(f"TutorAgent explain error: {e}")
            return TutorExplanation(
                explanation=f"Let me explain {concept}: This is a fundamental concept that you'll use frequently.",
                examples=[],
                analogies=[],
                key_points=[],
                practice_suggestions=[]
            )
    
    async def generate_encouragement(
        self,
        context: UserContext,
        recent_performance: str = "neutral"
    ) -> str:
        """
        Generate personalized encouragement based on user's progress.
        """
        try:
            completed = len(context.completed_lessons)
            
            if recent_performance == "good":
                messages = [
                    f"Excellent work! You've completed {completed} lessons and are making great progress!",
                    "You're really getting the hang of this! Keep up the amazing work!",
                    "Your dedication is paying off! I can see real improvement!"
                ]
            elif recent_performance == "struggling":
                messages = [
                    "Learning takes time, and you're doing great by sticking with it!",
                    "Every expert was once a beginner. Keep asking questions!",
                    "It's okay to find this challenging - that means you're learning!"
                ]
            else:
                messages = [
                    f"You've completed {completed} lessons - keep going!",
                    "You're making steady progress. Every step counts!",
                    "Stay curious and keep exploring!"
                ]
            
            import random
            return random.choice(messages)
            
        except Exception as e:
            logger.error(f"TutorAgent encouragement error: {e}")
            return "Keep up the great work!"


# Singleton instance
_tutor_agent: Optional[TutorAgent] = None


def get_tutor_agent() -> TutorAgent:
    """Get or create the singleton TutorAgent instance"""
    global _tutor_agent
    if _tutor_agent is None:
        _tutor_agent = TutorAgent()
    return _tutor_agent
