"""
Chat API endpoint for iOS app
Handles conversational AI interactions with user profile personalization
"""

import logging
import time
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.core.config import settings
from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.models import User
from lyo_app.personalization.service import PersonalizationEngine
from lyo_app.ai_agents.a2a.schemas import Artifact, ArtifactType, A2ACourseRequest
from lyo_app.ai_agents.a2a.orchestrator import A2AOrchestrator
from lyo_app.chat.a2ui_recursive import ChatResponseV2, UIComponent, migrate_legacy_content_types
from lyo_app.chat.assembler import ResponseAssembler
from lyo_app.chat.a2ui_integration import chat_a2ui_service
from lyo_app.a2ui.a2ui_generator import a2ui

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# AI CLASSROOM INTEGRATION HELPERS
# ============================================================

def detect_ai_classroom_intent(message: str) -> str:
    """Detect AI Classroom specific intents"""
    message_lower = message.lower()

    if any(phrase in message_lower for phrase in ["teach me", "learn about", "course on", "create course"]):
        return "course_creation"
    elif any(phrase in message_lower for phrase in ["continue lesson", "continue my lesson", "resume course", "my progress"]):
        return "continue_learning"
    elif any(phrase in message_lower for phrase in ["show courses", "available courses", "explore courses"]):
        return "course_discovery"
    elif any(phrase in message_lower for phrase in ["complete", "finished", "done with"]):
        return "course_completion"
    else:
        return "general_learning"

async def generate_ai_classroom_course(message: str, user) -> Optional[Dict[str, Any]]:
    """Generate course using AI Classroom system and return course data for A2UI"""
    try:
        # Extract topic from message
        topic = extract_learning_topic(message)
        if not topic:
            return None

        # Mock course generation for now (replace with actual AI Classroom integration)
        # This would normally call the AI Classroom course generation service
        course_data = {
            'id': f"course_{hash(topic) % 10000}",
            'title': f"Learn {topic.title()}",
            'description': f"A comprehensive course covering all aspects of {topic}",
            'subject': topic,
            'grade_band': 'Intermediate',
            'estimated_minutes': 90,
            'total_nodes': 12,
            'thumbnail_url': None
        }
        return course_data

    except Exception as e:
        logger.error(f"Failed to generate AI Classroom course: {e}")
        return None

def extract_learning_topic(message: str) -> Optional[str]:
    """Extract learning topic from user message"""
    import re

    patterns = [
        r"teach me (?:about )?(.+?)(?:\s+please|\s+pls|\s+today|\s+now|$)",
        r"learn (?:about )?(.+?)(?:\s+please|\s+pls|\s+today|\s+now|$)",
        r"course on (.+?)(?:\s+please|\s+pls|\s+today|\s+now|$)",
        r"study (.+?)(?:\s+please|\s+pls|\s+today|\s+now|$)"
    ]

    for pattern in patterns:
        match = re.search(pattern, message.lower())
        if match:
            topic = match.group(1).strip()
            # Clean up common trailing words
            topic = re.sub(r'\s+(please|pls|today|now)$', '', topic)
            return topic

    return None

async def get_user_learning_progress(user_id: str, course_id: str = None) -> Dict[str, Any]:
    """Get user's learning progress for A2UI display"""
    # Mock progress data (replace with actual AI Classroom progress tracking)
    return {
        'course_title': 'Python Fundamentals',
        'current_node': 7,
        'total_nodes': 12,
        'current_node_title': 'Functions and Modules',
        'next_node_title': 'Object-Oriented Programming',
        'motivation_message': "You're doing great! Only 5 more lessons to complete the course."
    }


# ============================================================
# INTENT DETECTION
# ============================================================

def detect_course_creation_intent(message: str) -> Optional[Dict[str, str]]:
    """
    Detects if the user is requesting course creation.
    Returns topic if detected, None otherwise.
    """
    message_lower = message.lower()
    
    # Patterns that indicate course creation
    course_patterns = [
        r"create (?:a )?course (?:on|about|for) (.+)",
        r"make (?:a )?course (?:on|about|for) (.+)",
        r"build (?:a )?course (?:on|about|for) (.+)",
        r"generate (?:a )?course (?:on|about|for) (.+)",
        r"design (?:a )?course (?:on|about|for) (.+)",
        r"(?:i want to learn|learn) (?:about )?(.+?)(?:,.*course|.*make.*course)",
        r"(?:teach me|course on|study) (.+)",
        r"can you (?:make|create|build) (?:a )?course.*?(?:on|about|for) (.+)",
    ]
    
    for pattern in course_patterns:
        match = re.search(pattern, message_lower)
        if match:
            topic = match.group(1).strip()
            return {"topic": topic, "intent": "course_creation"}
    
    return None


