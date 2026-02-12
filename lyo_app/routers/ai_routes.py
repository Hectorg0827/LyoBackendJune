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
    "EDUCATIONAL_EXPLANATION": """You are Lyo, an expert educational AI tutor with an engaging, friendly personality. 
Explain the following topic in a clear, engaging way suitable for learning.
Use emojis sparingly for warmth 🎯. Use examples and analogies where helpful.
Format with markdown for readability. Keep the explanation comprehensive but digestible.

Topic: {prompt}""",
    
    "COURSE_GENERATION": """You are Lyo, an expert curriculum designer and tutor.
Create a FULL mini-course on the following topic. This should be comprehensive and educational.

📚 **FORMAT YOUR RESPONSE EXACTLY LIKE THIS:**

# 🎓 [Course Title]

## 📖 Overview
[2-3 sentences about what the student will learn]

## 🎯 Learning Objectives
- Objective 1
- Objective 2
- Objective 3

## 📝 Lesson 1: [First Key Concept]
[Detailed explanation with examples]

### 💡 Key Points:
- Point 1
- Point 2

## 📝 Lesson 2: [Second Key Concept]
[Detailed explanation with examples]

### 💡 Key Points:
- Point 1
- Point 2

## 📝 Lesson 3: [Third Key Concept]
[Detailed explanation with examples]

### 💡 Key Points:
- Point 1
- Point 2

## 🧪 Practice Exercise
[A practical exercise or problem to solve]

## ✅ Summary
[Recap of what was learned]

---
Now create a full course on: {prompt}""",
    
    "QUIZ_GENERATION": """You are Lyo, an expert assessment creator.
Generate 5 practice questions for the following topic.
Format each question clearly with options and the correct answer explained.

Topic: {prompt}""",
    
    "NOTE_SUMMARIZATION": """You are Lyo, an expert note-taker.
Summarize the following content into concise, well-organized notes.
Use bullet points and clear sections. Extract key points and important concepts.

Content: {prompt}""",
    
    "PRACTICE_QUESTIONS": """You are Lyo, an expert tutor.
Generate 3-5 practice problems for the following topic.
Include step-by-step solutions for each.

Topic: {prompt}""",
    
    "GENERAL": """You are Lyo, a helpful and engaging AI learning assistant.
Respond to the following in a helpful, educational manner.
Use markdown formatting and be conversational but informative.

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
        
        # AI resilience manager returns "content" key
        response_text = result.get("content") or result.get("response") or result.get("text") or ""
        
        return AIGenerateResponse(
            response=response_text,
            task_type=task_type,
            tokens_used=result.get("tokens_used"),
            model_used=result.get("model", "Google Gemini 2.0 Flash"),
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


# =============================================================================
# QUICK CHAT ENDPOINT (Non-Streaming Fast Path)
# =============================================================================

class AIChatRequest(BaseModel):
    """Request schema for quick chat — used by iOS fast path"""
    message: str = Field(..., min_length=1, max_length=5000, description="The user message")
    stream: bool = Field(False, description="Whether to stream (always false for this endpoint)")
    provider: Optional[str] = Field("gemini", description="AI provider preference")
    context: Optional[Dict[str, str]] = Field(None, description="Optional context (course_id, lesson_id)")


class AIChatResponse(BaseModel):
    """Response schema for quick chat"""
    model_config = {"protected_namespaces": ()}

    response: str = Field(..., description="AI response text")
    conversationHistory: Optional[List[Dict[str, str]]] = Field(None, description="Conversation turns")
    latency_ms: Optional[int] = Field(None, description="Response time in milliseconds")
    model_used: Optional[str] = Field(None, description="AI model used")


@router.post("/chat", response_model=AIChatResponse)
async def quick_chat(request: AIChatRequest):
    """
    Lightweight non-streaming chat endpoint for fast-path responses.
    
    Used by the iOS Two-Speed Engine for simple questions, greetings,
    and quick interactions that don't need the full Lyo2 streaming pipeline.
    Targets < 500ms response time.
    
    Note: This endpoint does NOT require authentication (public access).
    """
    start_time = time.time()
    
    try:
        # Ensure AI manager is initialized
        if not ai_resilience_manager.session:
            await ai_resilience_manager.initialize()
        
        # Build a conversational prompt
        system_prompt = (
            "You are Lyo, a friendly and knowledgeable AI learning companion. "
            "Keep your response concise (2-4 sentences) and helpful. "
            "Use a warm, conversational tone. "
            "If the user is asking about a topic, give a brief but informative answer."
        )
        
        # Add context if provided
        if request.context:
            course_id = request.context.get("course_id")
            lesson_id = request.context.get("lesson_id")
            if course_id:
                system_prompt += f"\nContext: Currently in course {course_id}"
            if lesson_id:
                system_prompt += f", lesson {lesson_id}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message}
        ]
        
        # Generate response using the resilience manager (Gemini → GPT fallback)
        result = await ai_resilience_manager.chat_completion(
            messages=messages,
            max_tokens=500,  # Keep fast-path responses short
            temperature=0.7
        )
        
        response_text = result.get("content") or result.get("response") or result.get("text") or ""
        latency_ms = int((time.time() - start_time) * 1000)
        
        return AIChatResponse(
            response=response_text,
            conversationHistory=[
                {"role": "user", "content": request.message},
                {"role": "assistant", "content": response_text}
            ],
            latency_ms=latency_ms,
            model_used="gemini-flash"
        )
        
    except Exception as e:
        logger.error(f"Quick chat failed: {e}", exc_info=True)
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Fallback response
        return AIChatResponse(
            response="I'm here to help! Could you tell me more about what you'd like to learn?",
            latency_ms=latency_ms,
            model_used="fallback"
        )


@router.get("/health")
async def ai_health():
    """Check AI service health"""
    try:
        # Check if AI resilience manager is initialized
        is_available = (
            ai_resilience_manager is not None and 
            hasattr(ai_resilience_manager, 'session') and 
            ai_resilience_manager.session is not None
        )
        return {
            "status": "healthy" if is_available else "initializing",
            "ai_available": is_available,
            "models": ["gemini-pro", "gemini-flash", "gpt-4o-mini"]
        }
    except Exception as e:
        return {
            "status": "degraded",
            "ai_available": False,
            "error": str(e)
        }
