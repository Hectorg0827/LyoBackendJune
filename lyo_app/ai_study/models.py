"""
AI Study Mode Database Models
Manages study sessions, conversation history, and quiz generation data
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, Integer, Float, Boolean, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from lyo_app.core.database import Base


class StudySessionStatus(str, enum.Enum):
    """Study session status enumeration"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class MessageRole(str, enum.Enum):
    """Chat message role enumeration"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


"""
AI Study Mode Database Models
Manages study sessions, conversation history, and quiz generation data
"""

import uuid
import enum
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Integer,
    Float,
    Boolean,
    JSON,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base


# ============================================================================
# ENUMS
# ==========================================================================

class StudySessionStatus(str, enum.Enum):
    """Study session status enumeration"""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class MessageRole(str, enum.Enum):
    """Chat message role enumeration"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class QuizType(str, enum.Enum):
    """Quiz type enumeration"""

    MULTIPLE_CHOICE = "multiple_choice"
    OPEN_ENDED = "open_ended"
    TRUE_FALSE = "true_false"
    FILL_IN_BLANK = "fill_in_blank"


# ============================================================================
# MODELS
# ==========================================================================

class StudySession(Base):
    """
    Represents an AI-powered study session for a learning resource
    """

    __tablename__ = "study_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resource_id = Column(String, nullable=False)  # ID of the learning material
    resource_title = Column(String(500), nullable=True)  # Cached resource title
    resource_type = Column(String(100), nullable=True)  # Type of resource (video, article, etc.)

    # Session metadata
    status = Column(SQLEnum(StudySessionStatus), default=StudySessionStatus.ACTIVE)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    total_duration_minutes = Column(Integer, default=0)

    # AI tutor configuration
    tutor_personality = Column(String(100), default="socratic")  # socratic, encouraging, challenging
    difficulty_level = Column(String(50), nullable=True)
    learning_objectives = Column(JSON, nullable=True)  # List of learning goals

    # Performance metrics
    message_count = Column(Integer, default=0)
    ai_response_count = Column(Integer, default=0)
    average_response_time = Column(Float, default=0.0)
    user_engagement_score = Column(Float, default=0.0)  # 0-1 scale

    # Relationships
    user = relationship("User", back_populates="study_sessions")
    messages = relationship("StudyMessage", back_populates="session", cascade="all, delete-orphan")
    quizzes = relationship("GeneratedQuiz", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resource_id": self.resource_id,
            "resource_title": self.resource_title,
            "resource_type": self.resource_type,
            "status": self.status.value if self.status else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_duration_minutes": self.total_duration_minutes,
            "tutor_personality": self.tutor_personality,
            "difficulty_level": self.difficulty_level,
            "learning_objectives": self.learning_objectives,
            "message_count": self.message_count,
            "ai_response_count": self.ai_response_count,
            "average_response_time": self.average_response_time,
            "user_engagement_score": self.user_engagement_score,
        }


class StudyMessage(Base):
    """
    Represents a single message in a study session conversation
    """

    __tablename__ = "study_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("study_sessions.id"), nullable=False)
    role = Column(SQLEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)

    # Message metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    token_count = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)  # Time taken to generate (for AI messages)

    # AI model information (for assistant messages)
    ai_model = Column(String(100), nullable=True)  # e.g., "gpt-4", "gpt-3.5-turbo"
    ai_temperature = Column(Float, nullable=True)
    ai_max_tokens = Column(Integer, nullable=True)

    # User interaction data (for user messages)
    user_typing_time_ms = Column(Integer, nullable=True)

    # Relationships
    session = relationship("StudySession", back_populates="messages")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role.value if self.role else None,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "token_count": self.token_count,
            "response_time_ms": self.response_time_ms,
            "ai_model": self.ai_model,
            "ai_temperature": self.ai_temperature,
            "ai_max_tokens": self.ai_max_tokens,
            "user_typing_time_ms": self.user_typing_time_ms,
        }


