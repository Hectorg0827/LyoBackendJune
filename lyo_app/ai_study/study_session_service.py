"""
Intelligent Study Session Service
Manages stateful AI-powered study conversations with Socratic tutoring approach
"""

import logging
import time
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from lyo_app.core.database import get_db
from lyo_app.ai_agents.orchestrator import ai_orchestrator
from lyo_app.learning.models import Course, Lesson
from lyo_app.ai_study.models import StudySession, StudyMessage, StudySessionType
from lyo_app.core.ai_resilience import ai_resilience_manager

logger = logging.getLogger(__name__)

@dataclass
class ConversationMessage:
    """Individual message in conversation history"""
    role: str  # "system", "user", "assistant"
    content: str
    timestamp: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StudySessionContext:
    """Complete context for a study session"""
    resource_id: str
    resource_type: str  # "course", "lesson", "topic", "custom"
    resource_title: str
    difficulty_level: str
    subject_area: str
    learning_objectives: List[str]
    user_profile: Dict[str, Any]
    session_metadata: Dict[str, Any] = field(default_factory=dict)

class StudySessionService:
    """Intelligent Study Session Management Service"""
    
    def __init__(self):
        self.session_cache: Dict[str, List[ConversationMessage]] = {}
        self.context_cache: Dict[str, StudySessionContext] = {}
        self.tutoring_styles = {
            "socratic": "Guide with questions, avoid direct answers",
            "collaborative": "Work together to solve problems", 
            "explanatory": "Provide detailed explanations with examples",
            "practical": "Focus on hands-on application and practice"
        }
    
    async def create_study_session(
        self,
        user_id: int,
        resource_id: str,
        resource_type: str = "lesson",
        tutoring_style: str = "socratic",
        db: Session = None
    ) -> Dict[str, Any]:
        """Create a new intelligent study session"""
        
        try:
            # Get resource context
            context = await self._build_resource_context(resource_id, resource_type, db)
            
            # Create database session record
            study_session = StudySession(
                user_id=user_id,
                resource_id=resource_id,
                resource_type=resource_type,
                session_type=StudySessionType.SOCRATIC_TUTORING,
                metadata={
                    "tutoring_style": tutoring_style,
                    "resource_title": context.resource_title,
                    "difficulty_level": context.difficulty_level,
                    "subject_area": context.subject_area
                }
            )
            
            db.add(study_session)
            db.commit()
            db.refresh(study_session)
            
            # Generate initial system prompt
            system_prompt = await self._generate_system_prompt(context, tutoring_style)
            
            # Initialize conversation with system message
            initial_conversation = [
                ConversationMessage(
                    role="system",
                    content=system_prompt,
                    timestamp=time.time(),
                    metadata={"session_id": study_session.id}
                )
            ]
            
            # Cache the session
            session_key = f"{user_id}:{study_session.id}"
            self.session_cache[session_key] = initial_conversation
            self.context_cache[session_key] = context
            
            # Generate welcome message
            welcome_response = await self._generate_welcome_message(context, tutoring_style)
            
            # Add welcome message to conversation
            welcome_message = ConversationMessage(
                role="assistant",
                content=welcome_response,
                timestamp=time.time(),
                metadata={"message_type": "welcome"}
            )
            
            initial_conversation.append(welcome_message)
            
            # Save welcome message to database
            db_message = StudyMessage(
                session_id=study_session.id,
                role="assistant",
                content=welcome_response,
                metadata={"message_type": "welcome"}
            )
            db.add(db_message)
            db.commit()
            
            return {
                "session_id": study_session.id,
                "resource_title": context.resource_title,
                "welcome_message": welcome_response,
                "conversation_history": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp
                    }
                    for msg in initial_conversation if msg.role != "system"
                ],
                "tutoring_style": tutoring_style,
                "difficulty_level": context.difficulty_level,
                "subject_area": context.subject_area
            }
            
        except Exception as e:
            logger.error(f"Error creating study session: {e}")
            if db:
                db.rollback()
            raise e
    
    async def continue_study_session(
        self,
        user_id: int,
        session_id: int,
        user_input: str,
        conversation_history: List[Dict[str, str]] = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """Continue an existing study session with user input"""
        
        try:
            session_key = f"{user_id}:{session_id}"
            
            # Get session from database if not in cache
            if session_key not in self.session_cache:
                await self._load_session_from_db(session_id, user_id, db)
            
            # Get cached conversation and context
            cached_conversation = self.session_cache.get(session_key, [])
            context = self.context_cache.get(session_key)
            
            if not context:
                raise ValueError(f"Study session {session_id} not found")
            
            # Build current conversation history
            current_conversation = []
            
            # Add system prompt
            if cached_conversation and cached_conversation[0].role == "system":
                current_conversation.append(cached_conversation[0])
            
            # Add conversation history (if provided) or use cached
            if conversation_history:
                for msg in conversation_history:
                    current_conversation.append(
                        ConversationMessage(
                            role=msg["role"],
                            content=msg["content"],
                            timestamp=msg.get("timestamp", time.time())
                        )
                    )
            else:
                current_conversation.extend(cached_conversation[1:])  # Skip system message
            
            # Add new user message
            user_message = ConversationMessage(
                role="user",
                content=user_input,
                timestamp=time.time()
            )
            current_conversation.append(user_message)
            
            # Save user message to database
            db_user_message = StudyMessage(
                session_id=session_id,
                role="user",
                content=user_input,
                metadata={"timestamp": time.time()}
            )
            db.add(db_user_message)
            
            # Generate AI response using enhanced context
            ai_response = await self._generate_tutoring_response(
                current_conversation,
                context,
                user_input
            )
            
            # Add AI response to conversation
            ai_message = ConversationMessage(
                role="assistant",
                content=ai_response["content"],
                timestamp=time.time(),
                metadata=ai_response.get("metadata", {})
            )
            current_conversation.append(ai_message)
            
            # Save AI message to database
            db_ai_message = StudyMessage(
                session_id=session_id,
                role="assistant",
                content=ai_response["content"],
                metadata=ai_response.get("metadata", {})
            )
            db.add(db_ai_message)
            
            # Update session activity
            study_session = db.query(StudySession).filter(StudySession.id == session_id).first()
            if study_session:
                study_session.updated_at = datetime.utcnow()
                study_session.message_count = len(current_conversation) - 1  # Exclude system message
            
            db.commit()
            
            # Update cache
            self.session_cache[session_key] = current_conversation
            
            # Prepare response
            return {
                "response": ai_response["content"],
                "updated_conversation_history": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp
                    }
                    for msg in current_conversation if msg.role != "system"
                ],
                "session_metadata": {
                    "message_count": len(current_conversation) - 1,
                    "session_duration": time.time() - (current_conversation[1].timestamp if len(current_conversation) > 1 else time.time()),
                    "ai_model_used": ai_response.get("model", "unknown"),
                    "response_confidence": ai_response.get("confidence", 0.8)
                },
                "tutoring_insights": ai_response.get("tutoring_insights", {}),
                "suggested_next_steps": ai_response.get("suggested_next_steps", [])
            }
            
        except Exception as e:
            logger.error(f"Error continuing study session: {e}")
            if db:
                db.rollback()
            raise e
    
    async def get_session_history(
        self,
        user_id: int,
        session_id: int,
        db: Session = None
    ) -> Dict[str, Any]:
        """Get complete session history and analytics"""
        
        try:
            # Get session from database
            study_session = db.query(StudySession).filter(
                and_(StudySession.id == session_id, StudySession.user_id == user_id)
            ).first()
            
            if not study_session:
                raise ValueError(f"Study session {session_id} not found")
            
            # Get all messages
            messages = db.query(StudyMessage).filter(
                StudyMessage.session_id == session_id
            ).order_by(StudyMessage.created_at).all()
            
            # Calculate session analytics
            analytics = await self._calculate_session_analytics(study_session, messages)
            
            return {
                "session_id": session_id,
                "resource_id": study_session.resource_id,
                "resource_type": study_session.resource_type,
                "session_type": study_session.session_type.value,
                "created_at": study_session.created_at.isoformat(),
                "updated_at": study_session.updated_at.isoformat(),
                "message_count": len(messages),
                "conversation_history": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.created_at.timestamp(),
                        "metadata": msg.metadata
                    }
                    for msg in messages
                ],
                "session_metadata": study_session.metadata,
                "analytics": analytics
            }
            
        except Exception as e:
            logger.error(f"Error getting session history: {e}")
            raise e
    
    async def _build_resource_context(
        self,
        resource_id: str,
        resource_type: str,
        db: Session
    ) -> StudySessionContext:
        """Build comprehensive context for the resource being studied"""
        
        try:
            if resource_type == "course":
                course = db.query(Course).filter(Course.id == resource_id).first()
                if course:
                    return StudySessionContext(
                        resource_id=resource_id,
                        resource_type=resource_type,
                        resource_title=course.title,
                        difficulty_level=course.difficulty_level or "intermediate",
                        subject_area=course.category or "general",
                        learning_objectives=course.learning_objectives or []
                    )
            
            elif resource_type == "lesson":
                lesson = db.query(Lesson).filter(Lesson.id == resource_id).first()
                if lesson:
                    course = lesson.course
                    return StudySessionContext(
                        resource_id=resource_id,
                        resource_type=resource_type,
                        resource_title=lesson.title,
                        difficulty_level=course.difficulty_level if course else "intermediate",
                        subject_area=course.category if course else "general",
                        learning_objectives=lesson.learning_objectives or []
                    )
            
            # Default fallback context
            return StudySessionContext(
                resource_id=resource_id,
                resource_type=resource_type,
                resource_title=f"Study Topic {resource_id}",
                difficulty_level="intermediate",
                subject_area="general",
                learning_objectives=["Master the fundamentals", "Apply knowledge practically"]
            )
            
        except Exception as e:
            logger.error(f"Error building resource context: {e}")
            # Return minimal context
            return StudySessionContext(
                resource_id=resource_id,
                resource_type=resource_type,
                resource_title="Study Session",
                difficulty_level="intermediate",
                subject_area="general",
                learning_objectives=[]
            )
    
    async def _generate_system_prompt(
        self,
        context: StudySessionContext,
        tutoring_style: str
    ) -> str:
        """Generate intelligent system prompt for the AI tutor"""
        
        style_instructions = self.tutoring_styles.get(tutoring_style, self.tutoring_styles["socratic"])
        
        system_prompt = f"""You are an expert AI tutor for LyoApp, specializing in {context.subject_area}. 

RESOURCE CONTEXT:
- Topic: {context.resource_title}
- Difficulty: {context.difficulty_level}
- Subject Area: {context.subject_area}
- Learning Objectives: {', '.join(context.learning_objectives) if context.learning_objectives else 'General understanding'}

TUTORING APPROACH: {style_instructions}

INSTRUCTIONS:
1. Use the Socratic method - guide with questions rather than giving direct answers
2. Adapt to the student's understanding level and pace
3. Encourage critical thinking and problem-solving
4. Provide hints and scaffolding when students struggle
5. Celebrate progress and maintain positive engagement
6. Connect concepts to real-world applications
7. Check understanding frequently with targeted questions

RESPONSE STYLE:
- Keep responses concise but engaging (2-4 sentences typical)
- Use encouraging and supportive language
- Ask thought-provoking follow-up questions
- Provide specific, actionable guidance
- Reference the learning objectives when relevant

Remember: Your goal is to facilitate learning, not to lecture. Guide the student to discover answers through thoughtful questioning and gentle guidance."""

        return system_prompt
    
    async def _generate_welcome_message(
        self,
        context: StudySessionContext,
        tutoring_style: str
    ) -> str:
        """Generate personalized welcome message for the study session"""
        
        welcome_prompts = {
            "socratic": f"Welcome to your study session on '{context.resource_title}'! I'm here to guide you through this topic using questions that will help you discover the answers yourself. What would you like to explore first, or do you have a specific question to start with?",
            
            "collaborative": f"Hi! I'm excited to work with you on '{context.resource_title}'. We'll tackle this together as learning partners. What aspect of this topic interests you most, or where would you like to begin?",
            
            "explanatory": f"Welcome! I'm here to help you understand '{context.resource_title}' with clear explanations and examples. What specific concepts or questions do you have about this topic?",
            
            "practical": f"Great choice studying '{context.resource_title}'! I'll help you learn through hands-on examples and practical applications. What real-world problem or scenario would you like to explore related to this topic?"
        }
        
        return welcome_prompts.get(tutoring_style, welcome_prompts["socratic"])
    
    async def _generate_tutoring_response(
        self,
        conversation: List[ConversationMessage],
        context: StudySessionContext,
        user_input: str
    ) -> Dict[str, Any]:
        """Generate intelligent tutoring response using AI"""
        
        try:
            # Prepare conversation for AI
            ai_conversation = [
                {"role": msg.role, "content": msg.content}
                for msg in conversation
            ]
            
            # Add context-aware enhancement to user input
            enhanced_context = f"""
            
ADDITIONAL CONTEXT:
- Current topic: {context.resource_title}
- Subject area: {context.subject_area}
- Difficulty level: {context.difficulty_level}
- Learning objectives: {', '.join(context.learning_objectives) if context.learning_objectives else 'Not specified'}
            """
            
            # Use AI resilience manager for response generation
            ai_response = await ai_resilience_manager.chat_completion(
                message=user_input + enhanced_context,
                model_preference="gemini-pro",  # Use best model for tutoring
                max_retries=2,
                use_cache=True
            )
            
            # Analyze response for tutoring insights
            insights = await self._analyze_tutoring_interaction(user_input, ai_response["response"], context)
            
            return {
                "content": ai_response["response"],
                "model": ai_response.get("model", "unknown"),
                "confidence": 0.85,  # High confidence for educational responses
                "metadata": {
                    "tokens_used": ai_response.get("tokens_used", 0),
                    "response_time": ai_response.get("timestamp", time.time()),
                    "tutoring_style": "socratic"
                },
                "tutoring_insights": insights,
                "suggested_next_steps": await self._generate_next_steps(user_input, ai_response["response"], context)
            }
            
        except Exception as e:
            logger.error(f"Error generating tutoring response: {e}")
            
            # Fallback response
            return {
                "content": "I'm having trouble processing your question right now. Could you try rephrasing it, or ask about a specific aspect of the topic you'd like to explore?",
                "model": "fallback",
                "confidence": 0.5,
                "metadata": {"error": str(e)},
                "tutoring_insights": {},
                "suggested_next_steps": ["Try rephrasing your question", "Ask about a specific concept"]
            }
    
    async def _analyze_tutoring_interaction(
        self,
        user_input: str,
        ai_response: str,
        context: StudySessionContext
    ) -> Dict[str, Any]:
        """Analyze the tutoring interaction for insights"""
        
        insights = {
            "user_engagement_level": "medium",
            "question_complexity": "medium",
            "learning_progress_indicator": "on_track",
            "suggested_difficulty_adjustment": "maintain",
            "key_concepts_identified": [],
            "misconceptions_detected": []
        }
        
        # Simple heuristic analysis (can be enhanced with ML models)
        if len(user_input.split()) > 20:
            insights["user_engagement_level"] = "high"
        elif len(user_input.split()) < 5:
            insights["user_engagement_level"] = "low"
        
        # Check for question words indicating engagement
        question_words = ["why", "how", "what", "when", "where", "which"]
        if any(word in user_input.lower() for word in question_words):
            insights["question_complexity"] = "high"
        
        return insights
    
    async def _generate_next_steps(
        self,
        user_input: str,
        ai_response: str,
        context: StudySessionContext
    ) -> List[str]:
        """Generate suggested next steps for the learner"""
        
        # Generate contextual next steps
        next_steps = []
        
        # Based on context and subject area
        if context.subject_area.lower() in ["mathematics", "math"]:
            next_steps.extend([
                "Try solving a practice problem",
                "Explore a real-world application",
                "Review the fundamental concepts"
            ])
        elif context.subject_area.lower() in ["science", "physics", "chemistry", "biology"]:
            next_steps.extend([
                "Conduct a thought experiment",
                "Examine a case study",
                "Connect to everyday phenomena"
            ])
        elif context.subject_area.lower() in ["programming", "computer science", "coding"]:
            next_steps.extend([
                "Write some sample code",
                "Debug a common error",
                "Build a small project"
            ])
        else:
            next_steps.extend([
                "Explore a related concept",
                "Apply this to a practical scenario",
                "Ask a follow-up question"
            ])
        
        return next_steps[:3]  # Return top 3 suggestions
    
    async def _load_session_from_db(
        self,
        session_id: int,
        user_id: int,
        db: Session
    ):
        """Load session from database into cache"""
        
        try:
            # Get session
            study_session = db.query(StudySession).filter(
                and_(StudySession.id == session_id, StudySession.user_id == user_id)
            ).first()
            
            if not study_session:
                raise ValueError(f"Study session {session_id} not found")
            
            # Get messages
            messages = db.query(StudyMessage).filter(
                StudyMessage.session_id == session_id
            ).order_by(StudyMessage.created_at).all()
            
            # Rebuild conversation
            conversation = []
            
            # Add system prompt (regenerate if needed)
            context = await self._build_resource_context(
                study_session.resource_id,
                study_session.resource_type,
                db
            )
            
            tutoring_style = study_session.metadata.get("tutoring_style", "socratic")
            system_prompt = await self._generate_system_prompt(context, tutoring_style)
            
            conversation.append(
                ConversationMessage(
                    role="system",
                    content=system_prompt,
                    timestamp=study_session.created_at.timestamp()
                )
            )
            
            # Add all messages
            for msg in messages:
                conversation.append(
                    ConversationMessage(
                        role=msg.role,
                        content=msg.content,
                        timestamp=msg.created_at.timestamp(),
                        metadata=msg.metadata
                    )
                )
            
            # Cache the session
            session_key = f"{user_id}:{session_id}"
            self.session_cache[session_key] = conversation
            self.context_cache[session_key] = context
            
        except Exception as e:
            logger.error(f"Error loading session from database: {e}")
            raise e
    
    async def _calculate_session_analytics(
        self,
        session: StudySession,
        messages: List[StudyMessage]
    ) -> Dict[str, Any]:
        """Calculate comprehensive session analytics"""
        
        if not messages:
            return {"message_count": 0, "duration_minutes": 0}
        
        # Basic metrics
        user_messages = [msg for msg in messages if msg.role == "user"]
        ai_messages = [msg for msg in messages if msg.role == "assistant"]
        
        # Calculate duration
        start_time = messages[0].created_at
        end_time = messages[-1].created_at
        duration_minutes = (end_time - start_time).total_seconds() / 60
        
        # Calculate engagement metrics
        avg_user_message_length = sum(len(msg.content.split()) for msg in user_messages) / len(user_messages) if user_messages else 0
        
        return {
            "message_count": len(messages),
            "user_messages": len(user_messages),
            "ai_messages": len(ai_messages),
            "duration_minutes": round(duration_minutes, 2),
            "avg_user_message_length": round(avg_user_message_length, 1),
            "engagement_score": min(1.0, (len(user_messages) * avg_user_message_length) / 100),
            "session_intensity": len(messages) / max(duration_minutes, 1),  # messages per minute
            "last_activity": end_time.isoformat()
        }

# Global service instance
study_session_service = StudySessionService()
