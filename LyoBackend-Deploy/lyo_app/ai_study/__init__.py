"""
AI Study Mode Package
Intelligent study session endpoints with Socratic tutoring and quiz generation
"""

from .routes import router as ai_study_router
from .models import StudySession, StudyMessage, GeneratedQuiz, QuizAttempt
from .schemas import (
    StudySessionRequest, StudySessionResponse, StudyConversationRequest,
    StudyConversationResponse, QuizGenerationRequest, QuizGenerationResponse,
    QuizAttemptRequest, QuizAttemptResponse
)
from .service import study_mode_service

__all__ = [
    "ai_study_router",
    "StudySession",
    "StudyMessage", 
    "GeneratedQuiz",
    "QuizAttempt",
    "StudySessionRequest",
    "StudySessionResponse",
    "StudyConversationRequest",
    "StudyConversationResponse",
    "QuizGenerationRequest",
    "QuizGenerationResponse",
    "QuizAttemptRequest",
    "QuizAttemptResponse",
    "study_mode_service"
]
