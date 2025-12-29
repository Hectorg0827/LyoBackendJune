"""
Analytics routes for course generation usage tracking.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from lyo_app.ai_agents.multi_agent_v2.analytics import get_usage_tracker, CourseGenerationMetrics

logger = logging.getLogger(__name__)

# Create router
analytics_router = APIRouter(
    prefix="/api/v2/courses/analytics",
    tags=["Course Generation Analytics"]
)


@analytics_router.get("/user/{user_id}")
async def get_user_analytics(
    user_id: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get analytics for a specific user.
    
    Returns detailed usage statistics including:
    - Total courses generated
    - Cost breakdown
    - Quality scores
    - Daily trends
    """
    try:
        tracker = get_usage_tracker()
        analytics = await tracker.get_user_analytics(user_id, days)
        
        return analytics
        
    except Exception as e:
        logger.error(f"Failed to get user analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/system")
async def get_system_analytics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get system-wide analytics (admin only in production).
    
    Returns aggregate statistics across all users.
    """
    try:
        tracker = get_usage_tracker()
        analytics = await tracker.get_system_analytics(days)
        
        return analytics
        
    except Exception as e:
        logger.error(f"Failed to get system analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/course/{course_id}")
async def get_course_metrics(course_id: str):
    """
    Get detailed metrics for a specific course generation.
    
    Includes:
    - Token usage by agent
    - Cost breakdown
    - Generation time
    - Quality score
    """
    try:
        tracker = get_usage_tracker()
        metrics = await tracker.get_course_metrics(course_id)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="Course metrics not found")
        
        return metrics.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get course metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
