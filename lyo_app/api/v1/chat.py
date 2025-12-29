"""
Chat API endpoint for iOS app
Handles conversational AI interactions with user profile personalization
"""

import logging
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.models import User
from lyo_app.personalization.service import PersonalizationEngine

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class ConversationMessage(BaseModel):
    """Single message in conversation history"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request from iOS app"""
    message: str = Field(..., min_length=1, max_length=5000)
    conversation_history: Optional[List[ConversationMessage]] = Field(default=[], description="Previous conversation messages")
    include_chips: Optional[int] = Field(default=0, description="Whether to include suggestion chips")
    include_ctas: Optional[int] = Field(default=0, description="Whether to include CTAs")


class ChatResponse(BaseModel):
    """Chat response to iOS app"""
    model_config = {"protected_namespaces": ()}
    
    response: str = Field(..., description="AI generated response")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for tracking")
    model_used: str = Field(default="Google Gemini 2.0 Flash", description="Model used for generation")
    success: bool = Field(default=True, description="Whether request succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    user_profile: Optional[Dict[str, Any]] = Field(None, description="User learning profile summary")


def _difficulty_to_level(optimal_difficulty: float) -> str:
    """Convert 0.0-1.0 difficulty to human-readable level"""
    if optimal_difficulty < 0.35:
        return "beginner"
    elif optimal_difficulty < 0.65:
        return "intermediate"
    else:
        return "advanced"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Main chat endpoint for iOS app conversational AI.
    
    Handles messages with conversation history and generates contextual responses.
    Now includes user profile personalization for better adaptive learning.
    """
    start_time = time.time()
    
    try:
        # Ensure AI manager is initialized
        if not ai_resilience_manager.session:
            await ai_resilience_manager.initialize()
        
        # Fetch user's learning profile for personalization
        personalization_engine = PersonalizationEngine()
        user_profile_summary = None
        profile_context = ""
        
        try:
            profile = await personalization_engine.get_mastery_profile(db, str(current_user.id))
            level = _difficulty_to_level(profile.optimal_difficulty)
            
            user_profile_summary = {
                "level": level,
                "optimal_difficulty": profile.optimal_difficulty,
                "strengths": profile.strengths[:3] if profile.strengths else [],
                "weaknesses": profile.weaknesses[:3] if profile.weaknesses else [],
                "learning_velocity": profile.learning_velocity
            }
            
            # Build profile context for AI
            if profile.strengths or profile.weaknesses:
                profile_context = f"""
User Learning Profile:
- Current Level: {level}
- Strengths: {', '.join(profile.strengths[:3]) if profile.strengths else 'Still learning'}
- Areas to improve: {', '.join(profile.weaknesses[:3]) if profile.weaknesses else 'Being explored'}
- Learning pace: {'fast' if profile.learning_velocity > 0.6 else 'steady' if profile.learning_velocity > 0.3 else 'careful'}

Adapt your responses to match their level. If they ask to create a course, suggest {level} level by default."""
            
        except Exception as profile_err:
            logger.warning(f"Could not load user profile: {profile_err}")
            # Continue without profile - will work as before
        
        # Build message history for context
        messages = []
        
        # Add conversation history
        if request.conversation_history:
            for msg in request.conversation_history[-10:]:  # Keep last 10 messages for context
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Add current message if not already in history
        if not messages or messages[-1]["content"] != request.message:
            messages.append({
                "role": "user",
                "content": request.message
            })
        
        # Add system message for Lyo personality with optional profile context
        system_message = {
            "role": "user",
            "content": f"""You are Lyo, a friendly and engaging AI learning assistant. 
Be conversational, helpful, and educational. Use emojis sparingly for warmth.
Format responses with markdown for readability. Keep responses concise but informative.

When a user asks to create a course, briefly confirm the topic and ask about their preferred level (beginner/intermediate/advanced) if you don't know it yet.

{profile_context}"""
        }
        messages.insert(0, system_message)
        
        # Generate response
        result = await ai_resilience_manager.chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )
        
        # Extract response text
        response_text = result.get("content") or result.get("response") or result.get("text") or ""
        
        if not response_text:
            raise ValueError("Empty response from AI")
        
        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Chat response generated in {latency_ms}ms for user {current_user.id}")
        
        return ChatResponse(
            response=response_text,
            model_used=result.get("model", "Google Gemini 2.0 Flash"),
            success=True,
            error=None,
            user_profile=user_profile_summary
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": True,
                "message": "Request could not be processed. Please try again.",
                "category": "business_logic",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
        )