class GeneratedQuiz(Base):
    """
    Represents an AI-generated quiz for a study session or resource
    """

    __tablename__ = "generated_quizzes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("study_sessions.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resource_id = Column(String, nullable=False)

    # Quiz metadata
    quiz_type = Column(SQLEnum(QuizType), nullable=False)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    difficulty_level = Column(String(50), nullable=True)
    estimated_duration_minutes = Column(Integer, nullable=True)

    # Quiz content
    questions = Column(JSON, nullable=False)  # Array of question objects
    question_count = Column(Integer, nullable=False)

    # Generation metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    ai_model_used = Column(String(100), nullable=True)
    generation_prompt = Column(Text, nullable=True)  # The prompt used to generate
    generation_time_ms = Column(Integer, nullable=True)
    generation_token_count = Column(Integer, nullable=True)

    # Usage and performance
    times_taken = Column(Integer, default=0)
    average_score = Column(Float, nullable=True)  # 0-100 scale
    completion_rate = Column(Float, nullable=True)  # 0-1 scale

    # Quality metrics
    quality_rating = Column(Float, nullable=True)  # AI-assessed quality (0-1)
    user_feedback_rating = Column(Float, nullable=True)  # User feedback (1-5)
    is_validated = Column(Boolean, default=False)  # Whether questions have been reviewed

    # Relationships
    session = relationship("StudySession", back_populates="quizzes")
    user = relationship("User", back_populates="generated_quizzes")
    quiz_attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "resource_id": self.resource_id,
            "quiz_type": self.quiz_type.value if self.quiz_type else None,
            "title": self.title,
            "description": self.description,
            "difficulty_level": self.difficulty_level,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "questions": self.questions,
            "question_count": self.question_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "ai_model_used": self.ai_model_used,
            "generation_time_ms": self.generation_time_ms,
            "generation_token_count": self.generation_token_count,
            "times_taken": self.times_taken,
            "average_score": self.average_score,
            "completion_rate": self.completion_rate,
            "quality_rating": self.quality_rating,
            "user_feedback_rating": self.user_feedback_rating,
            "is_validated": self.is_validated,
        }


class QuizAttempt(Base):
    """
    Represents a user's attempt at a generated quiz
    """

    __tablename__ = "quiz_attempts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quiz_id = Column(String, ForeignKey("generated_quizzes.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Attempt metadata
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_minutes = Column(Float, nullable=True)

    # Results
    user_answers = Column(JSON, nullable=False)  # Array of user's answers
    score = Column(Float, nullable=True)  # 0-100 scale
    correct_answers = Column(Integer, default=0)
    total_questions = Column(Integer, nullable=False)

    # Performance analytics
    time_per_question = Column(JSON, nullable=True)  # Array of time spent per question
    confidence_levels = Column(JSON, nullable=True)  # User's confidence per question

    # Relationships
    quiz = relationship("GeneratedQuiz", back_populates="quiz_attempts")
    user = relationship("User", back_populates="quiz_attempts")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "quiz_id": self.quiz_id,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_minutes": self.duration_minutes,
            "user_answers": self.user_answers,
            "score": self.score,
            "correct_answers": self.correct_answers,
            "total_questions": self.total_questions,
            "time_per_question": self.time_per_question,
            "confidence_levels": self.confidence_levels,
        }


class StudySessionAnalytics(Base):
    """
    Aggregated analytics for study sessions (for performance insights)
    """

    __tablename__ = "study_session_analytics"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, default=datetime.utcnow)

    # Study metrics
    total_study_time_minutes = Column(Integer, default=0)
    sessions_started = Column(Integer, default=0)
    sessions_completed = Column(Integer, default=0)
    total_messages_sent = Column(Integer, default=0)
    total_ai_responses = Column(Integer, default=0)
    average_engagement_score = Column(Float, default=0.0)
    average_response_satisfaction = Column(Float, default=0.0)
    topics_studied = Column(JSON, nullable=True)  # List of topics
    learning_streak_days = Column(Integer, default=0)

    # AI usage
    total_tokens_used = Column(Integer, default=0)
    ai_cost_estimate = Column(Float, default=0.0)
    most_used_ai_model = Column(String(100), nullable=True)

    # Quiz statistics
    quizzes_generated = Column(Integer, default=0)
    quizzes_attempted = Column(Integer, default=0)
    average_quiz_score = Column(Float, default=0.0)

    # Relationships
    user = relationship("User", back_populates="study_analytics")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "total_study_time_minutes": self.total_study_time_minutes,
            "sessions_started": self.sessions_started,
            "sessions_completed": self.sessions_completed,
            "total_messages_sent": self.total_messages_sent,
            "total_ai_responses": self.total_ai_responses,
            "average_engagement_score": self.average_engagement_score,
            "average_response_satisfaction": self.average_response_satisfaction,
            "topics_studied": self.topics_studied,
            "learning_streak_days": self.learning_streak_days,
            "total_tokens_used": self.total_tokens_used,
            "ai_cost_estimate": self.ai_cost_estimate,
            "most_used_ai_model": self.most_used_ai_model,
            "quizzes_generated": self.quizzes_generated,
            "quizzes_attempted": self.quizzes_attempted,
            "average_quiz_score": self.average_quiz_score,
        }


