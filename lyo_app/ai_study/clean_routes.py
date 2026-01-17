"""
Clean API Routes for AI Study Mode
Implementing the exact endpoints specified in the requirements
"""

import json
import os
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user
from lyo_app.models.enhanced import User
from lyo_app.core.monitoring import monitor_request
from lyo_app.core.ai_resilience import ai_resilience_manager
from .comprehensive_service import comprehensive_study_service
from lyo_app.core.personality import LYO_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["AI Study Mode"])

# ============================================================================
# REQUEST/RESPONSE SCHEMAS (Exact as specified)
# ============================================================================

class ConversationMessage(BaseModel):
    """Message in conversation history"""
    role: str = Field(..., description="system|user|assistant")
    content: str = Field(..., description="Message content")

class StudySessionRequest(BaseModel):
    """Study session request - exactly as specified"""
    resourceId: str = Field(..., description="ID of learning resource")
    conversationHistory: List[ConversationMessage] = Field(default_factory=list, description="Chat history")
    userInput: str = Field(..., description="User's latest message")

class StudySessionResponse(BaseModel):
    """Study session response"""
    response: str = Field(..., description="AI tutor response")
    conversationHistory: List[ConversationMessage] = Field(..., description="Updated conversation history")

class QuizGenerationRequest(BaseModel):
    """Quiz generation request - exactly as specified"""
    resourceId: str = Field(..., description="Learning resource ID")
    quizType: str = Field(default="multiple_choice", description="Type of quiz")
    questionCount: int = Field(default=5, description="Number of questions")

class QuizQuestion(BaseModel):
    """Individual quiz question"""
    question: str
    options: List[str]
    correctAnswer: str

class AnswerAnalysisRequest(BaseModel):
    """Answer analysis request - exactly as specified"""
    question: str = Field(..., description="The quiz question")
    correctAnswer: str = Field(..., description="The correct answer")
    userAnswer: str = Field(..., description="User's answer")

# ============================================================================
# PHASE 2: AI STUDY MODE ENDPOINTS (Exact Implementation)
# ============================================================================

@router.post("/study-session")
@monitor_request("ai_study_session")
async def study_session_endpoint(
    request: StudySessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StudySessionResponse:
    """
    POST /api/v1/ai/study-session
    Stateful conversation endpoint for Socratic dialogue.
    
    Manages ongoing, Socratic dialogue with the user by:
    1. Constructing system prompt for the Google Gemini API
    2. Appending userInput to conversationHistory
    3. Sending entire history to Google Gemini
    4. Returning AI response with updated conversation history
    """
    
    try:
        # 1. Construct system prompt for the specific resourceId
        system_prompt = LYO_SYSTEM_PROMPT + f"""

---
**STUDY MODE SPECIFIC INSTRUCTIONS:**
You are helping a student learn about the topic: {request.resourceId}.

Your role in this Study Session:
- Guide the student through discovery-based learning
- Ask probing questions that lead to insights
- Never give direct answers; guide students to find answers themselves
- Be encouraging and patient
- Break complex concepts into digestible parts
- Celebrate student progress and insights

Focus on the learning material: {request.resourceId}
Use the Socratic method to facilitate deep understanding.
"""
        
        # 2. Build complete conversation history
        messages = []
        
        # Add system prompt
        messages.append({"role": "system", "content": system_prompt})
        
        # 3. Add conversation history
        for msg in request.conversationHistory:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # 4. Append the userInput to conversationHistory
        messages.append({"role": "user", "content": request.userInput})
        
        # 5. Send entire history to Google Gemini API
        ai_response = await ai_resilience_manager.chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            provider_order=["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.0-flash-lite"]  # Google Gemini models
        )
        
        # 6. Build updated conversation history to maintain state
        updated_history = []
        
        # Add existing conversation
        for msg in request.conversationHistory:
            updated_history.append(ConversationMessage(
                role=msg.role,
                content=msg.content
            ))
        
        # Add new user message
        updated_history.append(ConversationMessage(
            role="user",
            content=request.userInput
        ))
        
        # Add AI response
        updated_history.append(ConversationMessage(
            role="assistant",
            content=ai_response["content"]
        ))
        
        # Store conversation in database for persistence
        await _store_conversation_state(
            user_id=current_user.id,
            resource_id=request.resourceId,
            user_input=request.userInput,
            ai_response=ai_response["content"],
            conversation_history=updated_history,
            db=db
        )
        
        logger.info(f"Study session completed for user {current_user.id}, resource {request.resourceId}")
        
        return StudySessionResponse(
            response=ai_response["content"],
            conversationHistory=updated_history
        )
        
    except Exception as e:
        logger.error(f"Study session failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Study session failed: {str(e)}"
        )

