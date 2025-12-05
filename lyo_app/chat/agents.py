"""
Chat Module Agents

Agent implementations for different chat modes:
- Quick Explainer
- Course Planner
- Practice/Quiz
- Note Taker
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from uuid import uuid4
from abc import ABC, abstractmethod

from lyo_app.chat.models import ChatMode, ChipAction
from lyo_app.chat.templates import PromptTemplates, CTATemplates, SYSTEM_PROMPTS
from lyo_app.core.ai_resilience import ai_resilience_manager

logger = logging.getLogger(__name__)


# =============================================================================
# BASE AGENT
# =============================================================================

class BaseAgent(ABC):
    """Base class for all chat agents"""
    
    mode: ChatMode = ChatMode.GENERAL
    
    def __init__(self):
        self.templates = PromptTemplates
        self.cta_templates = CTATemplates
    
    @abstractmethod
    async def process(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Process a message and return response"""
        pass
    
    async def call_ai(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        provider_order: Optional[List[str]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Call AI with resilience and tracking"""
        start_time = time.time()
        
        try:
            response = await ai_resilience_manager.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                provider_order=provider_order or ["gemini-pro", "gemini-flash", "openai"]
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return response.get("content", ""), {
                "tokens_used": response.get("usage", {}).get("total_tokens"),
                "model_used": response.get("model"),
                "latency_ms": latency_ms
            }
        
        except Exception as e:
            logger.error(f"AI call failed in {self.mode.value}: {e}")
            raise
    
    def get_system_prompt(self) -> str:
        """Get the system prompt for this agent"""
        return SYSTEM_PROMPTS.get(self.mode.value, SYSTEM_PROMPTS["general"])
    
    def get_chips(self) -> List[Dict]:
        """Get chip actions for this mode"""
        return self.cta_templates.get_chips_for_mode(self.mode.value)


# =============================================================================
# QUICK EXPLAINER AGENT
# =============================================================================

class QuickExplainerAgent(BaseAgent):
    """Agent for quick explanations and definitions"""
    
    mode = ChatMode.QUICK_EXPLAINER
    
    async def process(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Process explanation request"""
        context = context or {}
        
        # Determine depth from context or default
        depth = context.get("depth", "moderate")
        additional_context = context.get("context")
        
        # Build prompt
        prompt = self.templates.quick_explain(
            topic=message,
            depth=depth,
            context=additional_context
        )
        
        # Build messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
        ]
        
        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-6:]:  # Last 6 messages for context
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        messages.append({"role": "user", "content": prompt})
        
        # Call AI
        response_text, metadata = await self.call_ai(messages, temperature=0.7)
        
        # Parse structured response if possible
        key_points = self._extract_key_points(response_text)
        related_topics = self._extract_related_topics(response_text)
        
        return {
            "response": response_text,
            "key_points": key_points,
            "related_topics": related_topics,
            "ctas": self.cta_templates.get_ctas_for_context("after_explanation"),
            "chips": self.get_chips(),
            **metadata
        }
    
    def _extract_key_points(self, text: str) -> List[str]:
        """Extract key points from response"""
        points = []
        lines = text.split("\n")
        
        in_key_points = False
        for line in lines:
            line = line.strip()
            
            # Check for key points section
            if "key point" in line.lower() or "key takeaway" in line.lower():
                in_key_points = True
                continue
            
            # Extract bullet points
            if in_key_points and (line.startswith("-") or line.startswith("•") or line.startswith("*")):
                points.append(line.lstrip("-•* "))
            elif in_key_points and line and not line.startswith("-") and not line.startswith("•"):
                # End of key points section
                if len(points) > 0:
                    break
        
        return points[:5]  # Max 5 key points
    
    def _extract_related_topics(self, text: str) -> List[str]:
        """Extract related topics from response"""
        topics = []
        lines = text.split("\n")
        
        for line in lines:
            line = line.strip()
            if "related topic" in line.lower() or "explore next" in line.lower():
                # Next lines might be topics
                continue
            if line.startswith("-") or line.startswith("•"):
                topic = line.lstrip("-•* ")
                if len(topic) < 100:  # Reasonable topic length
                    topics.append(topic)
        
        return topics[:3]  # Max 3 related topics


