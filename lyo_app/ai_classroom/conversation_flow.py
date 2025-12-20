"""
Conversation Flow Manager for Lyo's AI Classroom

Orchestrates the entire learning experience:
- Manages conversation state across sessions
- Routes intents to appropriate handlers
- Coordinates multi-agent course generation
- Integrates TTS, images, and streaming
- Creates a Netflix/YouTube-like learning flow
"""

import asyncio
import logging
import json
import uuid
from typing import Optional, List, Dict, Any, AsyncGenerator, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .intent_detector import (
    IntentDetector,
    ChatIntent,
    IntentType,
    get_intent_detector
)

logger = logging.getLogger(__name__)


class ConversationState(str, Enum):
    """States for the conversation flow"""
    IDLE = "idle"                           # Waiting for user input
    CHATTING = "chatting"                   # Active chat conversation
    GENERATING_COURSE = "generating_course" # Multi-agent course generation
    IN_LESSON = "in_lesson"                 # User is in a lesson
    TAKING_QUIZ = "taking_quiz"             # User is taking a quiz
    REVIEWING = "reviewing"                 # User is reviewing material
    PAUSED = "paused"                       # Session paused


class MessageRole(str, Enum):
    """Message roles"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """A single message in the conversation"""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    intent: Optional[ChatIntent] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "intent": self.intent.to_dict() if self.intent else None
        }


@dataclass
class ConversationSession:
    """A conversation session with full context"""
    session_id: str
    user_id: Optional[str]
    state: ConversationState = ConversationState.IDLE
    messages: List[Message] = field(default_factory=list)
    current_topic: Optional[str] = None
    current_course_id: Optional[str] = None
    current_lesson_index: int = 0
    quiz_progress: Dict[str, Any] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_message(self, role: MessageRole, content: str, **kwargs) -> Message:
        """Add a message to the conversation"""
        message = Message(role=role, content=content, **kwargs)
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
        return message
        
    def get_context_messages(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent messages in format suitable for AI"""
        return [
            {"role": m.role.value, "content": m.content}
            for m in self.messages[-limit:]
        ]
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "state": self.state.value,
            "messages": [m.to_dict() for m in self.messages],
            "current_topic": self.current_topic,
            "current_course_id": self.current_course_id,
            "current_lesson_index": self.current_lesson_index,
            "quiz_progress": self.quiz_progress,
            "preferences": self.preferences,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class FlowResponse:
    """Response from the conversation flow"""
    content: str
    response_type: str  # text, course, lesson, quiz, mixed
    state: ConversationState
    metadata: Dict[str, Any] = field(default_factory=dict)
    audio_url: Optional[str] = None
    images: List[str] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "response_type": self.response_type,
            "state": self.state.value,
            "metadata": self.metadata,
            "audio_url": self.audio_url,
            "images": self.images,
            "actions": self.actions
        }


