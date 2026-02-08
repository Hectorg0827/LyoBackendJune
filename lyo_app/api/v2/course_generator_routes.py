"""
API v2 - Course Generator V2 Endpoints
Exposes the strict schema CourseGeneratorV2 agent.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Optional
from pydantic import BaseModel

from lyo_app.auth.dependencies import get_current_user
from lyo_app.auth.models import User
from lyo_app.ai_agents.course_generator_v2 import CourseGeneratorV2
from lyo_app.api.v2.course_schemas import LyoCourse

router = APIRouter(prefix="/generator", tags=["generator-v2"])

class GenerateCourseRequestV2(BaseModel):
    topic: str
    target_audience: str = "beginner"
    learning_objectives: List[str] = []

@router.post("/generate", response_model=LyoCourse)
async def generate_course_v2(
    request: GenerateCourseRequestV2,
    current_user: User = Depends(get_current_user)
):
    """
    Generate a strictly typed LyoCourse (V2) end-to-end.
    Does NOT return a job ID - returns the full object (for MVP/Test).
    In production, this should likely be async/job-based too if it takes > 30s.
    """
    agent = CourseGeneratorV2()
    
    try:
        course = await agent.generate_course(
            topic=request.topic,
            target_audience=request.target_audience,
            learning_objectives=request.learning_objectives
        )
        return course
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/spanish-101-demo", response_model=LyoCourse)
async def get_spanish_101_demo():
    """
    Hardcoded demo for 'Spanish 101' to verify client deserialization
    without waiting for AI.
    """
    from lyo_app.api.v2.course_schemas import (
        LyoCourse, LyoModule, LyoLesson, LyoArtifact, 
        ArtifactType, RenderTarget, ArtifactAIMetadata,
        ConceptExplainerPayload, QuizArtifactPayload,
        FlashcardsPayload, Flashcard, QuizQuestion, QuizOption
    )
    
    # 1. Concept
    concept_payload = ConceptExplainerPayload(
        markdown="# Hola! Welcome to Spanish.\n\nToday we learn greetings.",
        hook="Ready to order tacos like a pro?",
        key_takeaways=["Hola = Hello", "Adios = Goodbye"]
    )
    
    # 2. Flashcards
    flashcards_payload = FlashcardsPayload(
        topic="Basic Greetings",
        cards=[
            Flashcard(front="Hola", back="Hello"),
            Flashcard(front="Amigo", back="Friend")
        ]
    )
    
    # 3. Quiz
    quiz_payload = QuizArtifactPayload(
        questions=[
            QuizQuestion(
                id="q1", 
                text="How do you say 'Hello'?", 
                options=[
                    QuizOption(id="a", text="Hola"),
                    QuizOption(id="b", text="Queso")
                ], 
                correct_option_id="a"
            )
        ]
    )
    
    lesson1 = LyoLesson(
        lesson_id="les_spanish_1",
        title="Greetings",
        goal="Learn to say hello",
        duration_minutes=5,
        artifacts=[
            LyoArtifact(
                artifact_id="art_1",
                type=ArtifactType.CONCEPT_EXPLAINER,
                content=concept_payload.dict(),
                ai_metadata=ArtifactAIMetadata(confidence=1.0)
            ),
            LyoArtifact(
                artifact_id="art_2",
                type=ArtifactType.FLASHCARDS,
                content=flashcards_payload.dict(),
                ai_metadata=ArtifactAIMetadata(confidence=1.0)
            ),
            LyoArtifact(
                artifact_id="art_3",
                type=ArtifactType.QUIZ,
                content=quiz_payload.dict(),
                ai_metadata=ArtifactAIMetadata(confidence=1.0)
            )
        ]
    )
    
    return LyoCourse(
        course_id="lyo_spanish_101_demo",
        title="Spanish 101 (V2 Demo)",
        target_audience="beginner",
        learning_objectives=["Basic Greetings"],
        modules=[
            LyoModule(
                module_id="mod_1",
                title="The Basics",
                goal="Start talking",
                lessons=[lesson1]
            )
        ],
        generation_source="demo"
    )