# =============================================================================
# COURSE PLANNER AGENT
# =============================================================================

class CoursePlannerAgent(BaseAgent):
    """Agent for creating structured learning paths"""
    
    mode = ChatMode.COURSE_PLANNER
    
    async def process(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Process course planning request"""
        context = context or {}
        
        # Build prompt
        prompt = self.templates.course_plan(
            topic=message,
            goal=context.get("goal"),
            time_available=context.get("time_available"),
            current_level=context.get("current_level", "beginner")
        )
        
        # Build messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
        ]
        
        if conversation_history:
            for msg in conversation_history[-4:]:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        messages.append({"role": "user", "content": prompt})
        
        # Call AI with higher token limit for course generation
        response_text, metadata = await self.call_ai(
            messages, 
            temperature=0.7, 
            max_tokens=2000
        )
        
        # Try to parse JSON response
        course_data = self._parse_course_response(response_text, message)
        
        return {
            "response": response_text,
            "course_data": course_data,
            "course_id": str(uuid4()),  # Generated course ID
            "ctas": self.cta_templates.get_ctas_for_context("after_course_plan"),
            "chips": self.get_chips(),
            **metadata
        }
    
    def _parse_course_response(self, text: str, topic: str) -> Dict[str, Any]:
        """Parse course structure from AI response"""
        # Try to find JSON in response
        try:
            # Look for JSON block
            start = text.find("{")
            end = text.rfind("}") + 1
            
            if start >= 0 and end > start:
                json_str = text[start:end]
                course_data = json.loads(json_str)
                return course_data
        except json.JSONDecodeError:
            pass
        
        # Fallback: create basic structure
        return {
            "title": f"Learning Path: {topic}",
            "description": f"A structured course to learn {topic}",
            "estimated_hours": 10,
            "modules": [
                {
                    "id": "module_1",
                    "title": "Introduction",
                    "description": f"Introduction to {topic}",
                    "estimated_minutes": 60,
                    "lessons": [
                        {"id": "lesson_1_1", "title": "Getting Started", "duration_minutes": 15},
                        {"id": "lesson_1_2", "title": "Core Concepts", "duration_minutes": 20},
                    ]
                }
            ],
            "learning_objectives": [f"Understand the fundamentals of {topic}"],
            "prerequisites": []
        }


# =============================================================================
# PRACTICE AGENT
# =============================================================================

class PracticeAgent(BaseAgent):
    """Agent for generating practice questions and quizzes"""
    
    mode = ChatMode.PRACTICE
    
    async def process(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Process practice/quiz request"""
        context = context or {}
        
        # Extract topic from message or context
        topic = context.get("topic", message)
        
        # Build prompt
        prompt = self.templates.practice_quiz(
            topic=topic,
            difficulty=context.get("difficulty", "intermediate"),
            question_count=context.get("question_count", 5),
            question_types=context.get("question_types")
        )
        
        # Build messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
        ]
        
        if conversation_history:
            # For practice, include more context about what was discussed
            for msg in conversation_history[-8:]:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        messages.append({"role": "user", "content": prompt})
        
        # Call AI
        response_text, metadata = await self.call_ai(
            messages, 
            temperature=0.8,  # Slightly higher for variety
            max_tokens=1500
        )
        
        # Parse quiz response
        quiz_data = self._parse_quiz_response(response_text, topic)
        
        return {
            "response": response_text,
            "quiz_data": quiz_data,
            "quiz_id": str(uuid4()),
            "ctas": self.cta_templates.get_ctas_for_context("after_quiz"),
            "chips": self.get_chips(),
            **metadata
        }
    
    def _parse_quiz_response(self, text: str, topic: str) -> Dict[str, Any]:
        """Parse quiz structure from AI response"""
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            
            if start >= 0 and end > start:
                json_str = text[start:end]
                quiz_data = json.loads(json_str)
                return quiz_data
        except json.JSONDecodeError:
            pass
        
        # Fallback: create basic quiz structure
        return {
            "quiz_id": str(uuid4()),
            "topic": topic,
            "questions": [
                {
                    "id": "q1",
                    "question": f"What is a key concept in {topic}?",
                    "question_type": "multiple_choice",
                    "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
                    "correct_answer": "A",
                    "explanation": "This is the correct answer because...",
                    "difficulty": "intermediate"
                }
            ]
        }


