"""
A2UI API Routes
FastAPI routes for server-driven UI components
"""

import logging
from typing import Dict, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from lyo_app.core.database import get_db
from lyo_app.auth.jwt_auth import get_optional_current_user
from lyo_app.models.enhanced import User
from lyo_app.chat.a2ui_integration import chat_a2ui_service
from lyo_app.a2ui.a2ui_generator import a2ui
from lyo_app.a2ui.capability_handler import get_client_capabilities, ClientCapabilities


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/a2ui", tags=["A2UI"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================

class A2UIScreenRequest(BaseModel):
    """Request for A2UI screen"""
    screen_id: str = Field(..., description="Screen identifier")
    user_id: Optional[str] = Field(None, description="User ID for personalization")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")


class A2UIActionRequest(BaseModel):
    """Request for A2UI action handling"""
    action_id: str = Field(..., description="Action identifier")
    component_id: str = Field(..., description="Component that triggered action")
    action_type: str = Field(..., description="Type of action (tap, selection, etc.)")
    params: Optional[Dict[str, Any]] = Field(None, description="Action parameters")


class A2UIResponse(BaseModel):
    """A2UI component response"""
    component: Dict[str, Any] = Field(..., description="A2UI component tree")
    screen_id: str = Field(..., description="Screen identifier")
    session_id: str = Field(..., description="Session identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class A2UIActionResponse(BaseModel):
    """A2UI action response"""
    component: Optional[Dict[str, Any]] = Field(None, description="Updated component tree")
    navigation: Optional[Dict[str, Any]] = Field(None, description="Navigation action")
    message: Optional[str] = Field(None, description="Response message")
    success: bool = Field(True, description="Action success status")


# =============================================================================
# SCREEN ENDPOINTS
# =============================================================================

@router.post("/screen/{screen_id}", response_model=A2UIResponse)
async def get_screen(
    screen_id: str,
    request: A2UIScreenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
    capabilities: ClientCapabilities = Depends(get_client_capabilities)
):
    """
    Get A2UI screen component tree
    """
    try:
        session_id = str(uuid4())
        user_name = current_user.first_name if current_user else "User"

        # Generate screen component based on screen_id
        if screen_id == "dashboard":
            # Mock user stats for demo
            stats = {
                "courses": 12,
                "progress": "87%",
                "streak": "5 days"
            }

            # Mock courses data
            courses = [
                {
                    "id": "ios-dev",
                    "title": "iOS Development",
                    "description": "Build your first iOS app with SwiftUI",
                    "progress": 68.5,
                    "difficulty": "Intermediate",
                    "duration": "4 hours",
                    "image_url": "https://developer.apple.com/swift/images/swift-og.png"
                },
                {
                    "id": "ml-basics",
                    "title": "Machine Learning Basics",
                    "description": "Introduction to AI and ML concepts",
                    "progress": 25.0,
                    "difficulty": "Beginner",
                    "duration": "6 hours"
                }
            ]

            component = a2ui.learning_dashboard(user_name, stats, courses)

        elif screen_id == "course":
            course_id = request.context.get("course_id", "default")
            course_data = {
                "title": "iOS Development with SwiftUI",
                "progress": 68.5,
                "description": "Master iOS app development"
            }
            lesson_data = {
                "chapter": 3,
                "title": "State Management",
                "description": "Learn @State and @Binding",
                "video_thumbnail": "https://example.com/thumbnail.jpg",
                "next_lesson": {
                    "id": "next",
                    "title": "Navigation and Routing",
                    "description": "Learn NavigationView and routing",
                    "type": "video",
                    "duration": "15 min"
                }
            }

            component = a2ui.course_content(course_data, lesson_data)

        elif screen_id == "quiz":
            quiz_data = {
                "title": "SwiftUI Knowledge Check",
                "current_question": 2,
                "total_questions": 5,
                "question": {
                    "question": "What property wrapper is used for simple local state in SwiftUI?",
                    "options": ["@State", "@Binding", "@StateObject", "@ObservedObject"],
                    "correct_answer": 0,
                    "selected_answer": None
                }
            }

            component = a2ui.quiz_session(quiz_data, 2, 5)

        elif screen_id == "chat":
            messages = [
                {
                    "content": "Hello! I'm your AI tutor. How can I help you today?",
                    "is_user": False
                }
            ]
            suggestions = ["Explain machine learning", "Create a Python course", "Help with Swift"]

            component = a2ui.chat_interface(messages, suggestions)

        else:
            # Default welcome screen
            component = chat_a2ui_service.generate_welcome_ui(user_name)

        return A2UIResponse(
            component=component.to_dict(),
            screen_id=screen_id,
            session_id=session_id,
            metadata={
                "user_id": str(current_user.id) if current_user else None,
                "generated_at": str(uuid4()),
                "screen_type": screen_id
            }
        )

    except Exception as e:
        logger.error(f"Failed to generate screen {screen_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate screen: {str(e)}")


@router.get("/screen/{screen_id}", response_model=A2UIResponse)
async def get_screen_simple(
    screen_id: str,
    user_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Simplified GET endpoint for screen retrieval
    """
    request = A2UIScreenRequest(
        screen_id=screen_id,
        user_id=user_id,
        context={}
    )

    return await get_screen(screen_id, request, db, current_user)


# =============================================================================
# ACTION ENDPOINTS
# =============================================================================

@router.post("/action", response_model=A2UIActionResponse)
async def handle_action(
    request: A2UIActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Handle A2UI component actions
    """
    try:
        action_id = request.action_id

        # Handle specific actions
        if action_id == "quick_learn":
            # Navigate to explanation generation
            return A2UIActionResponse(
                navigation={"screen": "explanation", "context": {"mode": "quick"}},
                message="Let's learn something quickly!"
            )

        elif action_id == "create_course":
            # Navigate to course creation
            return A2UIActionResponse(
                navigation={"screen": "course_creation", "context": {"mode": "create"}},
                message="Let's create a course!"
            )

        elif action_id == "practice_quiz":
            # Navigate to quiz
            return A2UIActionResponse(
                navigation={"screen": "quiz", "context": {"mode": "practice"}},
                message="Time for a quiz!"
            )

        elif action_id.startswith("continue_course_"):
            course_id = action_id.replace("continue_course_", "")
            return A2UIActionResponse(
                navigation={"screen": "course", "context": {"course_id": course_id}},
                message=f"Continuing course {course_id}"
            )

        elif action_id == "quiz_answer":
            # Handle quiz answer
            selected_answer = request.params.get("selectedAnswer")
            correct_answer = 0  # @State is correct

            # Generate updated quiz with answer
            quiz_data = {
                "title": "SwiftUI Knowledge Check",
                "current_question": 2,
                "total_questions": 5,
                "question": {
                    "question": "What property wrapper is used for simple local state in SwiftUI?",
                    "options": ["@State", "@Binding", "@StateObject", "@ObservedObject"],
                    "correct_answer": correct_answer,
                    "selected_answer": selected_answer
                }
            }

            updated_component = a2ui.quiz_session(quiz_data, 2, 5)

            return A2UIActionResponse(
                component=updated_component.to_dict(),
                message="Correct!" if selected_answer == correct_answer else "Try again!"
            )

        elif action_id == "send_message":
            # Handle chat message
            message = request.params.get("message", "Hello")

            # Generate chat response
            messages = [
                {"content": "Hello! I'm your AI tutor.", "is_user": False},
                {"content": message, "is_user": True},
                {"content": "That's a great question! Let me help you with that.", "is_user": False}
            ]

            updated_chat = a2ui.chat_interface(messages, ["Tell me more", "Create a course"])

            return A2UIActionResponse(
                component=updated_chat.to_dict(),
                message="Message sent!"
            )

        else:
            # Generic action handling
            return A2UIActionResponse(
                message=f"Action {action_id} handled successfully"
            )

    except Exception as e:
        logger.error(f"Failed to handle action {request.action_id}: {e}")
        return A2UIActionResponse(
            success=False,
            message=f"Action failed: {str(e)}"
        )


# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@router.get("/components/test")
async def test_components():
    """
    Test endpoint to verify A2UI components generation
    """
    try:
        # Generate test components
        components = {
            "welcome": chat_a2ui_service.generate_welcome_ui("Test User").to_dict(),
            "course": a2ui.course_card(
                "Test Course",
                "A test course description",
                progress=50.0,
                difficulty="Intermediate"
            ).to_dict(),
            "quiz": a2ui.quiz(
                "What is 2 + 2?",
                ["3", "4", "5", "6"],
                1
            ).to_dict(),
            "text": a2ui.text("Hello World!", font="title", color="#007AFF").to_dict(),
            "button": a2ui.button("Click Me", "test_action").to_dict()
        }

        return {
            "status": "success",
            "components": components,
            "generator_ready": True
        }

    except Exception as e:
        logger.error(f"Component test failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "generator_ready": False
        }


@router.get("/health")
async def health_check():
    """
    A2UI service health check
    """
    return {
        "status": "healthy",
        "service": "a2ui",
        "generator": "ready",
        "version": "1.0.0"
    }