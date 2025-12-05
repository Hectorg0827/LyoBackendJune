"""
Generative Curriculum Phase 2 API Routes
Advanced content generation and personalized learning paths
"""

import time
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user
from lyo_app.auth.models import User
from lyo_app.gen_curriculum.schemas import (
    ContentGenerationRequest,
    GeneratedContentResponse,
    LearningPathRequest,
    LearningPathResponse,
    ContentFeedbackRequest,
    PathAdaptationRequest,
    PathAdaptationResponse,
    ContentQualityMetrics,
    CurriculumGenerationRequest,
    CurriculumGenerationResponse
)
from lyo_app.gen_curriculum.service import gen_curriculum_engine
from lyo_app.personalization.service import personalization_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gen-curriculum", tags=["Generative Curriculum"])


@router.post("/content/generate", response_model=GeneratedContentResponse)
async def generate_content(
    request: ContentGenerationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate personalized learning content using AI
    
    This endpoint creates custom educational content tailored to:
    - Individual learner's current mastery level
    - Preferred learning style and emotional state  
    - Specific skill gaps and learning objectives
    - Optimal difficulty progression
    """
    start_time = time.time()
    
    try:
        logger.info(f"Generating {request.content_type} content for skill: {request.skill_id}")
        
        # Get personalization context if user provided
        personalization_context = {}
        if request.user_id:
            try:
                mastery_profile = await personalization_engine.get_mastery_profile(request.user_id)
                personalization_context = {
                    "current_mastery": mastery_profile.overall_mastery,
                    "learning_velocity": mastery_profile.learning_velocity,
                    "optimal_difficulty": mastery_profile.optimal_difficulty,
                    "current_affect": mastery_profile.current_affect,
                    "skill_masteries": mastery_profile.skill_masteries
                }
            except Exception as e:
                logger.warning(f"Could not get personalization context: {e}")
        
        # Generate content using the curriculum engine
        generated_content = await gen_curriculum_engine.generate_content(
            request=request,
            personalization_context=personalization_context,
            db=db
        )
        
        # Store quality metrics for continuous improvement
        background_tasks.add_task(
            _track_generation_metrics,
            content_id=generated_content.id,
            generation_time=time.time() - start_time,
            request_params=request.dict(),
            db=db
        )
        
        logger.info(f"Content generated successfully: ID {generated_content.id}")
        return generated_content
        
    except Exception as e:
        logger.error(f"Content generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Content generation failed: {str(e)}"
        )


@router.post("/learning-path/generate", response_model=LearningPathResponse)
async def generate_learning_path(
    request: LearningPathRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate personalized learning path with adaptive progression
    
    Creates a complete learning journey that:
    - Adapts to individual learning pace and style
    - Incorporates spaced repetition and forgetting curves
    - Includes checkpoints and branching logic
    - Provides fallback strategies for struggling learners
    """
    start_time = time.time()
    
    try:
        logger.info(f"Generating learning path for user {request.user_id}")
        
        # Get comprehensive learner profile
        mastery_profile = await personalization_engine.get_mastery_profile(request.user_id)
        
        # Generate personalized learning path
        learning_path = await gen_curriculum_engine.generate_learning_path(
            request=request,
            mastery_profile=mastery_profile,
            db=db
        )
        
        # Track path generation for analytics
        background_tasks.add_task(
            _track_path_generation,
            path_id=learning_path.id,
            generation_time=time.time() - start_time,
            user_id=request.user_id,
            db=db
        )
        
        logger.info(f"Learning path generated: ID {learning_path.id}")
        return learning_path
        
    except Exception as e:
        logger.error(f"Learning path generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Learning path generation failed: {str(e)}"
        )


@router.post("/curriculum/generate", response_model=CurriculumGenerationResponse)
async def generate_full_curriculum(
    request: CurriculumGenerationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate complete curriculum with modules, lessons, and assessments
    
    This creates a comprehensive educational program that includes:
    - Structured modules with clear learning progression
    - Multiple learning paths for different learning styles
    - Integrated assessments and feedback loops
    - Adaptive content based on performance data
    """
    start_time = time.time()
    
    try:
        logger.info(f"Generating full curriculum for: {request.learning_goal}")
        
        # Generate comprehensive curriculum
        curriculum = await gen_curriculum_engine.generate_adaptive_curriculum(
            user_id=request.user_id,
            learning_goal=request.learning_goal,
            subject_area=request.subject_area,
            constraints=request,
            db=db
        )
        
        # Async quality assurance and optimization
        background_tasks.add_task(
            _optimize_curriculum,
            curriculum_id=curriculum.id,
            user_id=request.user_id,
            db=db
        )
        
        generation_time = time.time() - start_time
        curriculum.generation_time_seconds = generation_time
        
        logger.info(f"Full curriculum generated: ID {curriculum.id} in {generation_time:.2f}s")
        return curriculum
        
    except Exception as e:
        logger.error(f"Curriculum generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Curriculum generation failed: {str(e)}"
        )


@router.get("/content/{content_id}", response_model=GeneratedContentResponse)
async def get_content(
    content_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get generated content by ID with usage tracking"""
    try:
        content = await gen_curriculum_engine.get_content_by_id(content_id, db)
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")
        
        # Track content access
        await gen_curriculum_engine.track_content_access(
            content_id=content_id,
            user_id=current_user.id,
            db=db
        )
        
        return content
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve content")


@router.get("/learning-path/{path_id}", response_model=LearningPathResponse)
async def get_learning_path(
    path_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get learning path with current progress"""
    try:
        path = await gen_curriculum_engine.get_learning_path_by_id(path_id, db)
        if not path:
            raise HTTPException(status_code=404, detail="Learning path not found")
        
        # Update last accessed timestamp
        await gen_curriculum_engine.update_path_access(path_id, current_user.id, db)
        
        return path
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving learning path {path_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve learning path")


@router.post("/content/{content_id}/feedback")
async def submit_content_feedback(
    content_id: int,
    feedback: ContentFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Submit learner feedback on generated content
    
    This feedback is used to:
    - Improve future content generation
    - Adapt difficulty levels
    - Identify common pain points
    - Optimize learning effectiveness
    """
    try:
        # Validate content exists
        content = await gen_curriculum_engine.get_content_by_id(content_id, db)
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")
        
        # Store feedback
        feedback_id = await gen_curriculum_engine.store_content_feedback(
            content_id=content_id,
            feedback=feedback,
            user_id=current_user.id,
            db=db
        )
        
        # Update personalization based on feedback
        if feedback.mastery_after is not None:
            await personalization_engine.update_mastery_from_feedback(
                user_id=current_user.id,
                skill_id=content.skill_id,
                mastery_change=feedback.mastery_after - (feedback.mastery_before or 0),
                db=db
            )
        
        return {"message": "Feedback submitted successfully", "feedback_id": feedback_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback for content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit feedback")


@router.post("/learning-path/{path_id}/adapt", response_model=PathAdaptationResponse)
async def adapt_learning_path(
    path_id: int,
    adaptation_request: PathAdaptationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Adapt learning path based on learner performance and feedback
    
    Adaptations can include:
    - Adjusting difficulty progression
    - Changing content types or pacing  
    - Adding scaffolding or review content
    - Modifying assessment frequency
    """
    try:
        # Validate learning path exists and belongs to user
        path = await gen_curriculum_engine.get_learning_path_by_id(path_id, db)
        if not path:
            raise HTTPException(status_code=404, detail="Learning path not found")
        
        if path.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Perform adaptation
        adaptation = await gen_curriculum_engine.adapt_learning_path(
            path_id=path_id,
            adaptation_request=adaptation_request,
            db=db
        )
        
        logger.info(f"Learning path {path_id} adapted: {adaptation.adaptation_type}")
        return adaptation
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adapting learning path {path_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to adapt learning path")


@router.get("/content/{content_id}/metrics", response_model=ContentQualityMetrics)
async def get_content_quality_metrics(
    content_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive quality metrics for generated content"""
    try:
        metrics = await gen_curriculum_engine.get_content_quality_metrics(content_id, db)
        if not metrics:
            raise HTTPException(status_code=404, detail="Content metrics not found")
        
        return metrics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving metrics for content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve content metrics")


@router.get("/user/{user_id}/learning-paths", response_model=List[LearningPathResponse])
async def get_user_learning_paths(
    user_id: int,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all learning paths for a user"""
    try:
        # Verify user can access these paths
        if user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        paths = await gen_curriculum_engine.get_user_learning_paths(
            user_id=user_id,
            active_only=active_only,
            db=db
        )
        
        return paths
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving learning paths for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve learning paths")


@router.post("/content/bulk-generate")
async def bulk_generate_content(
    requests: List[ContentGenerationRequest],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate multiple pieces of content efficiently
    
    Useful for pre-generating content for upcoming lessons
    or creating content variations for A/B testing
    """
    if len(requests) > 50:  # Limit bulk operations
        raise HTTPException(status_code=400, detail="Maximum 50 content pieces per bulk request")
    
    try:
        # Queue bulk generation as background task
        task_id = f"bulk_gen_{int(time.time())}"
        background_tasks.add_task(
            _bulk_generate_content,
            task_id=task_id,
            requests=requests,
            user_id=current_user.id,
            db=db
        )
        
        return {
            "message": "Bulk content generation started",
            "task_id": task_id,
            "content_count": len(requests),
            "estimated_completion_minutes": len(requests) * 2  # Rough estimate
        }
        
    except Exception as e:
        logger.error(f"Bulk content generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to start bulk generation")


# Background task helpers

async def _track_generation_metrics(
    content_id: int,
    generation_time: float,
    request_params: Dict[str, Any],
    db: AsyncSession
):
    """Track content generation metrics for analytics"""
    try:
        await gen_curriculum_engine.store_generation_metrics(
            content_id=content_id,
            generation_time=generation_time,
            request_params=request_params,
            db=db
        )
    except Exception as e:
        logger.error(f"Failed to track generation metrics: {e}")


async def _track_path_generation(
    path_id: int,
    generation_time: float,
    user_id: int,
    db: AsyncSession
):
    """Track learning path generation metrics"""
    try:
        await gen_curriculum_engine.store_path_generation_metrics(
            path_id=path_id,
            generation_time=generation_time,
            user_id=user_id,
            db=db
        )
    except Exception as e:
        logger.error(f"Failed to track path generation metrics: {e}")


async def _optimize_curriculum(
    curriculum_id: int,
    user_id: int,
    db: AsyncSession
):
    """Optimize curriculum after generation"""
    try:
        await gen_curriculum_engine.optimize_curriculum_async(
            curriculum_id=curriculum_id,
            user_id=user_id,
            db=db
        )
    except Exception as e:
        logger.error(f"Failed to optimize curriculum {curriculum_id}: {e}")


async def _bulk_generate_content(
    task_id: str,
    requests: List[ContentGenerationRequest],
    user_id: int,
    db: AsyncSession
):
    """Background task for bulk content generation"""
    try:
        results = await gen_curriculum_engine.bulk_generate_content(
            requests=requests,
            user_id=user_id,
            task_id=task_id,
            db=db
        )
        
        logger.info(f"Bulk generation completed: {task_id}, {len(results)} items")
        
    except Exception as e:
        logger.error(f"Bulk generation task {task_id} failed: {e}")