# =============================================================================
# NOTE TAKER AGENT
# =============================================================================

class NoteTakerAgent(BaseAgent):
    """Agent for creating and organizing notes"""
    
    mode = ChatMode.NOTE_TAKER
    
    async def process(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Process note-taking request"""
        context = context or {}
        
        # Determine what to note
        content_to_note = message
        
        # If coming from conversation, gather context
        if conversation_history and "save" in message.lower():
            # Extract recent assistant responses to save
            recent_content = []
            for msg in conversation_history[-6:]:
                if msg.get("role") == "assistant":
                    recent_content.append(msg.get("content", ""))
            if recent_content:
                content_to_note = "\n\n".join(recent_content)
        
        # Build prompt
        prompt = self.templates.take_note(
            content=content_to_note,
            title=context.get("title"),
            extract_key_points=context.get("extract_key_points", True)
        )
        
        # Build messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": prompt}
        ]
        
        # Call AI
        response_text, metadata = await self.call_ai(
            messages, 
            temperature=0.5,  # Lower temp for more consistent formatting
            max_tokens=1000
        )
        
        # Parse note response
        note_data = self._parse_note_response(response_text)
        
        return {
            "response": response_text,
            "note_data": note_data,
            "note_id": str(uuid4()),
            "ctas": self.cta_templates.get_ctas_for_context("after_note"),
            "chips": self.get_chips(),
            **metadata
        }
    
    def _parse_note_response(self, text: str) -> Dict[str, Any]:
        """Parse note structure from AI response"""
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            
            if start >= 0 and end > start:
                json_str = text[start:end]
                note_data = json.loads(json_str)
                return note_data
        except json.JSONDecodeError:
            pass
        
        # Fallback: use the text as content
        lines = text.split("\n")
        title = lines[0][:100] if lines else "Untitled Note"
        
        return {
            "title": title.strip("#").strip(),
            "content": text,
            "summary": text[:200] + "..." if len(text) > 200 else text,
            "key_points": [],
            "tags": []
        }


# =============================================================================
# GENERAL AGENT
# =============================================================================

class GeneralAgent(BaseAgent):
    """General-purpose conversational agent"""
    
    mode = ChatMode.GENERAL
    
    async def process(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Process general conversation"""
        context = context or {}
        
        # Build messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
        ]
        
        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-10:]:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        # Add context if provided
        if context.get("context"):
            messages.append({
                "role": "system",
                "content": f"Additional context: {context['context']}"
            })
        
        messages.append({"role": "user", "content": message})
        
        # Call AI
        response_text, metadata = await self.call_ai(messages)
        
        return {
            "response": response_text,
            "ctas": self.cta_templates.get_ctas_for_context("after_explanation"),
            "chips": self.get_chips(),
            **metadata
        }


# =============================================================================
# AGENT REGISTRY
# =============================================================================

class AgentRegistry:
    """Registry of all available agents"""
    
    def __init__(self):
        self._agents: Dict[ChatMode, BaseAgent] = {
            ChatMode.QUICK_EXPLAINER: QuickExplainerAgent(),
            ChatMode.COURSE_PLANNER: CoursePlannerAgent(),
            ChatMode.PRACTICE: PracticeAgent(),
            ChatMode.NOTE_TAKER: NoteTakerAgent(),
            ChatMode.GENERAL: GeneralAgent(),
        }
    
    def get_agent(self, mode: ChatMode) -> BaseAgent:
        """Get agent for a specific mode"""
        return self._agents.get(mode, self._agents[ChatMode.GENERAL])
    
    async def process(
        self,
        mode: ChatMode,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Process a message with the appropriate agent"""
        agent = self.get_agent(mode)
        return await agent.process(message, context, conversation_history)


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

agent_registry = AgentRegistry()