# ============================================================================
# LIGHTWEIGHT AI MANAGER PLACEHOLDER
# ==========================================================================

class AIStudyManager:
    """Simple AI Study Manager for initial startup"""

    async def generate_study_content(self, topic: str, difficulty: str = "intermediate", user_id: Optional[int] = None):
        """Generate study content (placeholder)"""
        return {
            "topic": topic,
            "difficulty": difficulty,
            "content": f"Study content for {topic} at {difficulty} level",
            "tokens_used": 100,
        }


def get_ai_study_manager():
    """Get AI study manager instance"""
    return AIStudyManager()
    
    # Relationships
    session = relationship("StudySession", back_populates="messages")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role.value,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "token_count": self.token_count,
            "response_time_ms": self.response_time_ms,
            "ai_model": self.ai_model,
            "ai_temperature": self.ai_temperature,
            "ai_max_tokens": self.ai_max_tokens,
            "user_typing_time_ms": self.user_typing_time_ms,
            "user_sentiment": self.user_sentiment,
            "helpfulness_rating": self.helpfulness_rating,
            "clarity_score": self.clarity_score
        }


class GeneratedQuiz(Base):
    """
    Represents an AI-generated quiz for a study session or resource
    """
    __tablename__ = "generated_quizzes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("study_sessions.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resource_id = Column(String, nullable=False)
    
    # Quiz metadata
    quiz_type = Column(SQLEnum(QuizType), nullable=False)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    difficulty_level = Column(String(50), nullable=True)
    estimated_duration_minutes = Column(Integer, nullable=True)
    
    # Quiz content
    questions = Column(JSON, nullable=False)  # Array of question objects
    question_count = Column(Integer, nullable=False)
    
    # Generation metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    ai_model_used = Column(String(100), nullable=True)
    generation_prompt = Column(Text, nullable=True)  # The prompt used to generate
    generation_time_ms = Column(Integer, nullable=True)
    generation_token_count = Column(Integer, nullable=True)
    
    # Usage and performance
    times_taken = Column(Integer, default=0)
    average_score = Column(Float, nullable=True)  # 0-100 scale
    completion_rate = Column(Float, nullable=True)  # 0-1 scale
    
    # Quality metrics
    quality_rating = Column(Float, nullable=True)  # AI-assessed quality (0-1)
    user_feedback_rating = Column(Float, nullable=True)  # User feedback (1-5)
    is_validated = Column(Boolean, default=False)  # Whether questions have been reviewed
    
    # Relationships
    session = relationship("StudySession", back_populates="quizzes")
    user = relationship("User", back_populates="generated_quizzes")
    quiz_attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "resource_id": self.resource_id,
            "quiz_type": self.quiz_type.value,
            "title": self.title,
            "description": self.description,
            "difficulty_level": self.difficulty_level,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "questions": self.questions,
            "question_count": self.question_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "ai_model_used": self.ai_model_used,
            "generation_time_ms": self.generation_time_ms,
            "generation_token_count": self.generation_token_count,
            "times_taken": self.times_taken,
            "average_score": self.average_score,
            "completion_rate": self.completion_rate,
            "quality_rating": self.quality_rating,
            "user_feedback_rating": self.user_feedback_rating,
            "is_validated": self.is_validated
        }


