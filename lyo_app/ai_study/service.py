"""
AI Study Mode Service Layer
Core business logic for intelligent study sessions and quiz generation
"""

import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func, desc
from sqlalchemy.orm import selectinload

from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.core.database import get_db
from .models import (
    StudySession, StudyMessage, GeneratedQuiz, QuizAttempt, 
    StudySessionStatus, MessageRole, QuizType
)
from .schemas import (
    StudySessionRequest, StudyConversationRequest, StudyConversationResponse,
    QuizGenerationRequest, QuizGenerationResponse, QuizAttemptRequest, QuizAttemptResponse,
    ConversationMessage, QuizQuestion, QuizResultDetail
)

logger = logging.getLogger(__name__)


class StudyModeService:
    """Service for managing AI-powered study sessions"""
    
    def __init__(self):
        self.ai_manager = ai_resilience_manager
        self.system_prompts = {
            "socratic": self._get_socratic_prompt,
            "encouraging": self._get_encouraging_prompt,
            "challenging": self._get_challenging_prompt,
            "patient": self._get_patient_prompt,
            "direct": self._get_direct_prompt
        }
    
    async def create_study_session(
        self, 
        user_id: int, 
        request: StudySessionRequest,
        db: AsyncSession
    ) -> StudySession:
        """Create a new AI study session"""
        
        session = StudySession(
            user_id=user_id,
            resource_id=request.resource_id,
            resource_title=request.resource_title,
            resource_type=request.resource_type,
            tutor_personality=request.tutor_personality,
            difficulty_level=request.difficulty_level,
            learning_objectives=request.learning_objectives
        )
        
        db.add(session)
        await db.commit()
        await db.refresh(session)
        
        logger.info(f"Created study session {session.id} for user {user_id} on resource {request.resource_id}")
        return session
    
    async def process_conversation(
        self,
        user_id: int,
        request: StudyConversationRequest,
        db: AsyncSession
    ) -> StudyConversationResponse:
        """Process a conversation turn in the study session"""
        
        start_time = time.time()
        
        # Get or create session
        session = await self._get_or_create_session(
            user_id, request.resource_id, request.session_id, db
        )
        
        # Save user message
        user_message = StudyMessage(
            session_id=session.id,
            role=MessageRole.USER,
            content=request.user_input,
            user_typing_time_ms=request.user_typing_time_ms
        )
        db.add(user_message)
        
        # Build conversation history
        conversation_history = await self._build_conversation_history(
            session, request.conversation_history, db
        )
        
        # Generate system prompt
        system_prompt = await self._generate_system_prompt(session, db)
        
        # Prepare messages for AI
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend([
            {"role": msg.role.value, "content": msg.content} 
            for msg in conversation_history
        ])
        messages.append({"role": "user", "content": request.user_input})
        
        # Get AI response
        try:
            ai_response = await self.ai_manager.chat_completion(
                message=json.dumps(messages),
                model_preference="openai-gpt4",
                use_cache=True
            )
            
            response_text = ai_response["response"]
            ai_model = ai_response["model"]
            token_count = ai_response.get("tokens_used", 0)
            
        except Exception as e:
            logger.error(f"AI response failed for session {session.id}: {e}")
            response_text = self._get_fallback_response(request.user_input)
            ai_model = "fallback"
            token_count = 0
        
        # Save AI message
        response_time_ms = int((time.time() - start_time) * 1000)
        ai_message = StudyMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=response_text,
            ai_model=ai_model,
            token_count=token_count,
            response_time_ms=response_time_ms
        )
        db.add(ai_message)
        
        # Update session metrics
        await self._update_session_metrics(session, response_time_ms, db)
        
        await db.commit()
        
        # Build updated conversation history
        updated_history = conversation_history + [
            ConversationMessage(role=MessageRole.USER, content=request.user_input),
            ConversationMessage(role=MessageRole.ASSISTANT, content=response_text)
        ]
        
        # Calculate engagement score
        engagement_score = await self._calculate_engagement_score(session, request.user_input)
        
        # Generate suggested actions
        suggested_actions = await self._generate_suggested_actions(session, response_text)
        
        return StudyConversationResponse(
            session_id=session.id,
            response=response_text,
            updated_conversation_history=updated_history,
            ai_model_used=ai_model,
            response_time_ms=response_time_ms,
            token_count=token_count,
            engagement_score=engagement_score,
            suggested_actions=suggested_actions,
            confidence_score=0.8  # TODO: Implement confidence calculation
        )
    
    async def generate_quiz(
        self,
        user_id: int,
        request: QuizGenerationRequest,
        db: AsyncSession
    ) -> QuizGenerationResponse:
        """Generate a quiz using AI"""
        
        start_time = time.time()
        
        # Get resource information (you would implement this based on your resource system)
        resource_info = await self._get_resource_info(request.resource_id, db)
        
        # Build generation prompt
        generation_prompt = await self._build_quiz_generation_prompt(
            resource_info, request
        )
        
        # Generate quiz with AI
        try:
            ai_response = await self.ai_manager.chat_completion(
                message=generation_prompt,
                model_preference="openai-gpt4",
                use_cache=False  # Don't cache quiz generation
            )
            
            # Parse AI response into quiz questions
            questions_data = await self._parse_quiz_response(ai_response["response"])
            ai_model = ai_response["model"]
            token_count = ai_response.get("tokens_used", 0)
            
        except Exception as e:
            logger.error(f"Quiz generation failed for resource {request.resource_id}: {e}")
            # Generate fallback quiz
            questions_data = await self._generate_fallback_quiz(request)
            ai_model = "fallback"
            token_count = 0
        
        # Create quiz questions
        questions = []
        for i, q_data in enumerate(questions_data):
            question = QuizQuestion(
                id=str(uuid.uuid4()),
                question=q_data.get("question", ""),
                question_type=request.quiz_type.value,
                options=q_data.get("options", []),
                correct_answer=q_data.get("correct_answer", ""),
                explanation=q_data.get("explanation", ""),
                difficulty=request.difficulty_level,
                topic=q_data.get("topic", ""),
                points=q_data.get("points", 1)
            )
            questions.append(question)
        
        # Save quiz to database
        generation_time_ms = int((time.time() - start_time) * 1000)
        quiz = GeneratedQuiz(
            user_id=user_id,
            resource_id=request.resource_id,
            session_id=request.session_id,
            quiz_type=request.quiz_type,
            title=f"Quiz: {resource_info.get('title', 'Study Material')}",
            description=f"AI-generated {request.quiz_type.value} quiz with {request.question_count} questions",
            difficulty_level=request.difficulty_level,
            estimated_duration_minutes=request.question_count * 2,  # 2 minutes per question
            questions=[q.dict() for q in questions],
            question_count=len(questions),
            ai_model_used=ai_model,
            generation_prompt=generation_prompt,
            generation_time_ms=generation_time_ms,
            generation_token_count=token_count
        )
        
        db.add(quiz)
        await db.commit()
        await db.refresh(quiz)
        
        logger.info(f"Generated quiz {quiz.id} with {len(questions)} questions for resource {request.resource_id}")
        
        return QuizGenerationResponse(
            quiz_id=quiz.id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            question_count=quiz.question_count,
            estimated_duration_minutes=quiz.estimated_duration_minutes,
            difficulty_level=quiz.difficulty_level,
            questions=questions,
            generation_metadata={
                "ai_model_used": ai_model,
                "generation_time_ms": generation_time_ms,
                "token_count": token_count,
                "resource_id": request.resource_id
            }
        )
    
    async def submit_quiz_attempt(
        self,
        user_id: int,
        request: QuizAttemptRequest,
        db: AsyncSession
    ) -> QuizAttemptResponse:
        """Process a quiz attempt submission"""
        
        # Get the quiz
        quiz_result = await db.execute(
            select(GeneratedQuiz).where(GeneratedQuiz.id == request.quiz_id)
        )
        quiz = quiz_result.scalar_one_or_none()
        
        if not quiz:
            raise ValueError(f"Quiz {request.quiz_id} not found")
        
        # Grade the quiz
        results = await self._grade_quiz(quiz, request.answers)
        
        # Calculate overall score
        total_points = sum(r["points_available"] for r in results)
        earned_points = sum(r["points_earned"] for r in results)
        score = (earned_points / total_points * 100) if total_points > 0 else 0
        correct_count = sum(1 for r in results if r["is_correct"])
        
        # Save attempt
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            user_id=user_id,
            completed_at=datetime.utcnow(),
            duration_minutes=request.total_time_minutes,
            user_answers=[a.dict() for a in request.answers],
            score=score,
            correct_answers=correct_count,
            total_questions=len(results),
            difficulty_rating=request.difficulty_rating,
            enjoyment_rating=request.enjoyment_rating,
            feedback_text=request.feedback
        )
        
        db.add(attempt)
        
        # Update quiz statistics
        quiz.times_taken += 1
        if quiz.average_score is None:
            quiz.average_score = score
        else:
            quiz.average_score = (quiz.average_score + score) / 2
        
        await db.commit()
        
        # Build detailed results
        detailed_results = []
        for i, result in enumerate(results):
            question_data = quiz.questions[i]
            detailed_results.append(QuizResultDetail(
                question_id=result["question_id"],
                question=question_data["question"],
                user_answer=result["user_answer"],
                correct_answer=result["correct_answer"],
                is_correct=result["is_correct"],
                points_earned=result["points_earned"],
                explanation=question_data.get("explanation", ""),
                time_taken_seconds=result.get("time_taken_seconds")
            ))
        
        # Generate performance insights
        performance_insights = await self._generate_performance_insights(
            score, results, quiz, attempt
        )
        
        # Generate recommendations
        recommendations = await self._generate_quiz_recommendations(
            score, quiz, user_id, db
        )
        
        return QuizAttemptResponse(
            attempt_id=attempt.id,
            quiz_id=quiz.id,
            score=score,
            correct_answers=correct_count,
            total_questions=len(results),
            percentage=score,
            grade=self._calculate_grade(score),
            time_taken_minutes=request.total_time_minutes or 0,
            detailed_results=detailed_results,
            performance_insights=performance_insights,
            recommended_actions=recommendations
        )
    
    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================
    
    async def _get_or_create_session(
        self,
        user_id: int,
        resource_id: str,
        session_id: Optional[str],
        db: AsyncSession
    ) -> StudySession:
        """Get existing session or create new one"""
        
        if session_id:
            result = await db.execute(
                select(StudySession).where(
                    and_(
                        StudySession.id == session_id,
                        StudySession.user_id == user_id
                    )
                )
            )
            session = result.scalar_one_or_none()
            if session:
                # Update last activity
                session.last_activity_at = datetime.utcnow()
                return session
        
        # Create new session
        session = StudySession(
            user_id=user_id,
            resource_id=resource_id,
            tutor_personality="socratic"
        )
        db.add(session)
        await db.flush()
        return session
    
    async def _build_conversation_history(
        self,
        session: StudySession,
        provided_history: List[ConversationMessage],
        db: AsyncSession
    ) -> List[ConversationMessage]:
        """Build conversation history from database and provided history"""
        
        # Get recent messages from database
        result = await db.execute(
            select(StudyMessage)
            .where(StudyMessage.session_id == session.id)
            .order_by(StudyMessage.created_at)
            .limit(50)  # Limit to recent messages
        )
        db_messages = result.scalars().all()
        
        # Convert to ConversationMessage objects
        history = []
        for msg in db_messages:
            history.append(ConversationMessage(
                role=msg.role,
                content=msg.content,
                timestamp=msg.created_at,
                token_count=msg.token_count
            ))
        
        # If provided history is longer, use it instead
        if len(provided_history) > len(history):
            return provided_history
        
        return history
    
    async def _generate_system_prompt(
        self, 
        session: StudySession, 
        db: AsyncSession
    ) -> str:
        """Generate system prompt based on session configuration"""
        
        # Get resource information
        resource_info = await self._get_resource_info(session.resource_id, db)
        
        # Get appropriate prompt generator
        prompt_generator = self.system_prompts.get(
            session.tutor_personality, 
            self._get_socratic_prompt
        )
        
        return prompt_generator(session, resource_info)
    
    def _get_socratic_prompt(self, session: StudySession, resource_info: Dict) -> str:
        """Generate Socratic method tutor prompt"""
        return f"""You are an AI tutor using the Socratic method for LyoApp. 

RESOURCE CONTEXT:
- Title: {resource_info.get('title', 'Unknown')}
- Type: {resource_info.get('type', 'Unknown')}
- Difficulty: {session.difficulty_level or 'Unknown'}

TUTORING APPROACH:
- Guide the student through questions rather than giving direct answers
- Help them discover concepts through guided inquiry
- Encourage critical thinking and self-reflection
- Ask follow-up questions to deepen understanding
- Acknowledge when they demonstrate good reasoning
- If they're struggling, break down concepts into smaller parts

LEARNING OBJECTIVES:
{', '.join(session.learning_objectives or ['General understanding'])}

Remember: Your goal is to help them learn by thinking, not by memorizing answers you provide. Always respond as a helpful, patient tutor who believes in the student's ability to understand the material through guided discovery."""
    
    def _get_encouraging_prompt(self, session: StudySession, resource_info: Dict) -> str:
        """Generate encouraging tutor prompt"""
        return f"""You are a supportive and encouraging AI tutor for LyoApp.

RESOURCE CONTEXT:
- Title: {resource_info.get('title', 'Unknown')}
- Type: {resource_info.get('type', 'Unknown')}
- Difficulty: {session.difficulty_level or 'Unknown'}

TUTORING STYLE:
- Be warm, positive, and supportive
- Celebrate small wins and progress
- Use encouraging language and positive reinforcement
- Help build confidence while maintaining academic rigor
- Provide helpful hints when students are stuck
- Frame mistakes as learning opportunities

LEARNING OBJECTIVES:
{', '.join(session.learning_objectives or ['General understanding'])}

Your mission is to create a positive learning environment where the student feels confident to explore, make mistakes, and grow. Always be their biggest supporter while helping them master the material."""
    
    def _get_challenging_prompt(self, session: StudySession, resource_info: Dict) -> str:
        """Generate challenging tutor prompt"""
        return f"""You are an intellectually rigorous AI tutor for LyoApp.

RESOURCE CONTEXT:
- Title: {resource_info.get('title', 'Unknown')}
- Type: {resource_info.get('type', 'Unknown')}
- Difficulty: {session.difficulty_level or 'Unknown'}

TUTORING APPROACH:
- Push students to think deeply and critically
- Ask probing questions that challenge assumptions
- Encourage students to defend their reasoning
- Introduce related concepts and applications
- Set high standards while remaining supportive
- Help students see connections between ideas

LEARNING OBJECTIVES:
{', '.join(session.learning_objectives or ['General understanding'])}

Your goal is to challenge students intellectually while helping them develop rigorous thinking skills. Push them to go beyond surface-level understanding to truly master the concepts."""
    
    def _get_patient_prompt(self, session: StudySession, resource_info: Dict) -> str:
        """Generate patient tutor prompt"""
        return f"""You are a patient and understanding AI tutor for LyoApp.

RESOURCE CONTEXT:
- Title: {resource_info.get('title', 'Unknown')}
- Type: {resource_info.get('type', 'Unknown')}
- Difficulty: {session.difficulty_level or 'Unknown'}

TUTORING STYLE:
- Take time to explain concepts thoroughly
- Break down complex ideas into manageable steps
- Repeat explanations in different ways if needed
- Allow students to work at their own pace
- Never make students feel rushed or pressured
- Use analogies and examples to clarify difficult concepts

LEARNING OBJECTIVES:
{', '.join(session.learning_objectives or ['General understanding'])}

Remember: Every student learns differently and at their own pace. Your patience and understanding will help them build a solid foundation for lasting learning."""
    
    def _get_direct_prompt(self, session: StudySession, resource_info: Dict) -> str:
        """Generate direct tutor prompt"""
        return f"""You are a direct and efficient AI tutor for LyoApp.

RESOURCE CONTEXT:
- Title: {resource_info.get('title', 'Unknown')}
- Type: {resource_info.get('type', 'Unknown')}
- Difficulty: {session.difficulty_level or 'Unknown'}

TUTORING STYLE:
- Provide clear, concise explanations
- Get straight to the point
- Focus on essential information
- Use structured, logical presentation
- Minimize unnecessary elaboration
- Be helpful but efficient

LEARNING OBJECTIVES:
{', '.join(session.learning_objectives or ['General understanding'])}

Your goal is to help students learn efficiently by providing clear, focused instruction that gets them to understanding quickly and effectively."""
    
    async def _get_resource_info(self, resource_id: str, db: AsyncSession) -> Dict[str, Any]:
        """Get information about a learning resource"""
        # TODO: Implement based on your resource system
        # This is a placeholder that would integrate with your existing resource models
        return {
            "title": f"Resource {resource_id}",
            "type": "general",
            "description": "Learning material",
            "difficulty": "intermediate"
        }
    
    def _get_fallback_response(self, user_input: str) -> str:
        """Generate fallback response when AI is unavailable"""
        return "I'm having trouble connecting to my AI systems right now. Could you please rephrase your question or try again in a moment? In the meantime, try breaking down the problem into smaller parts or reviewing the key concepts."
    
    async def _update_session_metrics(
        self, 
        session: StudySession, 
        response_time_ms: int, 
        db: AsyncSession
    ):
        """Update session performance metrics"""
        session.message_count += 1
        session.ai_response_count += 1
        session.last_activity_at = datetime.utcnow()
        
        # Update average response time
        if session.average_response_time == 0:
            session.average_response_time = response_time_ms
        else:
            total_time = session.average_response_time * (session.ai_response_count - 1)
            session.average_response_time = (total_time + response_time_ms) / session.ai_response_count
    
    async def _calculate_engagement_score(
        self, 
        session: StudySession, 
        user_input: str
    ) -> float:
        """Calculate user engagement score based on various factors"""
        # Simple engagement calculation based on message length and frequency
        # TODO: Implement more sophisticated engagement analysis
        
        base_score = 0.5
        
        # Message length factor
        if len(user_input) > 50:
            base_score += 0.2
        elif len(user_input) > 20:
            base_score += 0.1
        
        # Session activity factor
        if session.message_count > 5:
            base_score += 0.1
        
        # Time-based factor (active session)
        if session.last_activity_at:
            time_since_last = datetime.utcnow() - session.last_activity_at
            if time_since_last.total_seconds() < 300:  # 5 minutes
                base_score += 0.2
        
        return min(1.0, base_score)
    
    async def _generate_suggested_actions(
        self, 
        session: StudySession, 
        ai_response: str
    ) -> List[str]:
        """Generate suggested next actions for the user"""
        actions = []
        
        # Based on response content (simple keyword analysis)
        if "quiz" in ai_response.lower():
            actions.append("Take a practice quiz")
        
        if "example" in ai_response.lower():
            actions.append("Ask for more examples")
        
        if "concept" in ai_response.lower():
            actions.append("Explore related concepts")
        
        # Based on session state
        if session.message_count > 10:
            actions.append("Review what you've learned")
            actions.append("Take a break")
        
        if not actions:
            actions = [
                "Ask a follow-up question",
                "Request clarification",
                "Apply the concept to a new example"
            ]
        
        return actions[:3]  # Limit to 3 suggestions
    
    async def _build_quiz_generation_prompt(
        self,
        resource_info: Dict[str, Any],
        request: QuizGenerationRequest
    ) -> str:
        """Build prompt for quiz generation"""
        
        quiz_type_instructions = {
            QuizType.MULTIPLE_CHOICE: "Create multiple-choice questions with 4 options each.",
            QuizType.OPEN_ENDED: "Create open-ended questions that require thoughtful responses.",
            QuizType.TRUE_FALSE: "Create true/false questions with explanations.",
            QuizType.FILL_IN_BLANK: "Create fill-in-the-blank questions with clear context."
        }
        
        focus_topics_text = ""
        if request.focus_topics:
            focus_topics_text = f"Focus specifically on these topics: {', '.join(request.focus_topics)}"
        
        exclude_topics_text = ""
        if request.exclude_topics:
            exclude_topics_text = f"Avoid these topics: {', '.join(request.exclude_topics)}"
        
        prompt = f"""Generate a {request.quiz_type.value} quiz based on the following learning material:

RESOURCE DETAILS:
- Title: {resource_info.get('title', 'Unknown')}
- Type: {resource_info.get('type', 'Unknown')}
- Description: {resource_info.get('description', 'No description available')}

QUIZ REQUIREMENTS:
- Number of questions: {request.question_count}
- Difficulty level: {request.difficulty_level or 'intermediate'}
- Quiz type: {quiz_type_instructions[request.quiz_type]}

{focus_topics_text}
{exclude_topics_text}

OUTPUT FORMAT:
Return a JSON array where each question is an object with these fields:
- "question": The question text
- "options": Array of answer choices (for multiple choice) or null for other types
- "correct_answer": The correct answer
- "explanation": Brief explanation of why this is correct
- "topic": The specific topic this question covers
- "points": Points awarded for correct answer (default 1)

Ensure questions are:
- Clear and unambiguous
- Appropriate for the specified difficulty level
- Educationally valuable
- Well-distributed across the topic areas

Generate exactly {request.question_count} questions in valid JSON format."""
        
        return prompt
    
    async def _parse_quiz_response(self, ai_response: str) -> List[Dict[str, Any]]:
        """Parse AI response into quiz questions"""
        try:
            # Try to extract JSON from the response
            start_idx = ai_response.find('[')
            end_idx = ai_response.rfind(']') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_str = ai_response[start_idx:end_idx]
                questions = json.loads(json_str)
                return questions
            else:
                # If no JSON found, try to parse the entire response
                questions = json.loads(ai_response)
                return questions
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse quiz JSON: {e}")
            logger.error(f"AI response was: {ai_response}")
            # Return fallback questions
            return []
    
    async def _generate_fallback_quiz(self, request: QuizGenerationRequest) -> List[Dict[str, Any]]:
        """Generate fallback quiz when AI fails"""
        questions = []
        
        for i in range(min(request.question_count, 3)):  # Maximum 3 fallback questions
            if request.quiz_type == QuizType.MULTIPLE_CHOICE:
                question = {
                    "question": f"Question {i+1}: What is an important concept related to this topic?",
                    "options": ["Option A", "Option B", "Option C", "Option D"],
                    "correct_answer": "Option A",
                    "explanation": "This is a fallback question generated when AI services are unavailable.",
                    "topic": "General",
                    "points": 1
                }
            else:
                question = {
                    "question": f"Question {i+1}: Describe an important aspect of this topic.",
                    "options": None,
                    "correct_answer": "Any thoughtful response addressing the topic",
                    "explanation": "This is a fallback question generated when AI services are unavailable.",
                    "topic": "General",
                    "points": 1
                }
            
            questions.append(question)
        
        return questions
    
    async def _grade_quiz(
        self, 
        quiz: GeneratedQuiz, 
        user_answers: List
    ) -> List[Dict[str, Any]]:
        """Grade a quiz attempt"""
        results = []
        
        for i, user_answer in enumerate(user_answers):
            if i < len(quiz.questions):
                question = quiz.questions[i]
                correct_answer = question["correct_answer"]
                user_response = user_answer.user_answer
                
                # Simple grading logic (can be enhanced)
                is_correct = False
                if isinstance(correct_answer, str) and isinstance(user_response, str):
                    is_correct = correct_answer.lower().strip() == user_response.lower().strip()
                elif isinstance(correct_answer, (int, float)) and isinstance(user_response, (int, float)):
                    is_correct = correct_answer == user_response
                elif isinstance(correct_answer, list) and isinstance(user_response, list):
                    is_correct = set(correct_answer) == set(user_response)
                
                points_available = question.get("points", 1)
                points_earned = points_available if is_correct else 0
                
                results.append({
                    "question_id": user_answer.question_id,
                    "user_answer": user_response,
                    "correct_answer": correct_answer,
                    "is_correct": is_correct,
                    "points_available": points_available,
                    "points_earned": points_earned,
                    "time_taken_seconds": user_answer.time_taken_seconds
                })
        
        return results
    
    async def _generate_performance_insights(
        self,
        score: float,
        results: List[Dict[str, Any]],
        quiz: GeneratedQuiz,
        attempt: QuizAttempt
    ) -> Dict[str, Any]:
        """Generate performance insights and analysis"""
        
        insights = {
            "overall_performance": "excellent" if score >= 90 else "good" if score >= 70 else "needs_improvement",
            "strengths": [],
            "areas_for_improvement": [],
            "time_analysis": {},
            "difficulty_analysis": {}
        }
        
        # Analyze correct/incorrect patterns
        correct_topics = []
        incorrect_topics = []
        
        for result in results:
            topic = quiz.questions[results.index(result)].get("topic", "Unknown")
            if result["is_correct"]:
                correct_topics.append(topic)
            else:
                incorrect_topics.append(topic)
        
        # Identify strengths
        topic_counts = {}
        for topic in correct_topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        if topic_counts:
            best_topic = max(topic_counts, key=topic_counts.get)
            insights["strengths"].append(f"Strong understanding of {best_topic}")
        
        # Identify areas for improvement
        if incorrect_topics:
            most_difficult = max(set(incorrect_topics), key=incorrect_topics.count)
            insights["areas_for_improvement"].append(f"Review concepts related to {most_difficult}")
        
        # Time analysis
        if attempt.duration_minutes:
            avg_time_per_question = attempt.duration_minutes / len(results)
            insights["time_analysis"] = {
                "total_time_minutes": attempt.duration_minutes,
                "average_time_per_question": avg_time_per_question,
                "pace": "fast" if avg_time_per_question < 1 else "moderate" if avg_time_per_question < 2 else "slow"
            }
        
        return insights
    
    async def _generate_quiz_recommendations(
        self,
        score: float,
        quiz: GeneratedQuiz,
        user_id: int,
        db: AsyncSession
    ) -> List[str]:
        """Generate personalized recommendations based on quiz performance"""
        
        recommendations = []
        
        if score >= 90:
            recommendations.extend([
                "Excellent work! Try a more challenging quiz on this topic",
                "Explore advanced concepts related to this material",
                "Help other students by joining a study group"
            ])
        elif score >= 70:
            recommendations.extend([
                "Good job! Review the questions you missed",
                "Practice similar problems to reinforce learning",
                "Try explaining the concepts to someone else"
            ])
        else:
            recommendations.extend([
                "Review the core concepts before trying again",
                "Start with easier material on this topic",
                "Consider asking for help in a study session",
                "Break down complex topics into smaller parts"
            ])
        
        # Add general recommendations
        recommendations.extend([
            "Schedule regular review sessions",
            "Create flashcards for key concepts",
            "Join a study group for collaborative learning"
        ])
        
        return recommendations[:4]  # Limit to 4 recommendations
    
    def _calculate_grade(self, score: float) -> str:
        """Convert numeric score to letter grade"""
        if score >= 97:
            return "A+"
        elif score >= 93:
            return "A"
        elif score >= 90:
            return "A-"
        elif score >= 87:
            return "B+"
        elif score >= 83:
            return "B"
        elif score >= 80:
            return "B-"
        elif score >= 77:
            return "C+"
        elif score >= 73:
            return "C"
        elif score >= 70:
            return "C-"
        elif score >= 67:
            return "D+"
        elif score >= 60:
            return "D"
        else:
            return "F"


# Global service instance
study_mode_service = StudyModeService()
