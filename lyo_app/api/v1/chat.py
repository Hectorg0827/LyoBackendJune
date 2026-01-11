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
    context: Optional[str] = Field(None, description="Context or system instruction override")
    include_chips: Optional[int] = Field(default=0, description="Whether to include suggestion chips")
    include_ctas: Optional[int] = Field(default=0, description="Whether to include CTAs")


class ChatResponse(BaseModel):
    """Chat response to iOS app"""
    model_config = {"protected_namespaces": ()}
    
    response: str = Field(..., description="AI generated response")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for tracking")
    conversation_history: Optional[List[ConversationMessage]] = Field(None, description="Updated conversation history")
    model_used: str = Field(default="Google Gemini 2.0 Flash", description="Model used for generation")
    success: bool = Field(default=True, description="Whether request succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    user_profile: Optional[Dict[str, Any]] = Field(None, description="User learning profile summary")
    
@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Primary chat endpoint for iOS app.
    Provides Lyo's conversational AI with personalization.
    """
    start_time = time.time()
    try:
        # Get personalization context
        personalization = PersonalizationEngine()
        
        # Build profile context for AI prompts (Layer 1 & 2 personalization)
        profile_context = await personalization.build_prompt_context(db, str(current_user.id))
        
        # Get profile summary for client response
        user_profile = await personalization.get_mastery_profile(db, str(current_user.id))
        user_profile_summary = user_profile.model_dump() if user_profile else {}
        
        # Build message history for Gemini
        messages = []
        if request.conversation_history:
            for msg in request.conversation_history:
                # Map 'assistant' to 'model' for Gemini if needed, but ai_resilience handles mapping
                messages.append({"role": msg.role, "content": msg.content})
        
        # Add current message
        messages.append({"role": "user", "content": request.message})

        # Add system message for Lyo personality with optional profile context
        # Incorporate client-provided context if available
        client_context = request.context if request.context else ""
        
        system_content = f"""You are Lyo, a friendly and engaging AI learning assistant.
Be conversational, helpful, and educational. Use emojis sparingly for warmth.
Format responses with markdown for readability. Keep responses concise but informative.

When a user asks to create a course, briefly confirm the topic and ask about their preferred level (beginner/intermediate/advanced) if you don't know it yet.

{profile_context}

{client_context}"""

        system_message = {
            "role": "system",
            "content": system_content
        }
        messages.insert(0, system_message)
        
        # Generate response using resilient manager
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
                "message": f"Request could not be processed: {str(e)}" if not settings.is_production() else "Request could not be processed. Please try again.",
                "category": "business_logic",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
        )