class QuizAttempt(Base):
    """
    Represents a user's attempt at a generated quiz
    """
    __tablename__ = "quiz_attempts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quiz_id = Column(String, ForeignKey("generated_quizzes.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Attempt metadata
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_minutes = Column(Float, nullable=True)
    
    # Results
    user_answers = Column(JSON, nullable=False)  # Array of user's answers
    score = Column(Float, nullable=True)  # 0-100 scale
    correct_answers = Column(Integer, default=0)
    total_questions = Column(Integer, nullable=False)
    
    # Performance analytics
    time_per_question = Column(JSON, nullable=True)  # Array of time spent per question
    confidence_levels = Column(JSON, nullable=True)  # User's confidence per question
    help_requests = Column(Integer, default=0)  # Number of times user asked for help
    
    # Feedback
    difficulty_rating = Column(Integer, nullable=True)  # 1-5 scale
    enjoyment_rating = Column(Integer, nullable=True)  # 1-5 scale
    feedback_text = Column(Text, nullable=True)
    
    # Relationships
    quiz = relationship("GeneratedQuiz", back_populates="quiz_attempts")
    user = relationship("User", back_populates="quiz_attempts")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "quiz_id": self.quiz_id,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_minutes": self.duration_minutes,
            "user_answers": self.user_answers,
            "score": self.score,
            "correct_answers": self.correct_answers,
            "total_questions": self.total_questions,
            "time_per_question": self.time_per_question,
            "confidence_levels": self.confidence_levels,
            "help_requests": self.help_requests,
            "difficulty_rating": self.difficulty_rating,
            "enjoyment_rating": self.enjoyment_rating,
            "feedback_text": self.feedback_text
        }


class StudySessionAnalytics(Base):
    """
    Aggregated analytics for study sessions (for performance insights)
    """
    __tablename__ = "study_session_analytics"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, nullable=False)  # Date of the analytics snapshot
    
    # Daily aggregates
    total_study_time_minutes = Column(Integer, default=0)
    sessions_started = Column(Integer, default=0)
    sessions_completed = Column(Integer, default=0)
    total_messages_sent = Column(Integer, default=0)
    total_ai_responses = Column(Integer, default=0)
    
    # Performance metrics
    average_engagement_score = Column(Float, default=0.0)
    average_response_satisfaction = Column(Float, default=0.0)
    topics_studied = Column(JSON, nullable=True)  # Array of topics/resources
    learning_streak_days = Column(Integer, default=0)
    
    # AI usage statistics
    total_tokens_used = Column(Integer, default=0)
    ai_cost_estimate = Column(Float, default=0.0)
    most_used_ai_model = Column(String(100), nullable=True)
    
    # Quiz statistics
    quizzes_generated = Column(Integer, default=0)
    quizzes_attempted = Column(Integer, default=0)
    average_quiz_score = Column(Float, default=0.0)
    
    # Relationships
    user = relationship("User", back_populates="study_analytics")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "total_study_time_minutes": self.total_study_time_minutes,
            "sessions_started": self.sessions_started,
            "sessions_completed": self.sessions_completed,
            "total_messages_sent": self.total_messages_sent,
            "total_ai_responses": self.total_ai_responses,
            "average_engagement_score": self.average_engagement_score,
            "average_response_satisfaction": self.average_response_satisfaction,
            "topics_studied": self.topics_studied,
            "learning_streak_days": self.learning_streak_days,
            "total_tokens_used": self.total_tokens_used,
            "ai_cost_estimate": self.ai_cost_estimate,
            "most_used_ai_model": self.most_used_ai_model,
            "quizzes_generated": self.quizzes_generated,
            "quizzes_attempted": self.quizzes_attempted,
            "average_quiz_score": self.average_quiz_score
        }


class AIStudyManager:
    """Simple AI Study Manager for initial startup"""
    
    def __init__(self):
        pass
    
    async def generate_study_content(self, topic: str, difficulty: str = "intermediate", user_id: int = None):
        """Generate study content"""
        return {
            "topic": topic,
            "difficulty": difficulty,
            "content": f"Study content for {topic} at {difficulty} level",
            "tokens_used": 100
        }


def get_ai_study_manager():
    """Get AI study manager instance"""
    return AIStudyManager()