class ConversationManager:
    """
    The Brain of Lyo's AI Classroom
    
    Manages the complete learning experience:
    1. Receives user messages
    2. Detects intent
    3. Routes to appropriate handler
    4. Coordinates rich media generation
    5. Maintains conversation state
    """
    
    def __init__(self):
        self._sessions: Dict[str, ConversationSession] = {}
        self._intent_detector = get_intent_detector()
        
        # Handler callbacks (set by the routes)
        self._chat_handler: Optional[Callable] = None
        self._course_handler: Optional[Callable] = None
        self._quiz_handler: Optional[Callable] = None
        self._tts_handler: Optional[Callable] = None
        self._image_handler: Optional[Callable] = None
        
    def register_handlers(
        self,
        chat_handler: Optional[Callable] = None,
        course_handler: Optional[Callable] = None,
        quiz_handler: Optional[Callable] = None,
        tts_handler: Optional[Callable] = None,
        image_handler: Optional[Callable] = None
    ):
        """Register callback handlers for different content types"""
        if chat_handler:
            self._chat_handler = chat_handler
        if course_handler:
            self._course_handler = course_handler
        if quiz_handler:
            self._quiz_handler = quiz_handler
        if tts_handler:
            self._tts_handler = tts_handler
        if image_handler:
            self._image_handler = image_handler
            
    def create_session(
        self,
        user_id: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None
    ) -> ConversationSession:
        """Create a new conversation session"""
        session_id = str(uuid.uuid4())
        session = ConversationSession(
            session_id=session_id,
            user_id=user_id,
            preferences=preferences or {}
        )
        self._sessions[session_id] = session
        
        # Add welcome message
        session.add_message(
            MessageRole.ASSISTANT,
            "👋 Welcome to Lyo! I'm your AI tutor. What would you like to learn today? "
            "You can ask me questions, request explanations, or say 'create a course on [topic]' "
            "for a complete learning experience!"
        )
        
        logger.info(f"Created conversation session: {session_id}")
        return session
        
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get an existing session"""
        return self._sessions.get(session_id)
        
    def end_session(self, session_id: str) -> bool:
        """End and cleanup a session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Ended conversation session: {session_id}")
            return True
        return False
        
    async def process_message(
        self,
        session_id: str,
        user_message: str,
        include_audio: bool = False,
        user_context: str = "neutral"
    ) -> FlowResponse:
        """
        Process a user message and generate response
        
        This is the main entry point for the conversation flow.
        """
        session = self.get_session(session_id)
        if not session:
            session = self.create_session()
            
        # Add user message
        user_msg = session.add_message(MessageRole.USER, user_message)
        
        # Detect intent
        intent = self._intent_detector.detect(
            user_message,
            conversation_history=session.get_context_messages(),
            user_preferences=session.preferences
        )
        user_msg.intent = intent
        
        logger.info(f"Detected intent: {intent.intent_type.value} (confidence: {intent.confidence:.2f})")
        
        # Route based on intent
        response = await self._route_intent(session, intent, user_message, include_audio, user_context)
        
        # Add assistant response to history
        session.add_message(
            MessageRole.ASSISTANT,
            response.content,
            metadata={"response_type": response.response_type}
        )
        
        return response
        
    async def _route_intent(
        self,
        session: ConversationSession,
        intent: ChatIntent,
        message: str,
        include_audio: bool,
        user_context: str = "neutral"
    ) -> FlowResponse:
        """Route intent to appropriate handler"""
        
        # Check if course generation should be triggered
        if self._intent_detector.should_trigger_course_generation(intent):
            return await self._handle_course_request(session, intent, message)
            
        # Handle based on intent type
        if intent.intent_type in {IntentType.QUIZ_REQUEST, IntentType.PRACTICE}:
            return await self._handle_quiz_request(session, intent, message)
            
        if intent.intent_type == IntentType.CONTINUE:
            return await self._handle_continue(session)
            
        if intent.intent_type == IntentType.CLARIFY:
            return await self._handle_clarification(session, message)
            
        if intent.intent_type == IntentType.HELP:
            return self._handle_help(session)
            
        if intent.intent_type == IntentType.FEEDBACK:
            return await self._handle_feedback(session, message)
            
        # Default: Standard chat response
        return await self._handle_chat(session, intent, message, include_audio, user_context)
        
    async def _handle_chat(
        self,
        session: ConversationSession,
        intent: ChatIntent,
        message: str,
        include_audio: bool,
        user_context: str = "neutral"
    ) -> FlowResponse:
        """Handle standard chat messages"""
        session.state = ConversationState.CHATTING
        
        if intent.topic:
            session.current_topic = intent.topic
            
        # Build context-aware prompt
        context = session.get_context_messages(limit=5)
        
        # Get AI response
        if self._chat_handler:
            # Pass user_context to the handler
            content = await self._chat_handler(message, context, user_context=user_context)
        else:
            content = self._get_fallback_response(intent)
            
        response = FlowResponse(
            content=content,
            response_type="text",
            state=session.state,
            metadata={
                "intent": intent.to_dict(),
                "topic": intent.topic
            }
        )
        
        # Generate audio if requested
        if include_audio and self._tts_handler:
            try:
                audio_url = await self._tts_handler(content, intent.intent_type.value)
                response.audio_url = audio_url
            except Exception as e:
                logger.warning(f"TTS generation failed: {e}")
                
        # Generate image for deep dives
        if intent.intent_type == IntentType.DEEP_DIVE and intent.topic and self._image_handler:
            try:
                images = await self._image_handler(intent.topic, "concept_diagram")
                response.images = images
            except Exception as e:
                logger.warning(f"Image generation failed: {e}")
                
        return response
        
    async def _handle_course_request(
        self,
        session: ConversationSession,
        intent: ChatIntent,
        message: str
    ) -> FlowResponse:
        """Handle full course generation request - actually generates the course!"""
        session.state = ConversationState.GENERATING_COURSE
        
        topic = intent.topic or "your requested topic"
        session.current_topic = topic
        
        # If course handler is available, actually generate the course
        if self._course_handler:
            try:
                preferences = {
                    "level": intent.extracted_entities.get("level", "beginner"),
                    "time_constraint": intent.extracted_entities.get("time_constraint"),
                    "subtopics": intent.subtopics
                }
                
                # Actually call the course generation handler
                course_result = await self._course_handler(topic, preferences)
                
                if course_result.get("success"):
                    course_data = course_result.get("course_data", {})
                    course_response = course_data.get("response", "")
                    
                    # Build rich response with course content
                    content = (
                        f"🎓 **Course Created: {topic}**\n\n"
                        f"{course_response}\n\n"
                        f"---\n"
                        f"💡 *Ask me to explain any topic in more detail, or say 'quiz me' to test your knowledge!*"
                    )
                    
                    session.state = ConversationState.IN_LESSON
                    
                    return FlowResponse(
                        content=content,
                        response_type="course",
                        state=session.state,
                        metadata={
                            "intent": intent.to_dict(),
                            "topic": topic,
                            "generation_status": "completed",
                            "course_data": course_data
                        }
                    )
                else:
                    error_msg = course_result.get("error", "Unknown error")
                    logger.error(f"Course generation failed: {error_msg}")
                    
            except Exception as e:
                logger.error(f"Course handler error: {e}")
        
        # Fallback if course handler fails or isn't available
        # Use the chat handler to create course-like content
        if self._chat_handler:
            try:
                course_prompt = (
                    f"Create a structured mini-course on '{topic}'. Include:\n"
                    f"1. Overview and learning objectives\n"
                    f"2. Key concepts explained clearly\n"
                    f"3. Practical examples\n"
                    f"4. Summary of what was learned\n"
                    f"Format with clear sections using markdown."
                )
                context = session.get_context_messages(limit=3)
                course_content = await self._chat_handler(course_prompt, context)
                
                content = (
                    f"🎓 **Course: {topic}**\n\n"
                    f"{course_content}\n\n"
                    f"---\n"
                    f"💡 *Want to dive deeper? Ask me about any specific concept, or say 'quiz me' to test your knowledge!*"
                )
                
                session.state = ConversationState.IN_LESSON
                
                return FlowResponse(
                    content=content,
                    response_type="course",
                    state=session.state,
                    metadata={
                        "intent": intent.to_dict(),
                        "topic": topic,
                        "generation_status": "completed"
                    }
                )
            except Exception as e:
                logger.error(f"Fallback course generation error: {e}")
        
        # Ultimate fallback
        content = (
            f"🎓 I'd love to create a course on **{topic}** for you!\n\n"
            f"Unfortunately, I'm having trouble generating the full course right now. "
            f"Let me give you a quick overview instead:\n\n"
            f"**{topic}** is a fascinating subject. Ask me specific questions about it, "
            f"and I'll explain each concept in detail!"
        )
        
        return FlowResponse(
            content=content,
            response_type="course",
            state=session.state,
            metadata={
                "intent": intent.to_dict(),
                "topic": topic,
                "generation_status": "fallback"
            }
        )
        
    async def _handle_quiz_request(
        self,
        session: ConversationSession,
        intent: ChatIntent,
        message: str
    ) -> FlowResponse:
        """Handle quiz generation request"""
        session.state = ConversationState.TAKING_QUIZ
        
        topic = intent.topic or session.current_topic or "your learning"
        
        content = (
            f"📝 Let's test your knowledge of **{topic}**!\n\n"
            f"I'll give you a series of questions. Ready? Here's your first question..."
        )
        
        actions = []
        if self._quiz_handler:
            actions.append({
                "type": "generate_quiz",
                "topic": topic,
                "question_count": 5
            })
            
        return FlowResponse(
            content=content,
            response_type="quiz",
            state=session.state,
            metadata={
                "intent": intent.to_dict(),
                "topic": topic
            },
            actions=actions
        )
        
    async def _handle_continue(self, session: ConversationSession) -> FlowResponse:
        """Handle 'continue' / 'more' requests"""
        
        if session.state == ConversationState.IN_LESSON:
            content = "📖 Continuing with the next part of the lesson..."
            session.current_lesson_index += 1
        elif session.state == ConversationState.TAKING_QUIZ:
            content = "📝 Here's your next question..."
        else:
            topic = session.current_topic or "the topic"
            content = f"📚 Let me tell you more about {topic}..."
            
        return FlowResponse(
            content=content,
            response_type="text",
            state=session.state,
            actions=[{"type": "continue", "index": session.current_lesson_index}]
        )
        
    async def _handle_clarification(
        self,
        session: ConversationSession,
        message: str
    ) -> FlowResponse:
        """Handle clarification requests"""
        
        # Look at the last assistant message to clarify
        last_response = None
        for msg in reversed(session.messages):
            if msg.role == MessageRole.ASSISTANT:
                last_response = msg.content
                break
                
        content = (
            f"Let me explain that differently...\n\n"
            f"I understand that might have been confusing. "
        )
        
        if self._chat_handler:
            clarification = await self._chat_handler(
                f"Please clarify this simpler: {last_response or 'the previous topic'}. "
                f"The user asked: {message}",
                session.get_context_messages()
            )
            content += clarification
        else:
            content += "Please ask me a specific question about what you'd like clarified."
            
        return FlowResponse(
            content=content,
            response_type="text",
            state=session.state
        )
        
    def _handle_help(self, session: ConversationSession) -> FlowResponse:
        """Handle help requests"""
        content = """
🎓 **Welcome to Lyo AI Classroom!**

Here's what I can do for you:

**💬 Quick Learning**
• "What is [topic]?" - Get a quick explanation
• "Explain [concept]" - Understand something new
• "Give me an example of [topic]" - See it in practice

**📚 Deep Learning**
• "Create a course on [topic]" - Full structured curriculum
• "I want to learn [topic] from scratch" - Comprehensive guide
• "Teach me [skill] step by step" - Detailed tutorial

**📝 Practice & Quiz**
• "Quiz me on [topic]" - Test your knowledge
• "Give me exercises on [topic]" - Practice problems
• "Challenge me" - Advanced questions

**🎯 During Lessons**
• "Continue" or "Next" - Move to next section
• "Can you clarify that?" - Get simpler explanation
• "More examples please" - See additional examples

**💡 Pro Tips:**
• Be specific about your learning level (beginner/advanced)
• Mention time constraints ("in 30 minutes")
• Ask follow-up questions anytime!

What would you like to learn today?
"""
        
        return FlowResponse(
            content=content,
            response_type="text",
            state=session.state,
            metadata={"type": "help"}
        )
        
    async def _handle_feedback(
        self,
        session: ConversationSession,
        message: str
    ) -> FlowResponse:
        """Handle user feedback"""
        
        # Simple sentiment detection
        positive_words = {"thanks", "thank", "great", "awesome", "perfect", "good", "helpful", "love"}
        negative_words = {"wrong", "bad", "incorrect", "confused", "not helpful", "hate"}
        
        message_lower = message.lower()
        
        is_positive = any(word in message_lower for word in positive_words)
        is_negative = any(word in message_lower for word in negative_words)
        
        if is_positive:
            content = (
                "You're welcome! 😊 I'm glad I could help. "
                "Is there anything else you'd like to learn about?"
            )
        elif is_negative:
            content = (
                "I'm sorry that wasn't helpful. 😔 "
                "Could you tell me what was confusing? I'll try to explain it better."
            )
        else:
            content = "Thanks for your feedback! What would you like to explore next?"
            
        return FlowResponse(
            content=content,
            response_type="text",
            state=session.state,
            metadata={"feedback_type": "positive" if is_positive else "negative" if is_negative else "neutral"}
        )
        
    def _get_fallback_response(self, intent: ChatIntent) -> str:
        """Get a fallback response when handlers aren't available"""
        
        if intent.topic:
            return (
                f"I'd love to help you learn about **{intent.topic}**! "
                f"Let me prepare some information for you..."
            )
        else:
            return (
                "I'm here to help you learn! "
                "What topic would you like to explore today?"
            )
            
    async def stream_response(
        self,
        session_id: str,
        user_message: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream response for real-time experience
        
        Yields events as they happen for SSE streaming
        """
        session = self.get_session(session_id) or self.create_session()
        
        # Add user message
        session.add_message(MessageRole.USER, user_message)
        
        # Detect intent
        intent = self._intent_detector.detect(user_message)
        
        yield {
            "event": "intent_detected",
            "data": intent.to_dict()
        }
        
        # Yield typing indicator
        yield {
            "event": "typing",
            "data": {"status": "started"}
        }
        
        # Get strategy
        strategy = self._intent_detector.get_response_strategy(intent)
        
        yield {
            "event": "strategy",
            "data": strategy
        }
        
        # Generate response (simplified for streaming)
        response = await self.process_message(session_id, user_message)
        
        # Stream content word by word
        words = response.content.split()
        for i, word in enumerate(words):
            yield {
                "event": "content",
                "data": {
                    "word": word + " ",
                    "index": i,
                    "total": len(words)
                }
            }
            await asyncio.sleep(0.03)  # Natural typing feel
            
        yield {
            "event": "complete",
            "data": response.to_dict()
        }


# Singleton instance
_conversation_manager: Optional[ConversationManager] = None


async def _ai_chat_handler(message: str, context: List[Dict], user_context: str = "neutral") -> str:
    """AI chat handler using the resilience manager"""
    try:
        from lyo_app.core.ai_resilience import ai_resilience_manager
        
        # Dynamic System Prompt based on Context
        base_prompt = "You are Lyo, an expert AI tutor. "
        
        if "student" in user_context:
            system_content = (
                base_prompt + 
                "The user is a STUDENT. Focus on clear explanations, exam preparation, and academic concepts. "
                "Break down complex topics into study-friendly chunks. Use analogies suitable for coursework."
            )
        elif "professional" in user_context:
            system_content = (
                base_prompt + 
                "The user is a PROFESSIONAL. Focus on practical application, industry best practices, and efficiency. "
                "Skip the basics unless asked. Relate concepts to real-world business scenarios."
            )
        elif "hobbyist" in user_context:
            system_content = (
                base_prompt + 
                "The user is a HOBBYIST. Focus on fun, creativity, and exploration. "
                "Encourage experimentation and 'learning by doing'. Keep the tone enthusiastic."
            )
        else:
            system_content = (
                base_prompt + 
                "Be clear, encouraging, and helpful. Use markdown for formatting. "
                "Include emojis sparingly for warmth. Explain concepts step-by-step when needed."
            )

        # Build messages for AI
        messages = [
            {
                "role": "system",
                "content": system_content
            }
        ]
        
        # Add context messages
        for ctx_msg in context[-5:]:  # Last 5 messages for context
            messages.append({
                "role": ctx_msg.get("role", "user"),
                "content": ctx_msg.get("content", "")
            })
        
        # Add the current message
        messages.append({"role": "user", "content": message})
        
        # Call AI with resilience
        response = await ai_resilience_manager.chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )
        
        return response.get("content", "I'd be happy to help you with that!")
        
    except Exception as e:
        logger.error(f"AI chat handler error: {e}")
        return (
            "I'm having a temporary issue connecting to my AI capabilities. "
            "Please try again in a moment! 🔄"
        )


async def _course_generation_handler(topic: str, preferences: Dict) -> Dict:
    """Course generation handler using multi-agent system"""
    try:
        from lyo_app.chat.agents import agent_registry
        from lyo_app.chat.models import ChatMode
        
        # Use the course planner agent
        result = await agent_registry.process(
            mode=ChatMode.COURSE_PLANNER,
            message=f"Create a course on: {topic}",
            context=preferences
        )
        
        return {
            "success": True,
            "course_data": result
        }
        
    except Exception as e:
        logger.error(f"Course generation error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def get_conversation_manager() -> ConversationManager:
    """Get or create the conversation manager singleton with handlers registered"""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
        
        # Register handlers
        import asyncio
        _conversation_manager.register_handlers(
            chat_handler=_ai_chat_handler,
            course_handler=_course_generation_handler
        )
        logger.info("ConversationManager created with AI handlers registered")
        
    return _conversation_manager
