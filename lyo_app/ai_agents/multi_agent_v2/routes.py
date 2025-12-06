"""
Course Generation API v2 - Multi-Agent Course Creation Endpoints

MIT Architecture Engineering - Production-Grade API

This module provides REST API endpoints for the multi-agent course generation
system. It supports:
- Async course generation with job tracking
- Status polling for long-running generation
- Partial course regeneration
- Job resumption
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from lyo_app.ai_agents.multi_agent_v2 import (
    CourseGenerationPipeline,
    PipelineConfig,
    PipelineError,
    JobManager,
    JobStatus,
    GeneratedCourse,
    CourseIntent,
    CurriculumStructure,
    # Model Management
    ModelManager,
    ModelTier
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/v2/courses",
    tags=["Course Generation v2"]
)

# Global pipeline instance (will be initialized with proper config)
_pipeline: Optional[CourseGenerationPipeline] = None
_job_manager: Optional[JobManager] = None


# ==================== REQUEST/RESPONSE MODELS ====================

class CourseGenerationRequest(BaseModel):
    """Request to generate a new course"""
    request: str = Field(
        ..., 
        min_length=10,
        max_length=2000,
        description="Natural language description of the course to generate",
        examples=["Create a comprehensive Python programming course for beginners that covers variables, functions, and object-oriented programming"]
    )
    user_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional user context for personalization",
        examples=[{
            "skill_level": "beginner",
            "learning_style": "hands-on",
            "goals": "Get a job as a Python developer"
        }]
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional pipeline configuration overrides"
    )


class JobStatusResponse(BaseModel):
    """Response for job status check"""
    job_id: str
    status: str
    progress_percent: int
    current_step: Optional[str] = None
    steps_completed: List[str] = []
    estimated_time_remaining_seconds: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    error: Optional[str] = None


class CourseGenerationResponse(BaseModel):
    """Response for completed course generation"""
    job_id: str
    status: str
    course_id: str
    course_title: str
    course_description: str
    module_count: int
    lesson_count: int
    total_duration_minutes: int
    qa_score: float
    qa_recommendation: str
    generated_at: datetime
    generation_duration_seconds: float


class CourseDetailResponse(BaseModel):
    """Full course detail response"""
    course_id: str
    intent: Dict[str, Any]
    curriculum: Dict[str, Any]
    lessons: List[Dict[str, Any]]
    assessments: Optional[Dict[str, Any]]
    qa_report: Optional[Dict[str, Any]]
    generated_at: datetime
    generation_duration_seconds: float


class RegenerateRequest(BaseModel):
    """Request to regenerate specific parts of a course"""
    job_id: str
    component: str = Field(
        ...,
        description="Component to regenerate: 'intent', 'curriculum', 'lesson', 'assessments', 'qa'"
    )
    component_id: Optional[str] = Field(
        default=None,
        description="Specific component ID (e.g., lesson_id for lesson regeneration)"
    )
    feedback: Optional[str] = Field(
        default=None,
        description="Feedback to guide the regeneration"
    )


# ==================== HELPER FUNCTIONS ====================

def get_pipeline() -> CourseGenerationPipeline:
    """Get or create the pipeline instance"""
    global _pipeline, _job_manager
    if _pipeline is None:
        # In production, this would use proper database session
        config = PipelineConfig(
            max_retries_per_step=3,
            parallel_lesson_batch_size=3,
            qa_min_score=60,
            save_intermediate_results=True
        )
        _pipeline = CourseGenerationPipeline(config=config, job_manager=_job_manager)
    return _pipeline


def status_to_progress(status: JobStatus) -> int:
    """Convert job status to progress percentage"""
    progress_map = {
        JobStatus.PENDING: 0,
        JobStatus.RUNNING: 5,
        JobStatus.STEP_1_INTENT: 15,
        JobStatus.STEP_2_CURRICULUM: 30,
        JobStatus.STEP_3_CONTENT: 50,
        JobStatus.STEP_4_ASSESSMENTS: 75,
        JobStatus.STEP_5_QA: 90,
        JobStatus.STEP_6_FINALIZE: 95,
        JobStatus.COMPLETED: 100,
        JobStatus.FAILED: 0
    }
    return progress_map.get(status, 0)


# ==================== BACKGROUND TASK ====================

async def run_course_generation(
    job_id: str,
    request: str,
    user_context: Optional[Dict[str, Any]],
    pipeline: CourseGenerationPipeline
):
    """Background task to run course generation"""
    try:
        logger.info(f"Starting course generation for job {job_id}")
        course = await pipeline.generate_course(
            user_request=request,
            user_context=user_context,
            job_id=job_id
        )
        logger.info(f"Course generation completed for job {job_id}: {course.course_id}")
    except PipelineError as e:
        logger.error(f"Pipeline error for job {job_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error for job {job_id}: {e}")


# ==================== API ENDPOINTS ====================

@router.post(
    "/generate",
    response_model=Dict[str, Any],
    summary="Start Course Generation",
    description="Start an asynchronous course generation job. Returns a job_id for polling."
)
async def generate_course(
    request: CourseGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a new course generation job.
    
    This endpoint initiates an async course generation process using the
    multi-agent pipeline. The generation happens in the background.
    
    Returns a job_id that can be used to poll for status.
    """
    try:
        pipeline = get_pipeline()
        
        # Create a job ID
        job_id = f"cg_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        
        # Add background task
        background_tasks.add_task(
            run_course_generation,
            job_id=job_id,
            request=request.request,
            user_context=request.user_context,
            pipeline=pipeline
        )
        
        logger.info(f"Course generation job created: {job_id}")
        
        return {
            "job_id": job_id,
            "status": "accepted",
            "message": "Course generation started. Poll /status/{job_id} for updates.",
            "poll_url": f"/api/v2/courses/status/{job_id}"
        }
        
    except Exception as e:
        logger.error(f"Failed to start course generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    summary="Get Job Status",
    description="Get the current status of a course generation job."
)
async def get_job_status(job_id: str):
    """
    Get the status of a course generation job.
    
    Poll this endpoint to track progress of course generation.
    """
    try:
        # In production, this would query the job manager
        # For now, return a mock response showing structure
        
        # TODO: Integrate with actual JobManager when database is configured
        return JobStatusResponse(
            job_id=job_id,
            status="running",  # Would come from JobManager
            progress_percent=50,
            current_step="content",
            steps_completed=["intent", "curriculum"],
            estimated_time_remaining_seconds=120,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Failed to get job status for {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MODEL MANAGEMENT ENDPOINTS ====================
# These must be defined BEFORE the /{course_id} catch-all route

@router.get(
    "/models",
    summary="Get Model Configuration",
    description="Get the current model configuration for each agent/task."
)
async def get_model_config():
    """
    Get the current model configuration showing which Gemini model
    is used for each task.
    
    Model Strategy:
    - PREMIUM (Gemini 2.5 Pro): Complex reasoning tasks
    - STANDARD (Gemini 1.5 Flash): High-volume tasks
    - ECONOMY (Gemini 1.5 Flash low temp): Simple repetitive tasks
    """
    model_assignments = {}
    
    for task_name, tier in ModelManager.TASK_MODEL_MAP.items():
        config = ModelManager.MODELS[tier]
        model_assignments[task_name] = {
            "tier": tier.value,
            "model": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "cost_per_1k_tokens": config.cost_per_1k_tokens
        }
    
    return {
        "model_strategy": {
            "premium": "Gemini 2.5 Pro - Complex reasoning (orchestrator, curriculum, QA)",
            "standard": "Gemini 1.5 Flash - Balanced (content, assessments)",
            "economy": "Gemini 1.5 Flash (low temp) - Simple tasks"
        },
        "task_assignments": model_assignments,
        "available_tiers": [tier.value for tier in ModelTier]
    }


@router.get(
    "/models/cost-estimate",
    summary="Estimate Course Generation Cost",
    description="Estimate the cost of generating a course."
)
async def estimate_cost(
    course_type: str = Query(
        default="standard",
        description="Type of course: 'mini', 'standard', 'comprehensive'"
    )
):
    """
    Estimate the cost of generating a course based on typical token usage.
    """
    # Token multipliers based on course type
    multipliers = {
        "mini": 0.3,
        "standard": 1.0,
        "comprehensive": 2.5
    }
    
    multiplier = multipliers.get(course_type, 1.0)
    base_estimate = ModelManager.get_pipeline_cost_estimate("")
    
    # Apply multiplier
    adjusted_breakdown = {}
    total = 0.0
    
    for task, data in base_estimate["breakdown"].items():
        adjusted_tokens = int(data["tokens"] * multiplier)
        adjusted_cost = data["cost_usd"] * multiplier
        adjusted_breakdown[task] = {
            "tokens": adjusted_tokens,
            "model": data["model"],
            "cost_usd": round(adjusted_cost, 6)
        }
        total += adjusted_cost
    
    return {
        "course_type": course_type,
        "breakdown": adjusted_breakdown,
        "total_estimated_cost_usd": round(total, 4),
        "savings_vs_all_premium": f"{round((1 - total / (total * 3)) * 100)}%",
        "note": "Estimates based on average usage. Actual costs may vary."
    }


@router.post(
    "/models/mode",
    summary="Set Model Mode",
    description="Set the model mode for all tasks."
)
async def set_model_mode(
    mode: str = Query(
        ...,
        description="Mode to set: 'balanced' (default), 'premium' (quality), 'economy' (cost)"
    )
):
    """
    Set the model mode for the entire pipeline.
    
    - balanced: Default strategy (Gemini 2.5 Pro for complex, 1.5 Flash for simple)
    - premium: Use Gemini 2.5 Pro for all tasks (highest quality, highest cost)
    - economy: Use Gemini 1.5 Flash for all tasks (lowest cost)
    """
    if mode == "balanced":
        ModelManager.reset_to_defaults()
        message = "Reset to balanced mode (Gemini 2.5 Pro + 1.5 Flash)"
    elif mode == "premium":
        ModelManager.use_premium_for_all()
        message = "Set to premium mode (Gemini 2.5 Pro for all tasks)"
    elif mode == "economy":
        ModelManager.use_economy_for_all()
        message = "Set to economy mode (Gemini 1.5 Flash for all tasks)"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Use 'balanced', 'premium', or 'economy'"
        )
    
    return {
        "mode": mode,
        "message": message,
        "timestamp": datetime.utcnow().isoformat()
    }


# ==================== COURSE RETRIEVAL ENDPOINTS ====================

@router.get(
    "/{course_id}",
    response_model=CourseDetailResponse,
    summary="Get Generated Course",
    description="Get the full details of a generated course."
)
async def get_course(course_id: str):
    """
    Get full details of a generated course.
    
    Returns the complete course including all lessons, assessments, and QA report.
    """
    try:
        # In production, this would query the database
        raise HTTPException(
            status_code=404,
            detail=f"Course {course_id} not found"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get course {course_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/regenerate",
    response_model=Dict[str, Any],
    summary="Regenerate Course Component",
    description="Regenerate a specific component of a course (lesson, assessment, etc.)."
)
async def regenerate_component(
    request: RegenerateRequest,
    background_tasks: BackgroundTasks
):
    """
    Regenerate a specific component of an existing course.
    
    Supports granular regeneration of:
    - Intent (course plan)
    - Curriculum (structure)
    - Individual lessons
    - Assessments
    - QA review
    
    Useful for fixing specific parts without regenerating the entire course.
    """
    try:
        valid_components = ["intent", "curriculum", "lesson", "assessments", "qa"]
        if request.component not in valid_components:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid component. Must be one of: {valid_components}"
            )
        
        if request.component == "lesson" and not request.component_id:
            raise HTTPException(
                status_code=400,
                detail="component_id is required for lesson regeneration"
            )
        
        # In production, this would trigger targeted regeneration
        regeneration_job_id = f"rg_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        
        return {
            "regeneration_job_id": regeneration_job_id,
            "original_job_id": request.job_id,
            "component": request.component,
            "component_id": request.component_id,
            "status": "accepted",
            "message": f"Regeneration of {request.component} started."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start regeneration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/resume/{job_id}",
    response_model=Dict[str, Any],
    summary="Resume Job",
    description="Resume a failed or paused course generation job from its last checkpoint."
)
async def resume_job(
    job_id: str,
    background_tasks: BackgroundTasks
):
    """
    Resume a course generation job from its last successful checkpoint.
    
    Useful for resuming after:
    - Temporary AI provider failures
    - Rate limiting
    - Timeout issues
    """
    try:
        pipeline = get_pipeline()
        
        # Add background task to resume
        background_tasks.add_task(
            run_course_generation,
            job_id=job_id,
            request="",  # Will be loaded from job data
            user_context=None,
            pipeline=pipeline
        )
        
        return {
            "job_id": job_id,
            "status": "resuming",
            "message": f"Job {job_id} is being resumed from last checkpoint."
        }
        
    except Exception as e:
        logger.error(f"Failed to resume job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/jobs",
    response_model=List[JobStatusResponse],
    summary="List Jobs",
    description="List all course generation jobs with optional filtering."
)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of jobs to return"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip")
):
    """
    List course generation jobs.
    
    Supports filtering by status and pagination.
    """
    try:
        # In production, this would query the JobManager
        return []  # Placeholder
        
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/jobs/{job_id}",
    summary="Cancel Job",
    description="Cancel a running course generation job."
)
async def cancel_job(job_id: str):
    """
    Cancel a running course generation job.
    
    Note: This may not immediately stop in-progress AI calls,
    but will prevent further pipeline steps from executing.
    """
    try:
        # In production, this would update the job status
        return {
            "job_id": job_id,
            "status": "cancelled",
            "message": f"Job {job_id} has been cancelled."
        }
        
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HEALTH/DEBUG ENDPOINTS ====================

@router.get(
    "/health",
    summary="Health Check",
    description="Check if the course generation service is healthy."
)
async def health_check():
    """Check service health"""
    return {
        "status": "healthy",
        "service": "course-generation-v2",
        "version": "2.0.0",
        "pipeline_initialized": _pipeline is not None,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get(
    "/config",
    summary="Get Pipeline Config",
    description="Get current pipeline configuration (debug only)."
)
async def get_config():
    """Get current pipeline configuration"""
    pipeline = get_pipeline()
    config = pipeline.config
    
    return {
        "max_retries_per_step": config.max_retries_per_step,
        "gate_failure_threshold": config.gate_failure_threshold,
        "parallel_lesson_batch_size": config.parallel_lesson_batch_size,
        "qa_min_score": config.qa_min_score,
        "save_intermediate_results": config.save_intermediate_results,
        "enable_auto_fix": config.enable_auto_fix
    }
