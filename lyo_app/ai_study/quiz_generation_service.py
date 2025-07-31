"""
Intelligent Quiz Generation Service
AI-powered quiz creation with contextual questions and adaptive difficulty
"""

import logging
import json
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from sqlalchemy.orm import Session

from lyo_app.core.database import get_db
from lyo_app.ai_agents.orchestrator import orchestrator
from lyo_app.learning.models import Course, Lesson
from lyo_app.ai_study.models import QuizSession, QuizQuestion, QuizAttempt, QuestionType
from lyo_app.core.ai_resilience import ai_resilience_manager

logger = logging.getLogger(__name__)

class QuizType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    OPEN_ENDED = "open_ended"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    MATCHING = "matching"
    SHORT_ANSWER = "short_answer"

class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

@dataclass
class QuizGenerationRequest:
    """Request parameters for quiz generation"""
    resource_id: str
    resource_type: str = "lesson"  # "course", "lesson", "topic"
    quiz_type: QuizType = QuizType.MULTIPLE_CHOICE
    question_count: int = 5
    difficulty_level: DifficultyLevel = DifficultyLevel.INTERMEDIATE
    focus_areas: List[str] = field(default_factory=list)
    learning_objectives: List[str] = field(default_factory=list)
    time_limit_minutes: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class QuizQuestion:
    """Individual quiz question with all possible formats"""
    question: str
    question_type: QuizType
    options: Optional[List[str]] = None  # For multiple choice
    correct_answer: Union[str, List[str], int] = None
    explanation: Optional[str] = None
    difficulty_score: float = 0.5  # 0.0 = easy, 1.0 = very hard
    estimated_time_seconds: int = 60
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GeneratedQuiz:
    """Complete generated quiz with all questions and metadata"""
    quiz_id: str
    title: str
    questions: List[QuizQuestion]
    total_questions: int
    estimated_duration_minutes: int
    difficulty_level: DifficultyLevel
    subject_area: str
    learning_objectives: List[str]
    generation_metadata: Dict[str, Any] = field(default_factory=dict)

