"""
AI Routes

Provides the /api/v1/ai endpoints for AI generation.
This is the main endpoint the iOS app calls for AI interactions.
"""

import logging
import time
from typing import Optional, Dict, Any, List
from enum import Enum

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from lyo_app.core.ai_resilience import ai_resilience_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["AI"])


# =============================================================================
# SCHEMAS
# =============================================================================

class TaskType(str, Enum):
    """Supported AI task types"""
    EDUCATIONAL_EXPLANATION = "EDUCATIONAL_EXPLANATION"
    COURSE_GENERATION = "COURSE_GENERATION"
    QUIZ_GENERATION = "QUIZ_GENERATION"
    NOTE_SUMMARIZATION = "NOTE_SUMMARIZATION"
    PRACTICE_QUESTIONS = "PRACTICE_QUESTIONS"
    GENERAL = "GENERAL"


class AIGenerateRequest(BaseModel):
    """Request schema for AI generation"""
    prompt: str = Field(..., min_length=1, max_length=10000, description="The prompt to process")
    task_type: Optional[str] = Field("GENERAL", description="Type of task")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="Creativity level")
    max_tokens: Optional[int] = Field(1000, ge=1, le=4000, description="Max response tokens")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class AIGenerateResponse(BaseModel):
    """Response schema for AI generation"""
    model_config = {"protected_namespaces": ()}  # Allow 'model_' fields
    
    response: str = Field(..., description="Generated response")
    task_type: str = Field(..., description="Task type used")
    tokens_used: Optional[int] = Field(None, description="Tokens consumed")
    model_used: str = Field(..., description="AI model used")
    latency_ms: int = Field(..., description="Response time in milliseconds")
    # iOS-compatible fields
    success: bool = Field(True, description="Whether generation succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")


# =============================================================================
# TASK-SPECIFIC PROMPTS
# =============================================================================

TASK_PROMPTS = {
    "EDUCATIONAL_EXPLANATION": """You are Lio, an expert educational AI tutor. 
Explain the following topic in a clear, engaging way suitable for learning.
Use examples and analogies where helpful. Keep the explanation concise but comprehensive.

Topic: {prompt}""",
    
    "COURSE_GENERATION": """You are Lio, an expert curriculum designer.
Create a structured course outline for the following topic.
Include: title, description, modules with lessons, and learning objectives.

Topic: {prompt}""",
    
    "QUIZ_GENERATION": """You are Lio, an expert assessment creator.
Generate practice questions for the following topic.
Include a mix of question types with clear answers and explanations.

Topic: {prompt}""",
    
    "NOTE_SUMMARIZATION": """You are Lio, an expert note-taker.
Summarize the following content into concise, well-organized notes.
Extract key points and important concepts.

Content: {prompt}""",
    
    "PRACTICE_QUESTIONS": """You are Lio, an expert tutor.
Generate practice problems for the following topic.
Include step-by-step solutions.

Topic: {prompt}""",
    
    "GENERAL": """You are Lio, a helpful AI learning assistant.
Respond to the following in a helpful, educational manner.

{prompt}"""
}


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/generate", response_model=AIGenerateResponse)
async def generate_ai_response(request: AIGenerateRequest):
    """
    Generate AI response for educational tasks.
    
    This is the main endpoint for iOS app AI interactions.
    Supports various task types for educational content generation.
    
    Note: This endpoint does NOT require authentication for public access.
    """
    start_time = time.time()
    
    try:
        # Ensure AI manager is initialized
        if not ai_resilience_manager.session:
            await ai_resilience_manager.initialize()
        
        # Get task-specific prompt template
        task_type = request.task_type or "GENERAL"
        prompt_template = TASK_PROMPTS.get(task_type, TASK_PROMPTS["GENERAL"])
        full_prompt = prompt_template.format(prompt=request.prompt)
        
        # Add context if provided
        if request.context:
            context_str = "\n\nAdditional context:\n" + "\n".join(
                f"- {k}: {v}" for k, v in request.context.items()
            )
            full_prompt += context_str
        
        # Build messages for chat completion
        messages = [
            {"role": "user", "content": full_prompt}
        ]
        
        # Generate response using the resilience manager
        result = await ai_resilience_manager.chat_completion(
            messages=messages,
            temperature=request.temperature or 0.7,
            max_tokens=request.max_tokens or 1000
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return AIGenerateResponse(
            response=result.get("response", result.get("text", "")),
            task_type=task_type,
            tokens_used=result.get("tokens_used"),
            model_used=result.get("model", "gemini-pro"),
            latency_ms=latency_ms,
            success=True,
            error=None
        )
        
    except Exception as e:
        logger.error(f"AI generation failed: {e}", exc_info=True)
        latency_ms = int((time.time() - start_time) * 1000)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI generation failed: {str(e)}"
        )


@router.post("/explain")
async def quick_explain(request: AIGenerateRequest):
    """Quick explanation endpoint - alias for generate with EDUCATIONAL_EXPLANATION type"""
    request.task_type = "EDUCATIONAL_EXPLANATION"
    return await generate_ai_response(request)


@router.post("/course")
async def generate_course(request: AIGenerateRequest):
    """Course generation endpoint - alias for generate with COURSE_GENERATION type"""
    request.task_type = "COURSE_GENERATION"
    return await generate_ai_response(request)


@router.post("/quiz")
async def generate_quiz(request: AIGenerateRequest):
    """Quiz generation endpoint - alias for generate with QUIZ_GENERATION type"""
    request.task_type = "QUIZ_GENERATION"
    return await generate_ai_response(request)


@router.get("/health")
async def ai_health():
    """Check AI service health"""
    try:
        ai_client = get_ai_client()
        return {
            "status": "healthy",
            "ai_available": ai_client is not None,
            "models": ["gemini-pro", "gpt-4o-mini"]
        }
    except Exception as e:
        return {
            "status": "degraded",
            "ai_available": False,
            "error": str(e)
        }