@router.post("/generate-quiz")
@monitor_request("ai_quiz_generation")
async def generate_quiz_endpoint(
    request: QuizGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[QuizQuestion]:
    """
    POST /api/v1/ai/generate-quiz
    On-demand quiz generation endpoint.
    
    Creates contextual quizzes by:
    1. Creating one-shot prompt for Google Gemini API
    2. Instructing AI to generate quiz based on learning resource content
    3. Formatting output as valid JSON array
    4. Parsing and validating JSON before returning to client
    """
    
    try:
        # Get resource content for context (placeholder - implement based on your LMS)
        resource_content = await _get_resource_content(request.resourceId)
        
        # 1. Create one-shot prompt for the OpenAI API
        quiz_prompt = f"""
        Generate exactly {request.questionCount} {request.quizType} questions based on this learning content.
        
        Learning Resource: {request.resourceId}
        Content: {resource_content}
        
        IMPORTANT: Format your response as a valid JSON array ONLY. No other text.
        
        Required format:
        [
            {{
                "question": "Question text here",
                "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
                "correctAnswer": "A"
            }}
        ]
        
        Requirements:
        - Test understanding, not memorization
        - Questions should be clear and unambiguous
        - Provide exactly 4 options for multiple choice
        - Mark correct answer with letter (A, B, C, or D)
        - Focus on key concepts from the learning material
        
        Generate ONLY the JSON array, no additional text.
        """
        
        # 2. Send to Google Gemini with instruction to format as valid JSON
        ai_response = await ai_resilience_manager.chat_completion(
            messages=[{"role": "user", "content": quiz_prompt}],
            temperature=0.3,  # Lower temperature for consistency
            max_tokens=2000,
            provider_order=["gemini-2.0-flash", "gemini-2.0-flash-lite"]  # Google Gemini models
        )
        
        # 3. Parse and validate the JSON from AI before sending to client
        try:
            # Clean the response (remove any markdown formatting)
            json_content = ai_response["content"].strip()
            if json_content.startswith("```json"):
                json_content = json_content.replace("```json", "").replace("```", "").strip()
            elif json_content.startswith("```"):
                json_content = json_content.replace("```", "").strip()
            
            # Parse JSON
            quiz_data = json.loads(json_content)
            
            # Validate it's a list
            if not isinstance(quiz_data, list):
                raise ValueError("AI response must be a JSON array")
            
            # Validate and format questions
            validated_questions = []
            for i, q in enumerate(quiz_data):
                if not isinstance(q, dict) or "question" not in q:
                    continue
                
                # Ensure required fields exist
                question = QuizQuestion(
                    question=q.get("question", f"Question {i+1}"),
                    options=q.get("options", ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"]),
                    correctAnswer=q.get("correctAnswer", "A")
                )
                validated_questions.append(question)
            
            # Store quiz in database
            await _store_generated_quiz(
                user_id=current_user.id,
                resource_id=request.resourceId,
                quiz_type=request.quizType,
                questions=validated_questions,
                ai_metadata=ai_response,
                db=db
            )
            
            logger.info(f"Quiz generated for user {current_user.id}, resource {request.resourceId}")
            
            return validated_questions
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI quiz response as JSON: {e}")
            logger.debug(f"AI response was: {ai_response['content']}")
            
            # Return fallback quiz if JSON parsing fails
            return _generate_fallback_quiz(request.questionCount, request.quizType)
    
    except Exception as e:
        logger.error(f"Quiz generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quiz generation failed: {str(e)}"
        )

@router.post("/analyze-answer")
@monitor_request("ai_answer_analysis")
async def analyze_answer_endpoint(
    request: AnswerAnalysisRequest,
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    POST /api/v1/ai/analyze-answer
    Personalized feedback endpoint.
    
    Provides constructive feedback by:
    1. Sending details to Google Gemini API for comparison
    2. Instructing AI to provide encouraging, helpful feedback
    3. Explaining why answer may be incorrect and guiding toward right concept
    4. Not giving answer away, but guiding learning
    """
    
    try:
        # Build analysis prompt for AI
        feedback_prompt = f"""
        You are an encouraging AI tutor providing feedback on a student's quiz answer.
        
        Question: {request.question}
        Correct Answer: {request.correctAnswer}
        Student's Answer: {request.userAnswer}
        
        Your task:
        1. Compare the student's answer to the correct answer
        2. Provide encouraging, helpful feedback
        3. If incorrect, explain WHY it may be wrong without giving away the answer
        4. Guide the student toward the right concept or thinking process
        5. Be supportive and educational
        6. Encourage further learning and exploration
        
        Do not simply state the correct answer. Instead, guide the student to understand
        the underlying concepts and reasoning.
        
        Provide personalized, constructive feedback that helps the student learn.
        """
        
        # Send to Google Gemini for analysis
        ai_response = await ai_resilience_manager.chat_completion(
            messages=[{"role": "user", "content": feedback_prompt}],
            temperature=0.6,  # Moderate temperature for personalized but consistent feedback
            max_tokens=500,
            provider_order=["gemini-2.0-flash", "gemini-2.0-flash-lite"]  # Google Gemini models
        )
        
        logger.info(f"Answer analysis completed for user {current_user.id}")
        
        # Return as string containing personalized feedback
        return {"feedback": ai_response["content"]}
        
    except Exception as e:
        logger.error(f"Answer analysis failed: {e}", exc_info=True)
        
        # Fallback response
        return {
            "feedback": "Thank you for your answer. Please review the learning material and consider the key concepts we've discussed. Keep thinking about the underlying principles, and don't hesitate to ask questions if you need clarification!"
        }

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _store_conversation_state(
    user_id: int,
    resource_id: str,
    user_input: str,
    ai_response: str,
    conversation_history: List[ConversationMessage],
    db: AsyncSession
):
    """Store conversation state for persistence"""
    
    try:
        from .models import StudySession, StudyMessage, StudySessionStatus, MessageRole
        from sqlalchemy import select, and_
        
        # Get or create study session
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
        
        if not session:
            session = StudySession(
                user_id=user_id,
                resource_id=resource_id,
                resource_title=f"Learning: {resource_id}",
                status=StudySessionStatus.ACTIVE,
                tutor_personality="socratic"
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
        
        # Store the latest user message and AI response
        user_message = StudyMessage(
            session_id=session.id,
            role=MessageRole.USER,
            content=user_input,
            created_at=datetime.utcnow()
        )
        
        ai_message = StudyMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=ai_response,
            created_at=datetime.utcnow()
        )
        
        db.add(user_message)
        db.add(ai_message)
        
        # Update session stats
        session.message_count = len(conversation_history)
        session.last_activity_at = datetime.utcnow()
        
        await db.commit()
        
    except Exception as e:
        logger.error(f"Failed to store conversation state: {e}")
        # Don't fail the main request if storage fails

async def _get_resource_content(resource_id: str) -> str:
    """Get learning resource content for quiz generation context"""
    
    # Placeholder implementation - integrate with your learning management system
    # This should fetch actual content from your database/CMS
    
    content_samples = {
        "machine_learning_basics": """
        Machine Learning is a subset of artificial intelligence that enables computers to learn and make decisions from data without being explicitly programmed. Key concepts include:
        
        1. Supervised Learning: Learning from labeled training data
        2. Unsupervised Learning: Finding patterns in unlabeled data  
        3. Reinforcement Learning: Learning through rewards and penalties
        
        Common algorithms include linear regression, decision trees, neural networks, and clustering.
        Applications span across recommendation systems, image recognition, natural language processing, and predictive analytics.
        """,
        "python_fundamentals": """
        Python is a high-level programming language known for its simplicity and readability. Key concepts include:
        
        1. Variables and Data Types: strings, integers, floats, booleans
        2. Control Structures: if statements, loops (for, while)
        3. Functions: reusable blocks of code with parameters and return values
        4. Data Structures: lists, dictionaries, tuples, sets
        
        Python follows the principle of readability and uses indentation to define code blocks.
        It's widely used in web development, data science, automation, and machine learning.
        """,
        "default": f"""
        Learning content for {resource_id}:
        
        This resource covers fundamental concepts and practical applications.
        Key learning objectives include understanding core principles,
        applying knowledge to real-world scenarios, and developing
        critical thinking skills in the subject area.
        
        Students should focus on comprehension, analysis, and synthesis
        of the material to achieve mastery.
        """
    }
    
    return content_samples.get(resource_id, content_samples["default"])

async def _store_generated_quiz(
    user_id: int,
    resource_id: str,
    quiz_type: str,
    questions: List[QuizQuestion],
    ai_metadata: Dict[str, Any],
    db: AsyncSession
):
    """Store generated quiz in database"""
    
    try:
        from .models import GeneratedQuiz, QuizType
        
        # Convert questions to JSON format for storage
        questions_json = []
        for q in questions:
            questions_json.append({
                "question": q.question,
                "options": q.options,
                "correctAnswer": q.correctAnswer
            })
        
        quiz = GeneratedQuiz(
            user_id=user_id,
            resource_id=resource_id,
            quiz_type=QuizType.MULTIPLE_CHOICE,  # Default to multiple choice
            title=f"AI Generated Quiz: {resource_id}",
            description=f"Quiz with {len(questions)} questions",
            questions=questions_json,
            question_count=len(questions),
            estimated_duration_minutes=len(questions) * 2,
            ai_model_used=ai_metadata.get("model", "unknown"),
            generation_time_ms=int(ai_metadata.get("response_time", 0) * 1000),
            generation_token_count=ai_metadata.get("tokens_used", 0)
        )
        
        db.add(quiz)
        await db.commit()
        
    except Exception as e:
        logger.error(f"Failed to store quiz: {e}")
        # Don't fail the main request if storage fails

def _generate_fallback_quiz(question_count: int, quiz_type: str) -> List[QuizQuestion]:
    """Generate fallback quiz when AI fails"""
    
    fallback_questions = []
    
    for i in range(question_count):
        question = QuizQuestion(
            question=f"Sample question {i+1}: What is a key concept from this learning material?",
            options=[
                f"A) Concept option {i+1}A",
                f"B) Concept option {i+1}B", 
                f"C) Concept option {i+1}C",
                f"D) Concept option {i+1}D"
            ],
            correctAnswer="A"
        )
        fallback_questions.append(question)
    
    return fallback_questions


# ============================================================================
# A2UI WIDGET DETECTION LOGIC
# ============================================================================

def _detect_a2ui_widgets(message: str, context: str, ai_response: str) -> List["ContentTypePayload"]:
    """
    Detect which A2UI widgets to render based on message context, intent, AND AI response.
    
    This function analyzes:
    1. User's message for intent keywords
    2. Context mode (course, quiz, study)
    3. AI response content for structured output indicators
    
    Returns a list of widgets to render alongside the text response.
    """
    widgets = []
    message_lower = message.lower()
    context_lower = context.lower() if context else ""
    response_lower = ai_response.lower() if ai_response else ""
    
    # Track if we added any interactive widgets
    added_interactive_widget = False
    
    # ============================================================================
    # TOPIC SELECTION Widget
    # Triggered when user asks for recommendations OR AI suggests topics
    # ============================================================================
    topic_triggers = [
        "what should i learn",
        "recommend",
        "suggest",
        "help me choose",
        "what topic",
        "where should i start",
        "learning path"
    ]
    
    # Check both message AND AI response for topic selection indicators
    topic_in_message = any(trigger in message_lower for trigger in topic_triggers)
    topic_in_response = any(phrase in response_lower for phrase in ["choose from", "pick a topic", "select a subject", "you might enjoy"])
    
    if topic_in_message or topic_in_response:
        widgets.append(ContentTypePayload(
            type="topic_selection",  # snake_case for iOS
            title="Choose Your Path",
            topics=[
                TopicOptionPayload(title="Mathematics", icon="x.squareroot", gradientColors=["#FF512F", "#DD2476"]),
                TopicOptionPayload(title="Programming", icon="chevron.left.slash.chevron.right", gradientColors=["#4CB8C4", "#3CD3AD"]),
                TopicOptionPayload(title="Science", icon="atom", gradientColors=["#1FA2FF", "#12D8FA"]),
                TopicOptionPayload(title="Languages", icon="textformat", gradientColors=["#F857A6", "#FF5858"]),
                TopicOptionPayload(title="History", icon="book.fill", gradientColors=["#6366F1", "#8B5CF6"])
            ]
        ))
        added_interactive_widget = True
    
    # ============================================================================
    # COURSE ROADMAP Widget  
    # Triggered when in course mode, discussing structure, OR AI outputs course content
    # ============================================================================
    course_triggers = ["course", "module", "lesson", "curriculum", "syllabus", "learn", "teach me", "create a course"]
    course_response_indicators = ["module 1:", "lesson 1:", "here's the course", "course outline", "we'll cover"]
    
    course_in_message = any(trigger in message_lower for trigger in course_triggers)
    course_in_response = any(indicator in response_lower for indicator in course_response_indicators)
    course_mode = "mode=course" in context_lower
    
    if course_mode or course_in_message or course_in_response:
        # Build nested structure for iOS A2UIContent
        roadmap = A2UICourseRoadmapPayload(
            title="Course Roadmap",
            topic=message[:50] if message else "Learning",  # Extract topic from message
            level="beginner",
            modules=[
                A2UIModulePayload(
                    title="Introduction",
                    description="Getting started with the basics",
                    lessons=[A2UILessonPayload(title="Welcome", duration="5 min")]
                ),
                A2UIModulePayload(
                    title="Core Concepts",
                    description="Understanding the fundamentals",
                    lessons=[A2UILessonPayload(title="Key Ideas", duration="15 min")]
                ),
                A2UIModulePayload(
                    title="Practice",
                    description="Apply what you've learned",
                    lessons=[A2UILessonPayload(title="Exercises", duration="20 min")]
                ),
                A2UIModulePayload(
                    title="Assessment",
                    description="Test your knowledge",
                    lessons=[A2UILessonPayload(title="Quiz", duration="10 min")]
                )
            ]
        )
        
        widgets.append(ContentTypePayload(
            type="course_roadmap",  # snake_case for iOS
            title="Course Roadmap",
            course_roadmap=roadmap,  # Nested structure for iOS
            # Also include flat format for backwards compatibility
            modules=[
                CourseModulePayload(title="Introduction", duration="5 min", isCompleted=True),
                CourseModulePayload(title="Core Concepts", duration="15 min", isCompleted=False),
                CourseModulePayload(title="Practice", duration="20 min", isLocked=True),
                CourseModulePayload(title="Assessment", duration="10 min", isLocked=True)
            ],
            totalModules=4,
            completedModules=1
        ))
        added_interactive_widget = True
    
    # ============================================================================
    # FLASHCARDS Widget
    # Triggered in study mode, when user wants to memorize/review, OR AI explains concepts
    # ============================================================================
    flashcard_triggers = ["flashcard", "memorize", "review", "study card", "vocabulary", "key terms", "define"]
    flashcard_response_indicators = ["definition:", "key term:", "remember that", "important concept"]
    
    flashcard_in_message = any(trigger in message_lower for trigger in flashcard_triggers)
    flashcard_in_response = any(indicator in response_lower for indicator in flashcard_response_indicators)
    study_mode = "mode=study" in context_lower
    
    if study_mode or flashcard_in_message or flashcard_in_response:
        widgets.append(ContentTypePayload(
            type="flashcards",
            title="Study Flashcards",
            cards=[
                FlashcardPayload(front="What is a variable?", back="A named storage location that holds a value", hint="Think of it as a container"),
                FlashcardPayload(front="What is a function?", back="A reusable block of code that performs a specific task", hint="Called by name"),
                FlashcardPayload(front="What is a loop?", back="A control structure that repeats code while a condition is true", hint="for, while, etc.")
            ]
        ))
        added_interactive_widget = True
    
    # ============================================================================
    # QUIZ Widget
    # Triggered in quiz/test mode, when user wants to test, OR AI asks questions
    # ============================================================================
    quiz_triggers = ["quiz", "test me", "check my", "assessment", "practice question", "test yourself"]
    quiz_response_indicators = ["question:", "which of the following", "true or false", "what is the answer"]
    
    quiz_in_message = any(trigger in message_lower for trigger in quiz_triggers)
    quiz_in_response = any(indicator in response_lower for indicator in quiz_response_indicators)
    quiz_mode = "mode=quiz" in context_lower or "mode=test" in context_lower
    
    if quiz_mode or quiz_in_message or quiz_in_response:
        # Build nested quiz structure for iOS
        quiz_payload = A2UIQuizPayload(
            title="Quick Quiz",
            questions=[
                A2UIQuizQuestionPayload(
                    question="What is the primary benefit of using variables in programming?",
                    options=[
                        "A) They make code run faster",
                        "B) They allow you to store and reuse values",
                        "C) They are required by all programming languages",
                        "D) They reduce file size"
                    ],
                    correct_answer="B) They allow you to store and reuse values"
                )
            ]
        )
        
        widgets.append(ContentTypePayload(
            type="quiz",
            title="Quick Quiz",
            quiz=quiz_payload,  # Nested structure for iOS
            # Also keep flat format for backwards compatibility
            question="What is the primary benefit of using variables in programming?",
            options=[
                "A) They make code run faster",
                "B) They allow you to store and reuse values",
                "C) They are required by all programming languages",
                "D) They reduce file size"
            ],
            correctIndex=1,
            explanation="Variables allow you to store data that can be used and modified throughout your program."
        ))
        added_interactive_widget = True
    
    # ============================================================================
    # SUGGESTIONS Widget (FALLBACK)
    # Always add smart suggestions if no other interactive widget was added
    # This ensures every response has an A2UI component for engagement
    # ============================================================================
    if not added_interactive_widget:
        # Generate contextual suggestions based on message
        suggestions = _generate_contextual_suggestions(message_lower, response_lower)
        widgets.append(ContentTypePayload(
            type="suggestions",
            title="What's next?",
            suggestions=suggestions
        ))
    
    return widgets


def _generate_contextual_suggestions(message: str, response: str) -> List[str]:
    """Generate smart follow-up suggestions based on context."""
    # Default suggestions
    suggestions = [
        "Tell me more",
        "Create a course",
        "Quiz me",
        "Give examples"
    ]
    
    # Contextual overrides
    if "python" in message or "python" in response:
        suggestions = ["Python basics course", "Practice coding", "Show syntax examples", "Quiz on Python"]
    elif "math" in message or "math" in response:
        suggestions = ["Math course", "Practice problems", "Step-by-step solution", "Visual explanation"]
    elif "history" in message or "history" in response:
        suggestions = ["Timeline view", "Key events quiz", "Deep dive", "Related topics"]
    elif any(word in message for word in ["explain", "what is", "how does"]):
        suggestions = ["More details", "Simple analogy", "Real-world example", "Quiz me"]
    
    return suggestions


# ============================================================================
# PUBLIC AI CHAT ENDPOINT (NO AUTH REQUIRED)
# ============================================================================

class ChatRequest(BaseModel):
    """Simple chat request"""
    message: str = Field(..., description="User's message")
    conversationHistory: Optional[List[ConversationMessage]] = Field(default=None, alias="conversation_history", description="Optional chat history")
    context: Optional[str] = Field(default=None, description="Optional context like course topic")

    class Config:
        populate_by_name = True


# ============================================================================
# A2UI CONTENT TYPE MODELS (iOS Compatible)
# ============================================================================

class TopicOptionPayload(BaseModel):
    """Topic option for topic selection widget"""
    title: str
    icon: Optional[str] = "book.fill"
    gradientColors: Optional[List[str]] = ["#6366F1", "#8B5CF6"]
    
    class Config:
        populate_by_name = True

class CourseModulePayload(BaseModel):
    """Module for course roadmap widget - flat format for iOS CourseModule"""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    title: str
    duration: Optional[str] = None
    isCompleted: bool = False
    isLocked: bool = False
    
    class Config:
        populate_by_name = True

# Nested structures for iOS A2UI compatibility
class A2UILessonPayload(BaseModel):
    """Lesson for nested course roadmap"""
    title: str
    duration: str = "10 min"

class A2UIModulePayload(BaseModel):
    """Module with lessons for nested course roadmap"""
    title: str
    description: str = ""
    lessons: List[A2UILessonPayload] = []

class A2UICourseRoadmapPayload(BaseModel):
    """Nested course roadmap structure for iOS"""
    title: str
    topic: str
    level: str = "beginner"
    modules: List[A2UIModulePayload] = []

class A2UIQuizQuestionPayload(BaseModel):
    """Quiz question for iOS"""
    question: str
    options: List[str]
    correct_answer: str
    
    class Config:
        populate_by_name = True

class A2UIQuizPayload(BaseModel):
    """Nested quiz structure for iOS"""
    title: str
    questions: List[A2UIQuizQuestionPayload] = []

class FlashcardPayload(BaseModel):
    """Flashcard for flashcard widget"""
    front: str
    back: str
    hint: Optional[str] = None

class ContentTypePayload(BaseModel):
    """
    A2UI content type union - iOS Compatible
    
    Type values use snake_case for iOS compatibility:
    - text, processing, topic_selection, course_roadmap, flashcards, quiz, suggestions
    
    For course_roadmap and quiz, use nested structure with course_roadmap/quiz fields
    """
    type: str  # text, processing, topic_selection, course_roadmap, flashcards, quiz, suggestions
    
    # Processing widget
    step: Optional[str] = None
    progress: Optional[float] = None
    
    # Topic selection widget
    title: Optional[str] = None
    topics: Optional[List[TopicOptionPayload]] = None
    
    # Course roadmap widget - NESTED structure for iOS
    course_roadmap: Optional[A2UICourseRoadmapPayload] = None
    # Also keep flat format for backwards compatibility
    modules: Optional[List[CourseModulePayload]] = None
    totalModules: Optional[int] = None
    completedModules: Optional[int] = None
    
    # Flashcards widget
    cards: Optional[List[FlashcardPayload]] = None
    
    # Quiz widget - NESTED structure for iOS
    quiz: Optional[A2UIQuizPayload] = None
    # Also keep flat format for backwards compatibility
    question: Optional[str] = None
    options: Optional[List[str]] = None
    correctIndex: Optional[int] = None
    explanation: Optional[str] = None
    
    # Suggestions widget (fallback for engagement)
    suggestions: Optional[List[str]] = None
    
    class Config:
        populate_by_name = True


class ChatResponse(BaseModel):
    """Enhanced chat response with A2UI content types"""
    response: str = Field(..., description="AI response text")
    contentTypes: List[ContentTypePayload] = Field(default_factory=list, description="A2UI widget payloads")
    conversationHistory: List[ConversationMessage] = Field(..., description="Updated conversation history")

    class Config:
        populate_by_name = True

@router.post("/chat")
async def public_chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    POST /api/v1/ai/chat
    Public AI chat endpoint - NO AUTHENTICATION REQUIRED
    
    Simple chat interface for quick AI interactions.
    Used by iOS app for course generation and general AI chat.
    Now with A2UI widget support!
    """
    try:
        # Ensure AI manager is initialized
        if not ai_resilience_manager.session:
            await ai_resilience_manager.initialize()
        
        # Build system prompt
        system_prompt = LYO_SYSTEM_PROMPT + "\n\n**ADDITIONAL INSTRUCTIONS:**\nBe concise but thorough. Use examples when helpful."

        if request.context:
            system_prompt += f"\n\nContext: {request.context}"
            # Force structured output for course mode to trigger client-side widgets
            if "mode=course" in request.context.lower():
                system_prompt += "\n\nIMPORTANT: The user is in COURSE MODE. You MUST structure your response as a course outline.\nFormat your response to include:\n\"Course Title: [Title]\"\n\"Module 1: [Title]\" - [Description]\n\"Module 2: [Title]\" - [Description]\netc.\n\nKeep the intro brief and focus on the roadmap."

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history if provided
        if request.conversationHistory:
            for msg in request.conversationHistory:
                messages.append({"role": msg.role, "content": msg.content})
        
        # Add current message
        messages.append({"role": "user", "content": request.message})
        
        # Call AI
        ai_response = await ai_resilience_manager.chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            provider_order=["gemini-2.0-flash", "gemini-2.5-flash", "openai"]
        )
        
        # Extract content with fallback
        response_content = ai_response.get("content", ai_response.get("response", "I apologize, but I couldn't generate a response. Please try again."))
        
        # ============================================================================
        # A2UI WIDGET DETECTION
        # ============================================================================
        content_types = _detect_a2ui_widgets(
            message=request.message,
            context=request.context or "",
            ai_response=response_content
        )
        
        # Build updated history
        updated_history = []
        if request.conversationHistory:
            for msg in request.conversationHistory:
                updated_history.append(ConversationMessage(role=msg.role, content=msg.content))
        
        updated_history.append(ConversationMessage(role="user", content=request.message))
        updated_history.append(ConversationMessage(role="assistant", content=response_content))
        
        logger.info(f"Public chat completed with {len(content_types)} A2UI widgets")
        
        return ChatResponse(
            response=response_content,
            contentTypes=content_types,
            conversationHistory=updated_history
        )
        
    except Exception as e:
        logger.error(f"Public chat failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {str(e)}"
        )


# ============================================================================
# COURSE GENERATION ENDPOINT (NO AUTH REQUIRED)
# ============================================================================

class CourseLessonResponse(BaseModel):
    """Individual lesson in a course"""
    id: str = Field(..., description="Unique lesson ID")
    title: str = Field(..., description="Lesson title")
    description: str = Field(..., description="Lesson description")
    content: str = Field(..., description="Full lesson content")
    duration_minutes: int = Field(default=15, description="Estimated duration")
    order: int = Field(..., description="Order within module")

class CourseModuleResponse(BaseModel):
    """Module containing lessons"""
    id: str = Field(..., description="Unique module ID")
    title: str = Field(..., description="Module title")
    description: str = Field(..., description="Module description")
    lessons: List[CourseLessonResponse] = Field(..., description="Lessons in this module")
    order: int = Field(..., description="Order within course")

class CourseGenerationRequest(BaseModel):
    """Request to generate a full course"""
    topic: str = Field(..., description="Course topic/title")
    description: Optional[str] = Field(default=None, description="Optional description")
    difficulty: str = Field(default="intermediate", description="beginner/intermediate/advanced")
    num_modules: int = Field(default=3, ge=1, le=10, description="Number of modules")
    lessons_per_module: int = Field(default=3, ge=1, le=10, description="Lessons per module")

class CourseGenerationResponse(BaseModel):
    """Generated course response"""
    id: str = Field(..., description="Generated course ID")
    title: str = Field(..., description="Course title")
    description: str = Field(..., description="Course description")
    difficulty: str = Field(..., description="Difficulty level")
    estimated_hours: float = Field(..., description="Estimated completion time")
    modules: List[CourseModuleResponse] = Field(..., description="Course modules")
    generated_at: str = Field(..., description="Generation timestamp")

@router.post("/generate-course", response_model=CourseGenerationResponse)
async def generate_course_endpoint(request: CourseGenerationRequest) -> CourseGenerationResponse:
    """
    POST /api/v1/ai/generate-course
    Generate a complete AI course - NO AUTHENTICATION REQUIRED
    
    Creates a structured course with modules and lessons using AI.
    This is a public endpoint for the iOS course generation feature.
    """
    try:
        import uuid
        from datetime import datetime
        
        logger.info(f"Generating course for topic: {request.topic}")
        
        # Build the prompt for course generation
        course_prompt = f"""Generate a comprehensive educational course on the topic: "{request.topic}"

Requirements:
- Difficulty level: {request.difficulty}
- Number of modules: {request.num_modules}
- Lessons per module: {request.lessons_per_module}
{f'- Additional context: {request.description}' if request.description else ''}

Generate the course in the following JSON format ONLY (no other text):
{{
    "title": "Course Title",
    "description": "A comprehensive description of the course",
    "modules": [
        {{
            "title": "Module 1 Title",
            "description": "Module description",
            "lessons": [
                {{
                    "title": "Lesson 1 Title",
                    "description": "Brief lesson description",
                    "content": "Full detailed lesson content with explanations, examples, and key concepts. Make this substantial and educational.",
                    "duration_minutes": 15
                }}
            ]
        }}
    ]
}}

Make the content educational, engaging, and appropriate for the {request.difficulty} level.
Each lesson should have substantial, useful content (at least 200 words).
Include practical examples and clear explanations."""

        # Call AI to generate course
        ai_response = await ai_resilience_manager.chat_completion(
            messages=[{"role": "user", "content": course_prompt}],
            temperature=0.7,
            max_tokens=4000,
            provider_order=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash-lite"]
        )
        
        # Check for fallback response (AI service unavailable)
        if ai_response.get("is_fallback") or ai_response.get("model") == "fallback":
            logger.warning("AI returned fallback response, generating fallback course")
            course_data = _generate_fallback_course(request)
        else:
            # Parse the JSON response
            try:
                # Handle both "content" and "response" keys
                json_content = (ai_response.get("content") or ai_response.get("response", "{}")).strip()
                # Clean markdown formatting if present
                if json_content.startswith("```json"):
                    json_content = json_content.replace("```json", "").replace("```", "").strip()
                elif json_content.startswith("```"):
                    json_content = json_content.replace("```", "").strip()
                
                # Clean common JSON issues
                import re
                # Fix unescaped backslashes (e.g. LaTeX) by doubling them if not followed by valid escape char
                # This is a heuristic
                json_content = re.sub(r'\\(?![/u"bfnrt\\])', r'\\\\', json_content)
                
                course_data = json.loads(json_content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI course response: {e}")
                logger.debug(f"AI response was: {str(ai_response)[:500]}...")
                # Generate fallback course
                course_data = _generate_fallback_course(request)
        
        # Build response with proper IDs
        course_id = str(uuid.uuid4())
        modules = []
        total_duration = 0
        
        for mod_idx, mod_data in enumerate(course_data.get("modules", [])):
            module_id = str(uuid.uuid4())
            lessons = []
            
            for les_idx, les_data in enumerate(mod_data.get("lessons", [])):
                lesson_id = str(uuid.uuid4())
                duration = les_data.get("duration_minutes", 15)
                total_duration += duration
                
                lessons.append(CourseLessonResponse(
                    id=lesson_id,
                    title=les_data.get("title", f"Lesson {les_idx + 1}"),
                    description=les_data.get("description", ""),
                    content=les_data.get("content", "Content coming soon..."),
                    duration_minutes=duration,
                    order=les_idx + 1
                ))
            
            modules.append(CourseModuleResponse(
                id=module_id,
                title=mod_data.get("title", f"Module {mod_idx + 1}"),
                description=mod_data.get("description", ""),
                lessons=lessons,
                order=mod_idx + 1
            ))
        
        estimated_hours = round(total_duration / 60, 1)
        
        logger.info(f"Course generated successfully: {course_data.get('title', request.topic)}")
        
        return CourseGenerationResponse(
            id=course_id,
            title=course_data.get("title", request.topic),
            description=course_data.get("description", f"A comprehensive course on {request.topic}"),
            difficulty=request.difficulty,
            estimated_hours=estimated_hours,
            modules=modules,
            generated_at=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Course generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Course generation failed: {str(e)}"
        )


def _generate_fallback_course(request: CourseGenerationRequest) -> Dict[str, Any]:
    """Generate a fallback course structure when AI fails"""
    modules = []
    
    for mod_idx in range(request.num_modules):
        lessons = []
        for les_idx in range(request.lessons_per_module):
            lessons.append({
                "title": f"Lesson {les_idx + 1}: Introduction to {request.topic}",
                "description": f"Learn the fundamentals of {request.topic}",
                "content": f"""Welcome to this lesson on {request.topic}!

In this lesson, we'll explore the key concepts and fundamentals you need to know.

## Key Concepts

1. **Understanding the Basics**: Before diving deep, it's important to understand the foundational concepts.

2. **Practical Applications**: We'll look at how these concepts apply in real-world scenarios.

3. **Best Practices**: Learn the recommended approaches and techniques.

## Summary

This lesson covered the essential aspects of {request.topic}. In the next lesson, we'll build on these concepts with more advanced topics.

Take your time to review this material and make sure you understand each concept before moving forward.""",
                "duration_minutes": 15
            })
        
        modules.append({
            "title": f"Module {mod_idx + 1}: {request.topic} Fundamentals",
            "description": f"Master the core concepts of {request.topic}",
            "lessons": lessons
        })
    
    return {
        "title": f"Complete Guide to {request.topic}",
        "description": f"A comprehensive course covering all aspects of {request.topic} at the {request.difficulty} level.",
        "modules": modules
    }