class QuizGenerationService:
    """Intelligent Quiz Generation Service with AI-powered question creation"""
    
    def __init__(self):
        self.quiz_cache: Dict[str, GeneratedQuiz] = {}
        self.generation_templates = self._load_generation_templates()
    
    async def generate_quiz(
        self,
        user_id: int,
        request: QuizGenerationRequest,
        db: Session = None
    ) -> GeneratedQuiz:
        """Generate an intelligent, contextual quiz"""
        
        try:
            # Build resource context
            resource_context = await self._build_resource_context(
                request.resource_id,
                request.resource_type,
                db
            )
            
            # Generate questions using AI
            questions = await self._generate_questions_with_ai(
                resource_context,
                request
            )
            
            # Create quiz session in database
            quiz_session = QuizSession(
                user_id=user_id,
                resource_id=request.resource_id,
                resource_type=request.resource_type,
                quiz_type=request.quiz_type.value,
                question_count=len(questions),
                difficulty_level=request.difficulty_level.value,
                time_limit_minutes=request.time_limit_minutes,
                metadata={
                    "generation_request": request.__dict__,
                    "resource_context": resource_context,
                    "generation_timestamp": time.time()
                }
            )
            
            db.add(quiz_session)
            db.commit()
            db.refresh(quiz_session)
            
            # Save questions to database
            for i, question in enumerate(questions):
                db_question = QuizQuestion(
                    session_id=quiz_session.id,
                    question_number=i + 1,
                    question_text=question.question,
                    question_type=QuestionType(question.question_type.value),
                    options=question.options,
                    correct_answer=json.dumps(question.correct_answer),
                    explanation=question.explanation,
                    difficulty_score=question.difficulty_score,
                    estimated_time_seconds=question.estimated_time_seconds,
                    metadata=question.metadata
                )
                db.add(db_question)
            
            db.commit()
            
            # Create complete quiz object
            generated_quiz = GeneratedQuiz(
                quiz_id=str(quiz_session.id),
                title=f"Quiz: {resource_context.get('title', 'Study Quiz')}",
                questions=questions,
                total_questions=len(questions),
                estimated_duration_minutes=sum(q.estimated_time_seconds for q in questions) // 60 + 1,
                difficulty_level=request.difficulty_level,
                subject_area=resource_context.get('subject_area', 'General'),
                learning_objectives=resource_context.get('learning_objectives', []),
                generation_metadata={
                    "session_id": quiz_session.id,
                    "generated_at": time.time(),
                    "ai_model_used": "gpt-4",
                    "generation_version": "1.0"
                }
            )
            
            # Cache the quiz
            self.quiz_cache[str(quiz_session.id)] = generated_quiz
            
            return generated_quiz
            
        except Exception as e:
            logger.error(f"Error generating quiz: {e}")
            if db:
                db.rollback()
            raise e
    
    async def generate_adaptive_quiz(
        self,
        user_id: int,
        resource_id: str,
        user_performance_history: Dict[str, Any],
        db: Session = None
    ) -> GeneratedQuiz:
        """Generate adaptive quiz based on user's learning history and performance"""
        
        try:
            # Analyze user performance to determine optimal difficulty and focus areas
            adaptive_params = await self._analyze_user_performance(
                user_id,
                user_performance_history,
                db
            )
            
            # Create adaptive quiz request
            request = QuizGenerationRequest(
                resource_id=resource_id,
                quiz_type=adaptive_params["optimal_quiz_type"],
                question_count=adaptive_params["optimal_question_count"],
                difficulty_level=adaptive_params["optimal_difficulty"],
                focus_areas=adaptive_params["weak_areas"],
                time_limit_minutes=adaptive_params["optimal_time_limit"]
            )
            
            # Generate quiz with adaptive parameters
            quiz = await self.generate_quiz(user_id, request, db)
            
            # Add adaptive metadata
            quiz.generation_metadata.update({
                "adaptive_generation": True,
                "user_performance_analysis": adaptive_params,
                "personalization_level": "high"
            })
            
            return quiz
            
        except Exception as e:
            logger.error(f"Error generating adaptive quiz: {e}")
            raise e
    
    async def get_quiz(self, quiz_id: str, db: Session = None) -> Optional[GeneratedQuiz]:
        """Retrieve a generated quiz by ID"""
        
        try:
            # Check cache first
            if quiz_id in self.quiz_cache:
                return self.quiz_cache[quiz_id]
            
            # Load from database
            quiz_session = db.query(QuizSession).filter(QuizSession.id == int(quiz_id)).first()
            if not quiz_session:
                return None
            
            # Get questions
            db_questions = db.query(QuizQuestion).filter(
                QuizQuestion.session_id == quiz_session.id
            ).order_by(QuizQuestion.question_number).all()
            
            # Convert to quiz questions
            questions = []
            for db_q in db_questions:
                question = QuizQuestion(
                    question=db_q.question_text,
                    question_type=QuizType(db_q.question_type.value),
                    options=db_q.options,
                    correct_answer=json.loads(db_q.correct_answer) if db_q.correct_answer else None,
                    explanation=db_q.explanation,
                    difficulty_score=db_q.difficulty_score,
                    estimated_time_seconds=db_q.estimated_time_seconds,
                    metadata=db_q.metadata
                )
                questions.append(question)
            
            # Reconstruct quiz
            quiz = GeneratedQuiz(
                quiz_id=quiz_id,
                title=f"Quiz: {quiz_session.metadata.get('resource_context', {}).get('title', 'Study Quiz')}",
                questions=questions,
                total_questions=len(questions),
                estimated_duration_minutes=quiz_session.time_limit_minutes or sum(q.estimated_time_seconds for q in questions) // 60 + 1,
                difficulty_level=DifficultyLevel(quiz_session.difficulty_level),
                subject_area=quiz_session.metadata.get('resource_context', {}).get('subject_area', 'General'),
                learning_objectives=quiz_session.metadata.get('resource_context', {}).get('learning_objectives', []),
                generation_metadata=quiz_session.metadata
            )
            
            # Cache the quiz
            self.quiz_cache[quiz_id] = quiz
            
            return quiz
            
        except Exception as e:
            logger.error(f"Error retrieving quiz {quiz_id}: {e}")
            return None
    
    async def _build_resource_context(
        self,
        resource_id: str,
        resource_type: str,
        db: Session
    ) -> Dict[str, Any]:
        """Build comprehensive context for quiz generation"""
        
        try:
            context = {
                "resource_id": resource_id,
                "resource_type": resource_type,
                "title": "Study Topic",
                "subject_area": "General",
                "difficulty_level": "intermediate",
                "learning_objectives": [],
                "content_summary": "",
                "key_concepts": []
            }
            
            if resource_type == "course":
                course = db.query(Course).filter(Course.id == resource_id).first()
                if course:
                    context.update({
                        "title": course.title,
                        "subject_area": course.category or "General",
                        "difficulty_level": course.difficulty_level or "intermediate",
                        "learning_objectives": course.learning_objectives or [],
                        "content_summary": course.description or "",
                        "key_concepts": course.tags or []
                    })
            
            elif resource_type == "lesson":
                lesson = db.query(Lesson).filter(Lesson.id == resource_id).first()
                if lesson:
                    course = lesson.course
                    context.update({
                        "title": lesson.title,
                        "subject_area": course.category if course else "General",
                        "difficulty_level": course.difficulty_level if course else "intermediate",
                        "learning_objectives": lesson.learning_objectives or [],
                        "content_summary": lesson.content or "",
                        "key_concepts": lesson.tags or []
                    })
            
            return context
            
        except Exception as e:
            logger.error(f"Error building resource context: {e}")
            return {
                "resource_id": resource_id,
                "resource_type": resource_type,
                "title": "Study Topic",
                "subject_area": "General",
                "difficulty_level": "intermediate",
                "learning_objectives": [],
                "content_summary": "",
                "key_concepts": []
            }
    
    async def _generate_questions_with_ai(
        self,
        resource_context: Dict[str, Any],
        request: QuizGenerationRequest
    ) -> List[QuizQuestion]:
        """Generate quiz questions using AI with intelligent prompting"""
        
        try:
            # Build comprehensive AI prompt
            prompt = await self._build_generation_prompt(resource_context, request)
            
            # Use AI resilience manager for question generation
            ai_response = await ai_resilience_manager.chat_completion(
                message=prompt,
                model_preference="openai-gpt4",  # Use best model for question generation
                max_retries=3,
                use_cache=False  # Don't cache quiz generation for uniqueness
            )
            
            # Parse AI response into structured questions
            questions = await self._parse_ai_questions(ai_response["response"], request.quiz_type)
            
            # Validate and enhance questions
            validated_questions = await self._validate_and_enhance_questions(
                questions,
                resource_context,
                request
            )
            
            return validated_questions
            
        except Exception as e:
            logger.error(f"Error generating questions with AI: {e}")
            
            # Fallback to template-based generation
            return await self._generate_fallback_questions(resource_context, request)
    
    async def _build_generation_prompt(
        self,
        resource_context: Dict[str, Any],
        request: QuizGenerationRequest
    ) -> str:
        """Build comprehensive prompt for AI question generation"""
        
        template = self.generation_templates.get(request.quiz_type.value, self.generation_templates["multiple_choice"])
        
        prompt = f"""You are an expert educational assessment designer. Generate a high-quality {request.quiz_type.value} quiz.

CONTEXT:
- Topic: {resource_context['title']}
- Subject Area: {resource_context['subject_area']}
- Difficulty Level: {request.difficulty_level.value}
- Learning Objectives: {', '.join(resource_context['learning_objectives']) if resource_context['learning_objectives'] else 'General understanding'}
- Key Concepts: {', '.join(resource_context['key_concepts']) if resource_context['key_concepts'] else 'Core concepts'}

REQUIREMENTS:
- Generate exactly {request.question_count} questions
- Question type: {request.quiz_type.value}
- Difficulty: {request.difficulty_level.value}
- Focus areas: {', '.join(request.focus_areas) if request.focus_areas else 'All relevant topics'}

{template}

IMPORTANT: Respond with ONLY valid JSON. No additional text, explanations, or formatting.
"""
        
        return prompt
    
    async def _parse_ai_questions(
        self,
        ai_response: str,
        quiz_type: QuizType
    ) -> List[QuizQuestion]:
        """Parse AI response into structured quiz questions"""
        
        try:
            # Clean response and extract JSON
            cleaned_response = ai_response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            
            # Parse JSON
            questions_data = json.loads(cleaned_response)
            
            # Handle different response formats
            if isinstance(questions_data, dict) and "questions" in questions_data:
                questions_data = questions_data["questions"]
            elif isinstance(questions_data, dict) and "quiz" in questions_data:
                questions_data = questions_data["quiz"]
            
            questions = []
            for i, q_data in enumerate(questions_data):
                question = QuizQuestion(
                    question=q_data.get("question", f"Question {i+1}"),
                    question_type=quiz_type,
                    options=q_data.get("options", []) if quiz_type == QuizType.MULTIPLE_CHOICE else None,
                    correct_answer=q_data.get("correct_answer", q_data.get("answer", "")),
                    explanation=q_data.get("explanation", ""),
                    difficulty_score=q_data.get("difficulty", 0.5),
                    estimated_time_seconds=q_data.get("estimated_time", 60),
                    metadata={
                        "ai_generated": True,
                        "generation_confidence": q_data.get("confidence", 0.8)
                    }
                )
                questions.append(question)
            
            return questions
            
        except Exception as e:
            logger.error(f"Error parsing AI questions: {e}")
            # Return fallback question
            return [
                QuizQuestion(
                    question="What is the main concept you learned from this topic?",
                    question_type=QuizType.OPEN_ENDED,
                    correct_answer="Open-ended response",
                    explanation="Reflect on the key learnings from this topic.",
                    metadata={"fallback": True}
                )
            ]
    
    async def _validate_and_enhance_questions(
        self,
        questions: List[QuizQuestion],
        resource_context: Dict[str, Any],
        request: QuizGenerationRequest
    ) -> List[QuizQuestion]:
        """Validate and enhance generated questions"""
        
        enhanced_questions = []
        
        for i, question in enumerate(questions):
            # Validate question structure
            if not question.question or len(question.question.strip()) < 10:
                question.question = f"Question {i+1}: What is an important concept related to {resource_context['title']}?"
            
            # Ensure correct answer exists
            if not question.correct_answer:
                if question.question_type == QuizType.MULTIPLE_CHOICE and question.options:
                    question.correct_answer = question.options[0]
                else:
                    question.correct_answer = "Sample answer"
            
            # Set appropriate time estimates
            if question.estimated_time_seconds <= 0:
                time_estimates = {
                    QuizType.MULTIPLE_CHOICE: 45,
                    QuizType.TRUE_FALSE: 30,
                    QuizType.FILL_BLANK: 60,
                    QuizType.SHORT_ANSWER: 120,
                    QuizType.OPEN_ENDED: 300,
                    QuizType.MATCHING: 90
                }
                question.estimated_time_seconds = time_estimates.get(question.question_type, 60)
            
            # Adjust difficulty if needed
            if question.difficulty_score < 0 or question.difficulty_score > 1:
                difficulty_map = {
                    DifficultyLevel.BEGINNER: 0.3,
                    DifficultyLevel.INTERMEDIATE: 0.5,
                    DifficultyLevel.ADVANCED: 0.7,
                    DifficultyLevel.EXPERT: 0.9
                }
                question.difficulty_score = difficulty_map[request.difficulty_level]
            
            enhanced_questions.append(question)
        
        return enhanced_questions
    
    async def _generate_fallback_questions(
        self,
        resource_context: Dict[str, Any],
        request: QuizGenerationRequest
    ) -> List[QuizQuestion]:
        """Generate fallback questions when AI generation fails"""
        
        fallback_questions = []
        
        for i in range(request.question_count):
            if request.quiz_type == QuizType.MULTIPLE_CHOICE:
                question = QuizQuestion(
                    question=f"Which of the following best describes {resource_context['title']}?",
                    question_type=QuizType.MULTIPLE_CHOICE,
                    options=[
                        "A fundamental concept in the field",
                        "An advanced technique",
                        "A basic principle",
                        "A practical application"
                    ],
                    correct_answer="A fundamental concept in the field",
                    explanation="This question tests understanding of core concepts.",
                    difficulty_score=0.5,
                    metadata={"fallback": True}
                )
            
            elif request.quiz_type == QuizType.OPEN_ENDED:
                question = QuizQuestion(
                    question=f"Explain the main concepts you learned about {resource_context['title']}.",
                    question_type=QuizType.OPEN_ENDED,
                    correct_answer="Open-ended response about key concepts",
                    explanation="This question allows you to demonstrate your understanding.",
                    difficulty_score=0.6,
                    metadata={"fallback": True}
                )
            
            elif request.quiz_type == QuizType.TRUE_FALSE:
                question = QuizQuestion(
                    question=f"{resource_context['title']} is an important topic in {resource_context['subject_area']}.",
                    question_type=QuizType.TRUE_FALSE,
                    options=["True", "False"],
                    correct_answer="True",
                    explanation="This statement is generally true for most educational topics.",
                    difficulty_score=0.3,
                    metadata={"fallback": True}
                )
            
            else:
                # Default to short answer
                question = QuizQuestion(
                    question=f"What is one key takeaway from {resource_context['title']}?",
                    question_type=QuizType.SHORT_ANSWER,
                    correct_answer="Sample key takeaway",
                    explanation="Identify the most important concept you learned.",
                    difficulty_score=0.5,
                    metadata={"fallback": True}
                )
            
            fallback_questions.append(question)
        
        return fallback_questions
    
    async def _analyze_user_performance(
        self,
        user_id: int,
        performance_history: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """Analyze user performance to generate adaptive quiz parameters"""
        
        try:
            # Get recent quiz attempts
            recent_attempts = db.query(QuizAttempt).filter(
                QuizAttempt.user_id == user_id
            ).order_by(desc(QuizAttempt.created_at)).limit(10).all()
            
            # Calculate performance metrics
            if recent_attempts:
                avg_score = sum(attempt.score for attempt in recent_attempts) / len(recent_attempts)
                avg_completion_time = sum(attempt.completion_time_seconds for attempt in recent_attempts if attempt.completion_time_seconds) / len(recent_attempts)
            else:
                avg_score = 0.7  # Default assumption
                avg_completion_time = 300  # 5 minutes default
            
            # Determine adaptive parameters
            if avg_score >= 0.8:
                optimal_difficulty = DifficultyLevel.ADVANCED
                optimal_question_count = 8
            elif avg_score >= 0.6:
                optimal_difficulty = DifficultyLevel.INTERMEDIATE
                optimal_question_count = 6
            else:
                optimal_difficulty = DifficultyLevel.BEGINNER
                optimal_question_count = 4
            
            # Determine optimal quiz type based on performance
            optimal_quiz_type = QuizType.MULTIPLE_CHOICE
            if avg_score >= 0.7:
                optimal_quiz_type = QuizType.OPEN_ENDED  # More challenging for good performers
            
            return {
                "optimal_difficulty": optimal_difficulty,
                "optimal_question_count": optimal_question_count,
                "optimal_quiz_type": optimal_quiz_type,
                "optimal_time_limit": max(10, int(avg_completion_time / 60) + 5),
                "weak_areas": performance_history.get("weak_subjects", []),
                "performance_analysis": {
                    "avg_score": avg_score,
                    "avg_completion_time": avg_completion_time,
                    "total_attempts": len(recent_attempts)
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing user performance: {e}")
            
            # Return default adaptive parameters
            return {
                "optimal_difficulty": DifficultyLevel.INTERMEDIATE,
                "optimal_question_count": 5,
                "optimal_quiz_type": QuizType.MULTIPLE_CHOICE,
                "optimal_time_limit": 15,
                "weak_areas": [],
                "performance_analysis": {"error": str(e)}
            }
    
    def _load_generation_templates(self) -> Dict[str, str]:
        """Load AI generation templates for different quiz types"""
        
        return {
            "multiple_choice": """
Generate questions in this exact JSON format:
{
  "questions": [
    {
      "question": "Question text here?",
      "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
      "correct_answer": "A) Option 1",
      "explanation": "Brief explanation of why this is correct",
      "difficulty": 0.6,
      "estimated_time": 45
    }
  ]
}

Make questions challenging but fair. Include plausible distractors.
""",
            
            "open_ended": """
Generate questions in this exact JSON format:
{
  "questions": [
    {
      "question": "Question requiring detailed explanation?",
      "correct_answer": "Sample comprehensive answer covering key points",
      "explanation": "What a good answer should include",
      "difficulty": 0.7,
      "estimated_time": 180
    }
  ]
}

Focus on analysis, synthesis, and application of concepts.
""",
            
            "true_false": """
Generate questions in this exact JSON format:
{
  "questions": [
    {
      "question": "Statement to evaluate as true or false.",
      "options": ["True", "False"],
      "correct_answer": "True",
      "explanation": "Explanation of why this statement is true/false",
      "difficulty": 0.4,
      "estimated_time": 30
    }
  ]
}

Create nuanced statements that test deep understanding.
""",
            
            "short_answer": """
Generate questions in this exact JSON format:
{
  "questions": [
    {
      "question": "Question requiring brief but specific answer?",
      "correct_answer": "Expected short answer (1-3 sentences)",
      "explanation": "What the answer should cover",
      "difficulty": 0.5,
      "estimated_time": 90
    }
  ]
}

Focus on key facts, definitions, and essential concepts.
"""
        }

# Global service instance
quiz_generation_service = QuizGenerationService()