# ============================================================
# TRANSLATION LAYER (A2A -> A2UI)
# ============================================================

def translate_artifact_to_ui_component(artifact: Artifact) -> Optional[Dict[str, Any]]:
    """
    Translates internal A2A Artifacts into A2UI (Frontend) Components.
    This acts as the Envelope / Adapter layer.
    
    Returns a dictionary matching iOS A2UIContent structure:
    {
        "type": "course_roadmap" | "quiz" | "visual_gallery" | ...,
        "course_roadmap": {...},  // For courseRoadmap type
        "quiz": {...},           // For quiz type
        "title": "...",          // For topic_selection type
        "topics": [...]          // For topic_selection type
    }
    """
    # Helper to get generic content regardless of storage field
    # (data dict, text string, or url string)
    def get_content():
        return artifact.data or artifact.text or artifact.url

    # 1. VISUAL_PROMPT -> visual_gallery (not yet supported in iOS, skip for now)
    if artifact.type == ArtifactType.VISUAL_PROMPT:
        # iOS doesn't have visual_gallery yet, so skip
        return None
    
    # 2. ASSESSMENT -> quiz
    elif artifact.type == ArtifactType.ASSESSMENT:
        # Assessments are structured data
        quiz_data = artifact.data or {}
        questions = quiz_data.get("questions", []) if isinstance(quiz_data, dict) else []
        
        return {
            "type": "quiz",
            "quiz": {
                "title": artifact.name or "Quick Check",
                "questions": [
                    {
                        "question": q.get("question", ""),
                        "options": q.get("options", []),
                        "correct_answer": q.get("correct_answer", "")
                    }
                    for q in questions
                ]
            }
        }

    # 3. CURRICULUM_STRUCTURE -> course_roadmap
    elif artifact.type == ArtifactType.CURRICULUM_STRUCTURE:
        # Curriculum is structured data
        course_data = artifact.data or {}
        if not isinstance(course_data, dict):
            return None
            
        modules = course_data.get("modules", [])
        title = artifact.name or course_data.get("title", "Course Roadmap")
        topic = course_data.get("topic", "Learning Path")
        level = course_data.get("level", "beginner")
        
        # Convert modules to iOS format
        formatted_modules = []
        for mod in modules:
            lessons = mod.get("lessons", [])
            formatted_lessons = [
                {
                    "title": les.get("title", "Lesson"),
                    "duration": les.get("duration", "10 min")
                }
                for les in lessons
            ]
            
            formatted_modules.append({
                "title": mod.get("title", "Module"),
                "description": mod.get("description", ""),
                "lessons": formatted_lessons
            })
        
        return {
            "type": "course_roadmap",
            "course_roadmap": {
                "title": title,
                "topic": topic,
                "level": level,
                "modules": formatted_modules
            }
        }

    # 4. Fallback for other types
    return None


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
    ui_component: Optional[List[Dict[str, Any]]] = Field(None, description="List of A2UI Components for frontend rendering")
    
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
        
        # ============================================================
        # STEP 1: Detect Course Creation Intent
        # ============================================================
        course_intent = detect_course_creation_intent(request.message)
        
        if course_intent:
            logger.info(f"🎓 Course creation detected: {course_intent['topic']}")
            
            # Use A2A Orchestrator for course generation
            try:
                orchestrator = A2AOrchestrator()
                course_request = A2ACourseRequest(
                    topic=course_intent['topic'],
                    user_id=str(current_user.id),
                    level="beginner",  # Could be detected from message or profile
                    duration_minutes=30
                )
                
                # Generate course (non-streaming for now)
                a2a_response = await orchestrator.generate_course(course_request)
                
                # Extract artifacts
                artifacts = a2a_response.output_artifacts
                
                # Generate A2UI course UI using the proper service
                course_data = {
                    "title": f"Learn {course_intent['topic'].title()}",
                    "description": f"A comprehensive course on {course_intent['topic']}",
                    "lessons": []
                }

                # Extract lessons from artifacts
                for artifact in artifacts:
                    if artifact.type == ArtifactType.CURRICULUM_STRUCTURE and artifact.data:
                        modules = artifact.data.get("modules", [])
                        for module in modules:
                            for lesson in module.get("lessons", []):
                                course_data["lessons"].append({
                                    "title": lesson.get("title", "Lesson"),
                                    "type": "reading",
                                    "duration": f"{lesson.get('duration_minutes', 15)} min"
                                })

                # Generate proper A2UI component
                course_ui = chat_a2ui_service.generate_course_creation_ui(course_data)
                ui_component_json = course_ui.to_json() if course_ui else None

                # Build response text with A2UI formatting
                response_text = f"🎓 **Course Created: {course_intent['topic'].title()}**\n\nI've designed a comprehensive learning experience for you! The course includes {len(course_data['lessons'])} lessons covering all the essential concepts.\n\n✨ *Tap below to explore your personalized course*"

                latency_ms = int((time.time() - start_time) * 1000)
                logger.info(f"A2A Course generated in {latency_ms}ms with A2UI component")

                return ChatResponse(
                    response=response_text,
                    model_used="A2A Multi-Agent Pipeline + A2UI",
                    success=True,
                    error=None,
                    user_profile=user_profile_summary,
                    ui_component=[{"type": "a2ui", "component": ui_component_json}] if ui_component_json else None
                )
                
            except Exception as e:
                logger.error(f"A2A course generation failed: {e}", exc_info=True)
                # Fall through to regular chat completion
                pass
        
        # ============================================================
        # STEP 2: Regular Chat Completion (Non-course requests)
        # ============================================================
        
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

        # ============================================================
        # A2UI: Generate Enhanced Response with Better Formatting
        # ============================================================
        ui_component_json = None

        # Check if this is a learning-related response that could benefit from A2UI
        message_lower = request.message.lower()

        if any(word in message_lower for word in ["explain", "what is", "how does", "tell me about"]):
            # Generate explanation UI
            topic = request.message
            explanation_ui = chat_a2ui_service.generate_explanation_ui(response_text, topic)
            if explanation_ui:
                ui_component_json = explanation_ui.to_json()

        elif any(word in message_lower for word in ["help", "guide", "steps", "how to"]):
            # Generate welcome/help UI
            welcome_ui = chat_a2ui_service.generate_welcome_ui(current_user.name if hasattr(current_user, 'name') else "there")
            if welcome_ui:
                ui_component_json = welcome_ui.to_json()

        # Check if the AI result contains artifacts (populated by Orchestrator or Agents)
        artifacts_data = result.get("artifacts", [])
        if artifacts_data and isinstance(artifacts_data, list) and not ui_component_json:
            for art_data in artifacts_data:
                try:
                    # Ensure it's an Artifact model
                    if isinstance(art_data, dict):
                        artifact = Artifact(**art_data)
                    elif isinstance(art_data, Artifact):
                        artifact = art_data
                    else:
                        continue

                    # Attempt translation
                    translated = translate_artifact_to_ui_component(artifact)
                    if translated:
                        # Convert to A2UI format
                        if translated.get("type") == "course_roadmap":
                            course_data = translated["course_roadmap"]
                            course_ui = chat_a2ui_service.generate_course_creation_ui(course_data)
                            ui_component_json = course_ui.to_json() if course_ui else None
                        elif translated.get("type") == "quiz":
                            quiz_data = translated["quiz"]
                            quiz_ui = chat_a2ui_service.generate_quiz_ui({
                                "title": quiz_data.get("title", "Quiz"),
                                "current_question": 1,
                                "total_questions": len(quiz_data.get("questions", [])),
                                "question": quiz_data.get("questions", [{}])[0] if quiz_data.get("questions") else {}
                            })
                            ui_component_json = quiz_ui.to_json() if quiz_ui else None
                        break
                except Exception as e:
                    logger.warning(f"Failed to translate artifact: {e}")

        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Chat response generated in {latency_ms}ms with {'A2UI component' if ui_component_json else 'text only'}")

        return ChatResponse(
            response=response_text,
            model_used=result.get("model", "Google Gemini 2.0 Flash"),
            success=True,
            error=None,
            user_profile=user_profile_summary,
            ui_component=[{"type": "a2ui", "component": ui_component_json}] if ui_component_json else None
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


@router.post("/test", response_model=ChatResponse)
async def chat_test(request: ChatRequest):
    """
    Test chat endpoint for development and testing.
    Bypasses authentication and database dependencies.
    """
    start_time = time.time()
    try:
        # ============================================================
        # STEP 1: Detect Course Creation Intent
        # ============================================================
        course_intent = detect_course_creation_intent(request.message)

        if course_intent:
            logger.info(f"🎓 Course creation detected: {course_intent['topic']}")

            # Generate A2UI course UI using test data
            course_data = {
                "title": f"Learn {course_intent['topic'].title()}",
                "description": f"A comprehensive course on {course_intent['topic']}",
                "lessons": [
                    {"title": "Introduction", "type": "video", "duration": "15 min"},
                    {"title": "Core Concepts", "type": "interactive", "duration": "20 min"},
                    {"title": "Advanced Topics", "type": "reading", "duration": "12 min"},
                    {"title": "Practice & Review", "type": "quiz", "duration": "10 min"}
                ],
                "estimated_duration": "1 hour",
                "difficulty": "Beginner"
            }

            # Generate proper A2UI component
            course_ui = chat_a2ui_service.generate_course_creation_ui(course_data)
            ui_component_json = course_ui.to_json() if course_ui else None

            # Build response text
            response_text = f"🎓 **Course Created: {course_intent['topic'].title()}**\n\nI've designed a comprehensive learning experience for you! The course includes {len(course_data['lessons'])} lessons covering all the essential concepts.\n\n✨ *Tap below to explore your personalized course*"

            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Test course generated in {latency_ms}ms with A2UI component")

            return ChatResponse(
                response=response_text,
                model_used="Test A2UI Generator",
                success=True,
                error=None,
                user_profile={"test_user": True, "level": "beginner"},
                ui_component=[{"type": "a2ui", "component": ui_component_json}] if ui_component_json else None
            )

        # ============================================================
        # STEP 2: Other UI Types
        # ============================================================

        message_lower = request.message.lower()

        # Explanation requests
        if any(word in message_lower for word in ["explain", "what is", "how does", "tell me about"]):
            explanation_ui = chat_a2ui_service.generate_explanation_ui(
                f"Here's an explanation of {request.message}", request.message
            )
            ui_component_json = explanation_ui.to_json() if explanation_ui else None

            return ChatResponse(
                response=f"Let me explain {request.message} for you!",
                model_used="Test A2UI Generator",
                success=True,
                error=None,
                user_profile={"test_user": True, "level": "beginner"},
                ui_component=[{"type": "a2ui", "component": ui_component_json}] if ui_component_json else None
            )

        # Help requests
        elif any(word in message_lower for word in ["help", "guide", "steps", "how to", "getting started"]):
            welcome_ui = chat_a2ui_service.generate_welcome_ui("Test User")
            ui_component_json = welcome_ui.to_json() if welcome_ui else None

            return ChatResponse(
                response="Hi there! I'm Lyo, your AI learning assistant. Here are some things I can help you with:",
                model_used="Test A2UI Generator",
                success=True,
                error=None,
                user_profile={"test_user": True, "level": "beginner"},
                ui_component=[{"type": "a2ui", "component": ui_component_json}] if ui_component_json else None
            )

        # Quiz requests
        elif any(word in message_lower for word in ["quiz", "test", "questions"]):
            quiz_data = {
                "title": "Quick Knowledge Check",
                "current_question": 1,
                "total_questions": 3,
                "question": {
                    "question": "What is your current learning goal?",
                    "options": ["Learn programming", "Improve math skills", "Study science", "Practice languages"],
                    "correct_answer": 0
                }
            }
            quiz_ui = chat_a2ui_service.generate_quiz_ui(quiz_data)
            ui_component_json = quiz_ui.to_json() if quiz_ui else None

            return ChatResponse(
                response="Here's a quick quiz to help personalize your learning!",
                model_used="Test A2UI Generator",
                success=True,
                error=None,
                user_profile={"test_user": True, "level": "beginner"},
                ui_component=[{"type": "a2ui", "component": ui_component_json}] if ui_component_json else None
            )

        # Default response
        else:
            return ChatResponse(
                response=f"I understand you're asking about: {request.message}. Let me help you with that!",
                model_used="Test A2UI Generator",
                success=True,
                error=None,
                user_profile={"test_user": True, "level": "beginner"},
                ui_component=None
            )

    except Exception as e:
        logger.error(f"Test chat endpoint failed: {e}", exc_info=True)
        return ChatResponse(
            response="Sorry, I encountered an error. Please try again.",
            model_used="Test A2UI Generator",
            success=False,
            error=str(e),
            user_profile=None,
            ui_component=None
        )


@router.post("/v2", response_model=ChatResponseV2)
async def chat_v2(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enhanced chat endpoint with recursive A2UI support.
    Provides unlimited UI composition capabilities via server-driven UI.
    """
    start_time = time.time()
    assembler = ResponseAssembler()

    try:
        # Get personalization context
        personalization = PersonalizationEngine()
        profile_context = await personalization.build_prompt_context(db, str(current_user.id))
        user_profile = await personalization.get_mastery_profile(db, str(current_user.id))
        user_profile_summary = user_profile.model_dump() if user_profile else {}

        # ============================================================
        # STEP 1: Intent Detection & Specialized UI Generation
        # ============================================================

        message_lower = request.message.lower()
        ui_layout = None

        # Weather request example
        if "weather" in message_lower:
            weather_data = {
                "location": "San Francisco, CA",
                "temp": 72,
                "feels_like": 75,
                "condition": "Sunny",
                "humidity": 65,
                "wind_speed": 12
            }
            ui_layout = assembler.create_weather_ui(weather_data)
            response_text = "Here's the current weather information for you!"

        # AI Classroom Integration - Course & Learning Intents
        elif any(word in message_lower for word in ["course", "learning plan", "curriculum", "teach me", "learn", "lesson"]):
            # Detect specific AI Classroom intents
            classroom_intent = detect_ai_classroom_intent(request.message)

            if classroom_intent == "course_creation":
                # Generate course using AI Classroom and display with A2UI
                course_data = await generate_ai_classroom_course(request.message, current_user)
                if course_data:
                    ui_layout = assembler.create_course_preview_ui(course_data)
                    response_text = f"I've created a personalized course for you! This course covers {course_data.get('subject', 'the topic')} and should take about {course_data.get('estimated_minutes', 60)} minutes to complete."

            elif classroom_intent == "continue_learning":
                # Show learning progress with A2UI
                progress_data = await get_user_learning_progress(str(current_user.id))
                ui_layout = assembler.create_learning_progress_ui(progress_data)
                response_text = "Here's your current learning progress. Keep up the great work!"

            elif classroom_intent == "course_completion":
                # Show course completion celebration
                completion_data = {
                    'course_title': 'Python Fundamentals',
                    'total_nodes': 12,
                    'time_spent': 85,
                    'score': 92
                }
                ui_layout = assembler.create_course_completion_ui(completion_data)
                response_text = "🎉 Congratulations on completing your course!"

            else:
                # Fallback to existing A2A orchestrator for other course intents
                course_intent = detect_course_creation_intent(request.message)
                if course_intent:
                    # Try A2A orchestrator
                    try:
                        orchestrator = A2AOrchestrator()
                        course_request = A2ACourseRequest(
                            topic=course_intent['topic'],
                            user_id=str(current_user.id),
                            level="beginner",
                            duration_minutes=30
                        )

                        a2a_response = await orchestrator.generate_course(course_request)

                        # Convert A2A artifacts to legacy format for UI factory
                        course_data = {
                            "title": f"Course: {course_intent['topic']}",
                            "description": f"Comprehensive learning path for {course_intent['topic']}",
                            "total_modules": len(a2a_response.output_artifacts),
                            "estimated_time": 2,
                            "modules": []
                        }

                        for i, artifact in enumerate(a2a_response.output_artifacts):
                            if artifact.type == ArtifactType.CURRICULUM_STRUCTURE and artifact.data:
                                modules_data = artifact.data.get("modules", [])
                                for j, module in enumerate(modules_data):
                                    course_data["modules"].append({
                                        "id": f"{i}_{j}",
                                        "title": module.get("title", f"Module {j+1}"),
                                        "description": module.get("description", ""),
                                        "lessons": len(module.get("lessons", [])),
                                        "duration": 45,
                                        "status": "available"
                                    })

                        ui_layout = assembler.create_course_overview_ui(course_data)
                        response_text = f"I've created a comprehensive course on {course_intent['topic']}! 🚀"

                    except Exception as e:
                        logger.warning(f"A2A orchestrator failed, using fallback: {e}")
                        # Fallback course data
                        course_data = {
                            "title": f"Introduction to {course_intent['topic']}",
                            "description": f"Master the fundamentals of {course_intent['topic']}",
                            "total_modules": 3,
                            "estimated_time": 2,
                            "modules": [
                                {"id": "1", "title": "Getting Started", "description": "Basic concepts and setup", "lessons": 5, "duration": 30},
                                {"id": "2", "title": "Core Concepts", "description": "Deep dive into fundamentals", "lessons": 8, "duration": 45},
                                {"id": "3", "title": "Advanced Topics", "description": "Advanced techniques and best practices", "lessons": 6, "duration": 40}
                            ]
                        }
                        ui_layout = assembler.create_course_overview_ui(course_data)
                        response_text = f"I've created a learning plan for {course_intent['topic']}!"

        # Quiz/assessment request
        elif any(word in message_lower for word in ["quiz", "test", "assessment", "practice"]):
            quiz_data = {
                "score": 8,
                "total_questions": 10,
                "questions": [
                    {
                        "question": "What is the capital of France?",
                        "user_answer": "Paris",
                        "correct_answer": "Paris",
                        "user_correct": True,
                        "explanation": "Paris has been the capital of France since 987 AD."
                    },
                    {
                        "question": "What is 2 + 2?",
                        "user_answer": "5",
                        "correct_answer": "4",
                        "user_correct": False,
                        "explanation": "Basic arithmetic: 2 + 2 = 4"
                    }
                ]
            }
            ui_layout = assembler.create_quiz_results_ui(quiz_data)
            response_text = "Here are your quiz results! You did great! 🎉"

        # Study plan request
        elif any(word in message_lower for word in ["study plan", "learning path", "schedule"]):
            plan_data = {
                "description": "Personalized study plan based on your goals",
                "total_time": 180,
                "difficulty_level": "Mixed",
                "topics": [
                    {"id": "1", "title": "Fundamentals", "description": "Core concepts", "estimated_time": 60, "difficulty": "easy"},
                    {"id": "2", "title": "Advanced Concepts", "description": "Deep dive topics", "estimated_time": 90, "difficulty": "hard"},
                    {"id": "3", "title": "Practice Projects", "description": "Hands-on application", "estimated_time": 30, "difficulty": "medium"}
                ]
            }
            ui_layout = assembler.create_study_plan_ui(plan_data)
            response_text = "I've created a personalized study plan for you! 📚"

        # ============================================================
        # STEP 2: Default AI Chat Response (if no specialized UI)
        # ============================================================

        if not ui_layout:
            # Build messages for AI
            messages = []
            if request.conversation_history:
                for msg in request.conversation_history:
                    messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": request.message})

            # Add system context
            system_content = f"""You are Lyo, a friendly AI learning assistant.
Be conversational, helpful, and educational. Use emojis sparingly.
Format responses with markdown. Keep responses concise but informative.

{profile_context}"""

            system_message = {"role": "system", "content": system_content}
            messages.insert(0, system_message)

            # Generate AI response
            result = await ai_resilience_manager.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=1500
            )

            response_text = result.get("content") or result.get("response") or result.get("text") or ""
            if not response_text:
                raise ValueError("Empty response from AI")

        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Chat V2 response generated in {latency_ms}ms with {'recursive UI' if ui_layout else 'text only'}")

        return ChatResponseV2(
            response=response_text,
            ui_layout=ui_layout,
            session_id=f"session_{current_user.id}_{int(time.time())}",
            conversation_id=f"conv_{current_user.id}",
            response_mode="enhanced",
            content_types=None  # Legacy field for backward compatibility
        )

    except Exception as e:
        logger.error(f"Chat V2 endpoint failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": True,
                "message": f"Request could not be processed: {str(e)}" if not settings.is_production() else "Request could not be processed. Please try again.",
                "category": "business_logic",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
        )
