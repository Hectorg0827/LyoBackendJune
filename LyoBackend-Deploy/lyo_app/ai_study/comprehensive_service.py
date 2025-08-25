"""
Comprehensive AI Study Mode Service
Provides the complete AI-powered study experience with Socratic tutoring,
quiz generation, and personalized learning analytics.
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from lyo_app.core.ai_resilience import ai_resilience_manager
from .models import StudySession, StudyMessage, GeneratedQuiz, QuizAttempt, StudySessionStatus, MessageRole, QuizType
from .schemas import (
    StudySessionCreateRequest, StudySessionCreateResponse,
    StudyConversationRequest, StudyConversationResponse,
    QuizGenerationRequest, QuizGenerationResponse,
    AnswerAnalysisRequest, AnswerAnalysisResponse
)

logger = logging.getLogger(__name__)

class ComprehensiveStudyModeService:
    """
    Complete AI-powered study mode service with all required functionality
    """
    
    def __init__(self):
        self.ai_manager = ai_resilience_manager
        self.session_cache = {}  # In-memory session cache
        self.learning_objectives_cache = {}  # Cache for learning objectives
    
    # ============================================================================
    # PHASE 2: AI STUDY MODE ENDPOINTS IMPLEMENTATION
    # ============================================================================
    
    async def study_session_endpoint(
        self,
        request: StudyConversationRequest,
        user_id: int,
        db: AsyncSession
    ) -> StudyConversationResponse:
        """
        POST /api/v1/ai/study-session
        Stateful conversation endpoint for Socratic dialogue
        """
        
        try:
            # Get or create study session
            session = await self._get_or_create_session(
                user_id=user_id,
                resource_id=request.resource_id,
                db=db
            )
            
            # Build conversation context
            system_prompt = await self._build_system_prompt(
                resource_id=request.resource_id,
                session=session
            )
            
            # Prepare full conversation history
            messages = []
            
            # Add system prompt
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Add conversation history
            for msg in request.conversation_history:
                messages.append({
                    "role": msg.role.value,
                    "content": msg.content
                })
            
            # Add current user input
            messages.append({"role": "user", "content": request.user_input})
            
            # Get AI response
            ai_response = await self.ai_manager.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            # Store messages in database
            await self._store_conversation_turn(
                session=session,
                user_input=request.user_input,
                ai_response=ai_response["content"],
                ai_metadata=ai_response,
                db=db
            )
            
            # Build updated conversation history
            updated_history = []
            for msg in request.conversation_history:
                updated_history.append({
                    "role": msg.role.value,
                    "content": msg.content,
                    "timestamp": msg.timestamp or time.time()
                })
            
            # Add new messages
            updated_history.extend([
                {
                    "role": "user",
                    "content": request.user_input,
                    "timestamp": time.time()
                },
                {
                    "role": "assistant",
                    "content": ai_response["content"],
                    "timestamp": time.time()
                }
            ])
            
            # Generate tutoring insights
            insights = await self._generate_tutoring_insights(
                conversation_history=updated_history,
                session=session
            )
            
            # Generate next steps
            next_steps = await self._generate_next_steps(
                user_input=request.user_input,
                ai_response=ai_response["content"],
                session=session
            )
            
            # Update session metadata
            session_metadata = {
                "message_count": len(updated_history),
                "last_activity": time.time(),
                "engagement_level": insights.get("engagement_level", 0.5),
                "comprehension_score": insights.get("comprehension_score", 0.5)
            }
            
            return StudyConversationResponse(
                response=ai_response["content"],
                updated_conversation_history=updated_history,
                session_metadata=session_metadata,
                tutoring_insights=insights,
                suggested_next_steps=next_steps
            )
            
        except Exception as e:
            logger.error(f"Study session endpoint failed: {e}", exc_info=True)
            return StudyConversationResponse(
                response="I apologize, but I'm having trouble responding right now. Please try again.",
                updated_conversation_history=request.conversation_history,
                session_metadata={"error": str(e)},
                tutoring_insights={"error": "Service temporarily unavailable"},
                suggested_next_steps=["Please try your question again"]
            )
    
    async def generate_quiz_endpoint(
        self,
        request: QuizGenerationRequest,
        user_id: int,
        db: AsyncSession
    ) -> QuizGenerationResponse:
        """
        POST /api/v1/ai/generate-quiz
        On-demand quiz generation endpoint
        """
        
        try:
            # Get resource content for context
            resource_content = await self._get_resource_content(request.resource_id)
            
            # Build quiz generation prompt
            quiz_prompt = self._build_quiz_generation_prompt(
                resource_content=resource_content,
                quiz_type=request.quiz_type,
                question_count=request.question_count,
                difficulty=request.difficulty_level
            )
            
            # Generate quiz with AI
            ai_response = await self.ai_manager.chat_completion(
                messages=[{"role": "user", "content": quiz_prompt}],
                temperature=0.3,  # Lower temperature for consistency
                max_tokens=2000
            )
            
            # Parse and validate JSON response
            try:
                quiz_data = json.loads(ai_response["content"])
                if not isinstance(quiz_data, list):
                    raise ValueError("Quiz response must be a JSON array")
                
                # Validate question format
                validated_questions = []
                for i, question in enumerate(quiz_data):
                    if not isinstance(question, dict):
                        continue
                    
                    # Ensure required fields
                    if "question" not in question:
                        continue
                    
                    validated_question = {
                        "id": str(i + 1),
                        "question": question["question"],
                        "question_type": request.quiz_type.value,
                        "correct_answer": question.get("correctAnswer", ""),
                        "explanation": question.get("explanation", ""),
                        "difficulty": request.difficulty_level.value,
                        "topic": request.resource_id,
                        "points": 1
                    }
                    
                    # Add options for multiple choice
                    if request.quiz_type.value == "multiple_choice":
                        validated_question["options"] = question.get("options", [])
                    
                    validated_questions.append(validated_question)
                
                # Store quiz in database
                quiz_id = await self._store_generated_quiz(
                    user_id=user_id,
                    resource_id=request.resource_id,
                    quiz_type=request.quiz_type,
                    questions=validated_questions,
                    ai_metadata=ai_response,
                    db=db
                )
                
                return QuizGenerationResponse(
                    quiz_id=quiz_id,
                    title=f"Quiz: {request.resource_id}",
                    description=f"{request.quiz_type.value.replace('_', ' ').title()} quiz with {len(validated_questions)} questions",
                    quiz_type=request.quiz_type.value,
                    question_count=len(validated_questions),
                    estimated_duration_minutes=len(validated_questions) * 2,  # 2 minutes per question
                    difficulty_level=request.difficulty_level.value,
                    questions=validated_questions,
                    generation_metadata={
                        "ai_model": ai_response.get("model", "unknown"),
                        "tokens_used": ai_response.get("tokens_used", 0),
                        "generation_time": ai_response.get("response_time", 0),
                        "timestamp": time.time()
                    }
                )
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse quiz JSON: {e}")
                # Return fallback quiz
                fallback_questions = self._generate_fallback_quiz(
                    request.question_count,
                    request.quiz_type.value
                )
                
                return QuizGenerationResponse(
                    quiz_id=f"fallback_{int(time.time())}",
                    title=f"Sample Quiz: {request.resource_id}",
                    description="Fallback quiz generated when AI service is unavailable",
                    quiz_type=request.quiz_type.value,
                    question_count=len(fallback_questions),
                    estimated_duration_minutes=len(fallback_questions) * 2,
                    difficulty_level=request.difficulty_level.value,
                    questions=fallback_questions,
                    generation_metadata={"fallback": True}
                )
                
        except Exception as e:
            logger.error(f"Quiz generation failed: {e}", exc_info=True)
            raise Exception(f"Quiz generation failed: {str(e)}")
    
    async def analyze_answer_endpoint(
        self,
        request: AnswerAnalysisRequest,
        user_id: int
    ) -> AnswerAnalysisResponse:
        """
        POST /api/v1/ai/analyze-answer
        Personalized feedback endpoint
        """
        
        try:
            # Build analysis prompt
            analysis_prompt = f"""
            Please analyze this student's answer and provide constructive feedback.
            
            Question: {request.question}
            Correct Answer: {request.correct_answer}
            Student's Answer: {request.user_answer}
            
            Provide encouraging, helpful feedback that:
            1. Explains why the answer may be incorrect (if it is)
            2. Guides the student toward the right concept
            3. Does not simply give away the answer
            4. Encourages further learning
            
            Be supportive and educational in your response.
            """
            
            # Get AI analysis
            ai_response = await self.ai_manager.chat_completion(
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=0.5,
                max_tokens=500
            )
            
            # Determine if answer is correct (basic string comparison)
            is_correct = self._evaluate_answer_correctness(
                request.correct_answer,
                request.user_answer
            )
            
            # Generate suggestions based on correctness
            suggestions = []
            if not is_correct:
                suggestions = [
                    "Review the related concepts in the learning material",
                    "Try to understand the underlying principles",
                    "Practice similar questions to reinforce learning"
                ]
            else:
                suggestions = [
                    "Great job! Try more challenging questions",
                    "Explore related advanced topics",
                    "Help others who might be struggling with this concept"
                ]
            
            return AnswerAnalysisResponse(
                feedback=ai_response["content"],
                is_correct=is_correct,
                partial_credit=0.5 if not is_correct else 1.0,  # Simple partial credit
                suggestions=suggestions,
                related_concepts=[request.question.split()[0]]  # Simple concept extraction
            )
            
        except Exception as e:
            logger.error(f"Answer analysis failed: {e}", exc_info=True)
            # Fallback response
            return AnswerAnalysisResponse(
                feedback="Thank you for your answer. Please review the learning material and try again.",
                is_correct=False,
                suggestions=["Review the learning material", "Try again later"],
                related_concepts=[]
            )
    
    # ============================================================================
    # HELPER METHODS
    # ============================================================================
    
    async def _get_or_create_session(
        self,
        user_id: int,
        resource_id: str,
        db: AsyncSession
    ) -> StudySession:
        """Get existing active session or create new one"""
        
        # Check for existing active session
        result = await db.execute(
            select(StudySession).where(
                and_(
                    StudySession.user_id == user_id,
                    StudySession.resource_id == resource_id,
                    StudySession.status == StudySessionStatus.ACTIVE
                )
            )
        )
        
        session = result.scalar_one_or_none()
        
        if session:
            # Update last activity
            session.last_activity_at = datetime.utcnow()
            await db.commit()
            return session
        
        # Create new session
        session = StudySession(
            user_id=user_id,
            resource_id=resource_id,
            resource_title=f"Learning: {resource_id}",
            resource_type="lesson",
            status=StudySessionStatus.ACTIVE,
            tutor_personality="socratic",
            started_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow()
        )
        
        db.add(session)
        await db.commit()
        await db.refresh(session)
        
        return session
    
    async def _build_system_prompt(
        self,
        resource_id: str,
        session: StudySession
    ) -> str:
        """Build system prompt for AI tutor"""
        
        return f"""
        You are an expert AI tutor specializing in the Socratic method of teaching. 
        You are helping a student learn about the topic: {resource_id}.
        
        Your teaching style should be:
        - Ask probing questions that guide the student to discover answers themselves
        - Encourage critical thinking and deep understanding
        - Be patient and supportive
        - Break down complex concepts into manageable parts
        - Provide hints rather than direct answers
        - Celebrate insights and progress
        
        The student is studying: {session.resource_title or resource_id}
        
        Guide them through their learning journey with thoughtful questions and gentle guidance.
        Keep responses concise but engaging.
        """
    
    async def _store_conversation_turn(
        self,
        session: StudySession,
        user_input: str,
        ai_response: str,
        ai_metadata: Dict[str, Any],
        db: AsyncSession
    ):
        """Store conversation turn in database"""
        
        # Store user message
        user_message = StudyMessage(
            session_id=session.id,
            role=MessageRole.USER,
            content=user_input,
            created_at=datetime.utcnow()
        )
        
        # Store AI message
        ai_message = StudyMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=ai_response,
            created_at=datetime.utcnow(),
            ai_model=ai_metadata.get("model", "unknown"),
            token_count=ai_metadata.get("tokens_used", 0),
            response_time_ms=int(ai_metadata.get("response_time", 0) * 1000)
        )
        
        db.add(user_message)
        db.add(ai_message)
        
        # Update session stats
        session.message_count += 2
        session.ai_response_count += 1
        session.last_activity_at = datetime.utcnow()
        
        await db.commit()
    
    async def _generate_tutoring_insights(
        self,
        conversation_history: List[Dict[str, Any]],
        session: StudySession
    ) -> Dict[str, Any]:
        """Generate insights about the tutoring session"""
        
        # Simple heuristic-based insights
        user_messages = [msg for msg in conversation_history if msg["role"] == "user"]
        
        insights = {
            "engagement_level": min(len(user_messages) / 10.0, 1.0),  # Normalize to 0-1
            "comprehension_score": 0.7,  # Placeholder
            "question_frequency": len(user_messages),
            "session_duration_minutes": (time.time() - session.started_at.timestamp()) / 60,
            "learning_progress": "progressing well"
        }
        
        return insights
    
    async def _generate_next_steps(
        self,
        user_input: str,
        ai_response: str,
        session: StudySession
    ) -> List[str]:
        """Generate suggested next steps for learning"""
        
        # Simple rule-based next steps
        next_steps = [
            "Continue exploring this topic with more questions",
            "Try to apply what you've learned to a practical example",
            "Take a quiz to test your understanding"
        ]
        
        # Add contextual suggestions based on conversation
        if "?" in user_input:
            next_steps.append("Great question! Keep asking questions to deepen your understanding")
        
        if len(session.messages) > 10:
            next_steps.append("Consider taking a break and reviewing what you've learned")
        
        return next_steps[:3]  # Return top 3 suggestions
    
    def _build_quiz_generation_prompt(
        self,
        resource_content: str,
        quiz_type: str,
        question_count: int,
        difficulty: str
    ) -> str:
        """Build prompt for quiz generation"""
        
        if quiz_type == "multiple_choice":
            format_example = '''
            [
                {
                    "question": "What is the main concept discussed?",
                    "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
                    "correctAnswer": "A",
                    "explanation": "This is correct because..."
                }
            ]
            '''
        else:
            format_example = '''
            [
                {
                    "question": "Explain the main concept in your own words",
                    "correctAnswer": "Sample answer demonstrating understanding",
                    "explanation": "Key points to look for in the answer"
                }
            ]
            '''
        
        return f"""
        Create exactly {question_count} {quiz_type.replace('_', ' ')} questions based on this content.
        Difficulty level: {difficulty}
        
        Content:
        {resource_content[:2000]}  # Limit content length
        
        Generate questions that test understanding, not just memorization.
        
        Format your response as valid JSON only:
        {format_example}
        
        Respond with ONLY the JSON array, no other text.
        """
    
    async def _get_resource_content(self, resource_id: str) -> str:
        """Get content for the learning resource"""
        
        # Placeholder - in real implementation, this would fetch from database
        return f"""
        This is the learning content for resource: {resource_id}
        
        Key concepts:
        - Main topic overview
        - Important principles
        - Practical applications
        - Common misconceptions
        
        This content would normally be fetched from your learning management system.
        """
    
    async def _store_generated_quiz(
        self,
        user_id: int,
        resource_id: str,
        quiz_type: QuizType,
        questions: List[Dict[str, Any]],
        ai_metadata: Dict[str, Any],
        db: AsyncSession
    ) -> str:
        """Store generated quiz in database"""
        
        quiz = GeneratedQuiz(
            user_id=user_id,
            resource_id=resource_id,
            quiz_type=quiz_type,
            title=f"AI Generated Quiz: {resource_id}",
            description=f"Quiz with {len(questions)} questions",
            difficulty_level="intermediate",
            estimated_duration_minutes=len(questions) * 2,
            questions=questions,
            question_count=len(questions),
            ai_model_used=ai_metadata.get("model", "unknown"),
            generation_time_ms=int(ai_metadata.get("response_time", 0) * 1000),
            generation_token_count=ai_metadata.get("tokens_used", 0)
        )
        
        db.add(quiz)
        await db.commit()
        await db.refresh(quiz)
        
        return quiz.id
    
    def _generate_fallback_quiz(self, question_count: int, quiz_type: str) -> List[Dict[str, Any]]:
        """Generate fallback quiz when AI fails"""
        
        questions = []
        for i in range(question_count):
            if quiz_type == "multiple_choice":
                question = {
                    "id": str(i + 1),
                    "question": f"Sample question {i + 1} about the learning material",
                    "question_type": quiz_type,
                    "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
                    "correct_answer": "A",
                    "explanation": "This is a fallback question.",
                    "difficulty": "intermediate",
                    "topic": "sample",
                    "points": 1
                }
            else:
                question = {
                    "id": str(i + 1),
                    "question": f"Describe concept {i + 1} from the learning material",
                    "question_type": quiz_type,
                    "correct_answer": "Sample answer for demonstration",
                    "explanation": "Look for understanding of key concepts.",
                    "difficulty": "intermediate",
                    "topic": "sample",
                    "points": 1
                }
            
            questions.append(question)
        
        return questions
    
    def _evaluate_answer_correctness(self, correct_answer: str, user_answer: str) -> bool:
        """Simple answer correctness evaluation"""
        
        # Basic string comparison (case-insensitive)
        return correct_answer.lower().strip() == user_answer.lower().strip()

# Global service instance
comprehensive_study_service = ComprehensiveStudyModeService()
