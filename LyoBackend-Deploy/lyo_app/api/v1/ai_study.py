"""
AI Study Mode API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from lyo_app.core.database import get_db
from lyo_app.ai_study.models import StudySession, StudyMessage, GeneratedQuiz

router = APIRouter()

@router.post("/sessions")
async def create_study_session(
    resource_id: str,
    resource_title: str = None,
    tutor_personality: str = "socratic",
    db: Session = Depends(get_db)
):
    """Create a new AI study session"""
    session = StudySession(
        resource_id=resource_id,
        resource_title=resource_title,
        tutor_personality=tutor_personality,
        user_id=1  # Placeholder - should get from auth
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return session.to_dict()

@router.get("/sessions/{session_id}")
async def get_study_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Get study session details"""
    session = db.query(StudySession).filter(StudySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Study session not found")
    
    return session.to_dict()

@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    content: str,
    role: str = "user",
    db: Session = Depends(get_db)
):
    """Send a message in the study session"""
    # Verify session exists
    session = db.query(StudySession).filter(StudySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Study session not found")
    
    # Create message
    message = StudyMessage(
        session_id=session_id,
        role=role,
        content=content
    )
    
    db.add(message)
    
    # Update session activity
    session.last_activity_at = datetime.utcnow()
    session.message_count += 1
    
    db.commit()
    db.refresh(message)
    
    return message.to_dict()

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get messages from a study session"""
    messages = db.query(StudyMessage)\
        .filter(StudyMessage.session_id == session_id)\
        .offset(skip)\
        .limit(limit)\
        .all()
    
    return [message.to_dict() for message in messages]

@router.post("/quizzes/generate")
async def generate_quiz(
    resource_id: str,
    quiz_type: str = "multiple_choice",
    question_count: int = 5,
    difficulty_level: str = "medium",
    db: Session = Depends(get_db)
):
    """Generate an AI quiz for a resource"""
    quiz = GeneratedQuiz(
        resource_id=resource_id,
        quiz_type=quiz_type,
        question_count=question_count,
        difficulty_level=difficulty_level,
        questions=[],  # Placeholder - should generate with AI
        user_id=1  # Placeholder - should get from auth
    )
    
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    
    return quiz.to_dict()

@router.get("/analytics/user/{user_id}")
async def get_user_analytics(
    user_id: int,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get user study analytics"""
    return {
        "user_id": user_id,
        "total_study_time": 0,
        "sessions_completed": 0,
        "average_engagement": 0.0,
        "topics_studied": []
    }
