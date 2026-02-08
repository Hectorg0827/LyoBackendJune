"""
Workflow Routes - API endpoints for starting and monitoring workflows

These endpoints provide:
- Start course generation workflow
- Poll workflow status
- Get workflow result

The key difference from old routes:
- Returns immediately with workflow_id (doesn't block)
- iOS polls for status/completion
- Surviving server restart
"""

import logging
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from lyo_app.temporal.client import get_temporal_client, is_temporal_available
from lyo_app.temporal.workflows.course_generation import CourseGenerationWorkflowV1

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflows", tags=["Workflows"])


# ==============================================================================
# MARK: - Request/Response Models
# ==============================================================================

class StartCourseGenerationRequest(BaseModel):
    """Request to start a course generation workflow."""
    topic: str = Field(..., min_length=1, max_length=500)
    difficulty: str = Field("beginner", pattern="^(beginner|intermediate|advanced|expert)$")
    target_duration_hours: int = Field(10, ge=1, le=100)
    user_id: Optional[str] = None
    language: str = Field("en", max_length=10)
    learning_objectives: Optional[list] = None


class WorkflowStartResponse(BaseModel):
    """Response when workflow is started."""
    workflow_id: str
    status: str
    message: str



class WorkflowStatusResponse(BaseModel):
    """Response for workflow status query."""
    workflow_id: str
    status: str
    current_step: str
    total_steps: int
    completed_steps: int
    progress_percentage: float
    lessons_completed: list
    error_message: Optional[str] = None
    # Optimized Hydration Fields
    append_items: Optional[list] = None
    replace_items: Optional[list] = None
    proxy_justification: Optional[str] = None


class WorkflowResultResponse(BaseModel):
    """Response containing workflow result."""
    workflow_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ==============================================================================
# MARK: - Health Check
# ==============================================================================

@router.get("/health")
async def workflow_health():
    """Check if Temporal is available and connected."""
    temporal_available = is_temporal_available()
    
    if temporal_available:
        return {
            "status": "healthy",
            "temporal_connected": True,
            "message": "Workflow system is operational",
        }
    else:
        # Try to connect
        try:
            client = await get_temporal_client()
            return {
                "status": "healthy",
                "temporal_connected": True,
                "message": "Connected to Temporal",
            }
        except Exception as e:
            return {
                "status": "degraded",
                "temporal_connected": False,
                "message": f"Cannot connect to Temporal: {str(e)}",
                "fallback": "Using synchronous generation as fallback",
            }


# ==============================================================================
# MARK: - Start Workflow
# ==============================================================================

@router.post("/generate-course", response_model=WorkflowStartResponse)
async def start_course_generation(request: StartCourseGenerationRequest):
    """
    Start a new course generation workflow.
    
    Returns immediately with a workflow_id to poll for status.
    The actual generation happens in the background.
    """
    workflow_id = f"course-{uuid.uuid4()}"
    
    try:
        client = await get_temporal_client()
        
        # Start the workflow (returns immediately)
        await client.start_workflow(
            CourseGenerationWorkflowV1.run,
            {
                "topic": request.topic,
                "difficulty": request.difficulty,
                "target_duration_hours": request.target_duration_hours,
                "user_id": request.user_id,
                "language": request.language,
                "learning_objectives": request.learning_objectives or [],
            },
            id=workflow_id,
            task_queue="lyo-ai-queue",
        )
        
        logger.info(f"Started course generation workflow: {workflow_id} for topic: {request.topic}")
        
        return WorkflowStartResponse(
            workflow_id=workflow_id,
            status="STARTED",
            message=f"Course generation started for '{request.topic}'. Poll /status/{workflow_id} for progress.",
        )
        
    except Exception as e:
        logger.error(f"Failed to start workflow: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to start workflow: {str(e)}. Temporal may be unavailable.",
        )


# ==============================================================================
# MARK: - Poll Status
# ==============================================================================

@router.get("/{workflow_id}/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(workflow_id: str):
    """
    Get the current status of a workflow.
    
    iOS should poll this endpoint every 2 seconds during generation.
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)
        
        # Query the workflow for status
        status = await handle.query(CourseGenerationWorkflowV1.get_status)
        
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=status.get("status", "UNKNOWN"),
            current_step=status.get("current_step", ""),
            total_steps=status.get("total_steps", 0),
            completed_steps=status.get("completed_steps", 0),
            progress_percentage=status.get("progress_percentage", 0.0),
            lessons_completed=status.get("lessons_completed", []),
            error_message=status.get("error_message"),
            append_items=status.get("append_items", []),
            replace_items=status.get("replace_items", []),
            proxy_justification=status.get("proxy_justification"),
        )
        
    except Exception as e:
        logger.error(f"Failed to get workflow status: {e}")
        
        # Check if workflow doesn't exist vs other error
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=f"Workflow {workflow_id} not found",
            )
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workflow status: {str(e)}",
        )


# ==============================================================================
# MARK: - Get Result
# ==============================================================================

@router.get("/{workflow_id}/result", response_model=WorkflowResultResponse)
async def get_workflow_result(workflow_id: str):
    """
    Get the final result of a completed workflow.
    
    Call this when status is COMPLETED.
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)
        
        # Get the result (blocks until workflow completes or times out)
        result = await handle.result()
        
        return WorkflowResultResponse(
            workflow_id=workflow_id,
            status="COMPLETED",
            result=result,
        )
        
    except Exception as e:
        logger.error(f"Failed to get workflow result: {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=f"Workflow {workflow_id} not found",
            )
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workflow result: {str(e)}",
        )


# ==============================================================================
# MARK: - Cancel Workflow
# ==============================================================================

@router.post("/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str):
    """Cancel a running workflow."""
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)
        
        await handle.cancel()
        
        return {
            "workflow_id": workflow_id,
            "status": "CANCELLED",
            "message": "Workflow cancellation requested",
        }
        
    except Exception as e:
        logger.error(f"Failed to cancel workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel workflow: {str(e)}",
        )
