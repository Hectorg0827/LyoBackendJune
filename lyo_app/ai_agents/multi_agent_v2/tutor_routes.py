"""
Tutor API Routes - AI Tutoring Endpoints

MIT Architecture Engineering - Personalized Learning API

This module provides REST API endpoints for:
- Context-aware tutoring chat
- Progressive hints
- Concept explanations
- Learning feedback
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from lyo_app.ai_agents.multi_agent_v2.agents.tutor_agent import (
    get_tutor_agent,
    TutorAgent,
    TutorPersonality,
    ExplanationStyle,
    UserContext,
    TutorMessage,
    HintLevel,
    TutorResponse,
    HintResponse,
    TutorExplanation
)
from lyo_app.ai_agents.multi_agent_v2.agents.exercise_validator import (
    get_exercise_validator,
    ExerciseValidator,
    ExerciseContext,
    AnswerType,
    ValidationResult,
    CodeExecutionResult
)
from lyo_app.ai_agents.multi_agent_v2.agents.media_service import (
    get_media_service,
    MediaService,
    ImageGenerationRequest,
    DiagramGenerationRequest,
    ImageStyle,
    DiagramType,
    MediaResult
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/v2",
    tags=["AI Tutor & Exercises"]
)

# In-memory session storage (use Redis/DB in production)
_sessions: Dict[str, Dict[str, Any]] = {}


# ==================== REQUEST MODELS ====================

class TutorChatRequest(BaseModel):
    """Request for tutor chat"""
    message: str = Field(..., description="User's message")
    session_id: Optional[str] = Field(None, description="Existing session ID")
    course_id: Optional[str] = Field(None, description="Current course ID")
    lesson_id: Optional[str] = Field(None, description="Current lesson ID")
    topic: Optional[str] = Field(None, description="Current topic")
    personality: TutorPersonality = Field(
        default=TutorPersonality.ENCOURAGING,
        description="Tutor personality style"
    )


class HintRequest(BaseModel):
    """Request for a hint"""
    exercise_id: str
    exercise_description: str
    user_attempt: Optional[str] = None
    hint_level: HintLevel = HintLevel.SUBTLE
    course_id: Optional[str] = None
    lesson_id: Optional[str] = None


class ExplainRequest(BaseModel):
    """Request for concept explanation"""
    concept: str = Field(..., description="Concept to explain")
    course_id: Optional[str] = None
    lesson_id: Optional[str] = None
    style: Optional[ExplanationStyle] = None
    skill_level: str = "beginner"


class ValidateAnswerRequest(BaseModel):
    """Request to validate an answer"""
    exercise_id: str
    answer_type: AnswerType
    user_answer: str
    question: str
    expected_answer: Optional[str] = None
    expected_output: Optional[str] = None
    test_cases: Optional[List[Dict[str, Any]]] = None
    language: Optional[str] = None


class ValidateCodeRequest(BaseModel):
    """Request to validate code"""
    code: str
    language: str = "python"
    expected_output: Optional[str] = None
    test_cases: Optional[List[Dict[str, Any]]] = None
    timeout: int = 5


class GenerateImageRequest(BaseModel):
    """Request to generate an image"""
    concept: str
    style: ImageStyle = ImageStyle.EDUCATIONAL_DIAGRAM
    width: int = 512
    height: int = 512
    context: Optional[str] = None


class GenerateDiagramRequest(BaseModel):
    """Request to generate a diagram"""
    title: str
    diagram_type: DiagramType
    content: str
    theme: str = "default"


class CreateSessionRequest(BaseModel):
    """Request to create a tutor session"""
    user_id: str
    course_id: Optional[str] = None
    lesson_id: Optional[str] = None
    personality: TutorPersonality = TutorPersonality.ENCOURAGING


class FeedbackRequest(BaseModel):
    """Request to submit learning feedback"""
    session_id: str
    feedback_type: str  # "helpful", "confusing", "too_easy", "too_hard"
    message_id: Optional[str] = None
    comment: Optional[str] = None


# ==================== TUTOR ENDPOINTS ====================

@router.post(
    "/tutor/chat",
    response_model=TutorResponse,
    summary="Chat with AI Tutor",
    description="Send a message to the AI tutor and get a context-aware response."
)
async def tutor_chat(request: TutorChatRequest):
    """
    Chat with the AI tutor.
    
    The tutor adapts its responses based on:
    - Current course and lesson context
    - User's learning history
    - Selected personality style
    """
    try:
        tutor = get_tutor_agent()
        
        if not tutor.is_available:
            raise HTTPException(
                status_code=503,
                detail="AI tutor is temporarily unavailable"
            )
        
        # Get or create session
        session_id = request.session_id or str(uuid4())
        session = _sessions.get(session_id, {
            "messages": [],
            "user_context": None
        })
        
        # Build user context
        context = UserContext(
            user_id=session_id,
            course_id=request.course_id,
            lesson_id=request.lesson_id,
            current_topic=request.topic,
            completed_lessons=session.get("completed_lessons", []),
            quiz_scores=session.get("quiz_scores", {}),
            struggle_topics=session.get("struggle_topics", [])
        )
        
        # Get conversation history
        history = [
            TutorMessage(role=m["role"], content=m["content"])
            for m in session.get("messages", [])[-10:]
        ]
        
        # Get tutor response
        response = await tutor.chat(
            user_message=request.message,
            context=context,
            conversation_history=history,
            personality=request.personality
        )
        
        # Update session
        session["messages"].append({"role": "user", "content": request.message})
        session["messages"].append({"role": "assistant", "content": response.message})
        session["user_context"] = context.model_dump()
        _sessions[session_id] = session
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tutor chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/tutor/hint",
    response_model=HintResponse,
    summary="Get Progressive Hint",
    description="Get a hint for an exercise with progressive difficulty."
)
async def get_hint(request: HintRequest):
    """
    Get a progressive hint for an exercise.
    
    Hint levels:
    - subtle: Just a nudge in the right direction
    - moderate: More specific guidance
    - detailed: Near-complete solution explanation
    """
    try:
        tutor = get_tutor_agent()
        
        if not tutor.is_available:
            raise HTTPException(
                status_code=503,
                detail="AI tutor is temporarily unavailable"
            )
        
        context = UserContext(
            user_id="anonymous",
            course_id=request.course_id,
            lesson_id=request.lesson_id
        )
        
        response = await tutor.get_hint(
            exercise_description=request.exercise_description,
            user_attempt=request.user_attempt,
            hint_level=request.hint_level,
            context=context
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Hint generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/tutor/explain",
    response_model=TutorExplanation,
    summary="Explain Concept",
    description="Get a detailed explanation of a concept."
)
async def explain_concept(request: ExplainRequest):
    """
    Get a detailed explanation of a concept.
    
    Supports multiple explanation styles:
    - visual: Diagrams and visual descriptions
    - analogical: Real-world analogies
    - step_by_step: Numbered steps
    - example_based: Concrete examples
    - theoretical: Underlying principles
    """
    try:
        tutor = get_tutor_agent()
        
        if not tutor.is_available:
            raise HTTPException(
                status_code=503,
                detail="AI tutor is temporarily unavailable"
            )
        
        context = UserContext(
            user_id="anonymous",
            course_id=request.course_id,
            lesson_id=request.lesson_id,
            current_topic=request.concept,
            skill_level=request.skill_level,
            preferred_style=request.style or ExplanationStyle.EXAMPLE_BASED
        )
        
        response = await tutor.explain_concept(
            concept=request.concept,
            context=context,
            style=request.style
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explanation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/tutor/session",
    summary="Create Tutor Session",
    description="Create a new tutoring session."
)
async def create_session(request: CreateSessionRequest):
    """Create a new tutoring session for persistent conversation."""
    session_id = str(uuid4())
    
    _sessions[session_id] = {
        "session_id": session_id,
        "user_id": request.user_id,
        "course_id": request.course_id,
        "lesson_id": request.lesson_id,
        "personality": request.personality.value,
        "messages": [],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    return {
        "session_id": session_id,
        "message": "Session created successfully"
    }


@router.get(
    "/tutor/session/{session_id}",
    summary="Get Tutor Session",
    description="Get an existing tutoring session with history."
)
async def get_session(session_id: str):
    """Get a tutoring session by ID."""
    session = _sessions.get(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session


@router.post(
    "/tutor/feedback",
    summary="Submit Learning Feedback",
    description="Submit feedback on the tutoring experience."
)
async def submit_feedback(request: FeedbackRequest):
    """Submit feedback on a tutoring response."""
    session = _sessions.get(request.session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Store feedback (in production, save to database)
    if "feedback" not in session:
        session["feedback"] = []
    
    session["feedback"].append({
        "type": request.feedback_type,
        "message_id": request.message_id,
        "comment": request.comment,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {"status": "feedback_received", "message": "Thank you for your feedback!"}


# ==================== EXERCISE ENDPOINTS ====================

@router.post(
    "/exercises/validate",
    response_model=ValidationResult,
    summary="Validate Exercise Answer",
    description="Validate an answer for any exercise type."
)
async def validate_answer(request: ValidateAnswerRequest):
    """
    Validate an exercise answer.
    
    Supports:
    - Multiple choice
    - True/false
    - Short answer (AI-graded)
    - Code (executed)
    - Essay (AI-graded)
    - Fill-in-the-blank
    """
    try:
        validator = get_exercise_validator()
        
        context = ExerciseContext(
            exercise_id=request.exercise_id,
            exercise_type=request.answer_type,
            question=request.question,
            expected_answer=request.expected_answer,
            expected_output=request.expected_output,
            test_cases=request.test_cases,
            language=request.language
        )
        
        result = await validator.validate(
            user_answer=request.user_answer,
            context=context
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/exercises/validate/code",
    summary="Validate and Execute Code",
    description="Execute code and validate against expected output or test cases."
)
async def validate_code(request: ValidateCodeRequest):
    """
    Execute and validate code.
    
    Returns execution results including:
    - Output
    - Errors (if any)
    - Test case results
    - Execution time
    """
    try:
        validator = get_exercise_validator()
        
        # Execute the code
        execution_result = await validator.execute_code(
            code=request.code,
            language=request.language,
            timeout=request.timeout
        )
        
        response = {
            "execution": execution_result.model_dump(),
            "validation": None
        }
        
        # If expected output provided, validate
        if request.expected_output or request.test_cases:
            context = ExerciseContext(
                exercise_id="code_validation",
                exercise_type=AnswerType.CODE,
                question="Code execution",
                expected_output=request.expected_output,
                test_cases=request.test_cases,
                language=request.language
            )
            
            validation_result = await validator.validate(
                user_answer=request.code,
                context=context
            )
            
            response["validation"] = validation_result.model_dump()
        
        return response
        
    except Exception as e:
        logger.error(f"Code validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/exercises/hint",
    summary="Get Exercise Hint",
    description="Get a hint for an exercise."
)
async def get_exercise_hint(
    exercise_id: str = Body(...),
    question: str = Body(...),
    exercise_type: AnswerType = Body(AnswerType.SHORT_ANSWER),
    previous_attempts: List[str] = Body(default=[]),
    hint_level: int = Body(default=1, ge=1, le=3)
):
    """Get a hint for an exercise based on previous attempts."""
    try:
        validator = get_exercise_validator()
        
        context = ExerciseContext(
            exercise_id=exercise_id,
            exercise_type=exercise_type,
            question=question
        )
        
        hint = await validator.get_hint(
            context=context,
            previous_attempts=previous_attempts,
            hint_level=hint_level
        )
        
        return {
            "hint": hint,
            "level": hint_level,
            "remaining_hints": 3 - hint_level
        }
        
    except Exception as e:
        logger.error(f"Hint generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MEDIA ENDPOINTS ====================

@router.post(
    "/media/generate-image",
    response_model=MediaResult,
    summary="Generate Educational Image",
    description="Generate an AI image for a concept."
)
async def generate_image(request: GenerateImageRequest):
    """
    Generate an educational image for a concept.
    
    Styles available:
    - educational_diagram
    - concept_illustration
    - flowchart
    - infographic
    - photo_realistic
    - sketch
    """
    try:
        media_service = get_media_service()
        
        image_request = ImageGenerationRequest(
            concept=request.concept,
            style=request.style,
            width=request.width,
            height=request.height,
            additional_context=request.context
        )
        
        result = await media_service.generate_image(image_request)
        
        return result
        
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/media/generate-diagram",
    response_model=MediaResult,
    summary="Generate Diagram",
    description="Generate a Mermaid-based diagram."
)
async def generate_diagram(request: GenerateDiagramRequest):
    """
    Generate a diagram using Mermaid syntax.
    
    Diagram types:
    - flowchart
    - sequence
    - class
    - state
    - er (entity-relationship)
    - mindmap
    """
    try:
        media_service = get_media_service()
        
        diagram_request = DiagramGenerationRequest(
            title=request.title,
            diagram_type=request.diagram_type,
            content=request.content,
            theme=request.theme
        )
        
        result = await media_service.generate_diagram(diagram_request)
        
        return result
        
    except Exception as e:
        logger.error(f"Diagram generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/media/upload",
    response_model=MediaResult,
    summary="Upload Media File",
    description="Upload a file to cloud storage."
)
async def upload_media(
    file_data: bytes = Body(...),
    filename: str = Body(...),
    content_type: str = Body(default="application/octet-stream"),
    folder: str = Body(default="uploads")
):
    """Upload a file to cloud storage and get a signed URL."""
    try:
        media_service = get_media_service()
        
        result = await media_service.upload_file(
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            folder=folder
        )
        
        return result
        
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HEALTH CHECK ====================

@router.get(
    "/tutor/health",
    summary="Tutor Health Check",
    description="Check the health of tutor services."
)
async def tutor_health():
    """Check the health status of all tutor-related services."""
    tutor = get_tutor_agent()
    validator = get_exercise_validator()
    media = get_media_service()
    
    return {
        "status": "healthy",
        "services": {
            "tutor_agent": {
                "available": tutor.is_available,
                "model": tutor.model_name if tutor.is_available else None
            },
            "exercise_validator": {
                "available": validator.is_available
            },
            "media_service": {
                "storage_available": media.is_storage_available,
                "bucket": media.bucket_name
            }
        },
        "active_sessions": len(_sessions),
        "timestamp": datetime.utcnow().isoformat()
    }
