"""
Streaming routes for real-time course generation progress.
"""

import logging
import json
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from lyo_app.ai_agents.multi_agent_v2 import (
    CourseGenerationPipeline,
    PipelineConfig,
    QualityTier
)

logger = logging.getLogger(__name__)

# Create router
streaming_router = APIRouter(
    prefix="/api/v2/courses",
    tags=["Course Generation v2 - Streaming"]
)


# Reuse the same request model
from lyo_app.ai_agents.multi_agent_v2.routes import CourseGenerationRequest


@streaming_router.post(
    "/generate/stream",
    summary="Start Course Generation with Streaming",
    description="Generate course with real-time Server-Sent Events progress updates."
)
async def generate_course_stream(request: CourseGenerationRequest):
    """
    Start course generation with real-time progress streaming via SSE.
    
    Returns a stream of events showing:
    - Agent progress
    - Lesson completions
    - Cost updates
    - Final results
    
    Use EventSource API on frontend to consume this stream.
    """
    try:
        # Parse quality tier
        try:
            quality_tier = QualityTier(request.quality_tier)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid quality tier: {request.quality_tier}"
            )
        
        # Build pipeline config
        config = PipelineConfig(
            quality_tier=quality_tier,
            enable_code_examples=request.enable_code_examples,
            enable_practice_exercises=request.enable_practice_exercises,
            enable_final_quiz=request.enable_final_quiz,
            enable_multimedia_suggestions=request.enable_multimedia_suggestions,
            qa_strictness=request.qa_strictness,
            max_budget_usd=request.max_budget_usd,
            target_language=request.target_language
        )
        
        # Budget check
        if request.max_budget_usd:
            estimated_cost = config.get_estimated_cost()
            if not config.validate_budget(estimated_cost):
                raise HTTPException(
                    status_code=400,
                    detail=f"Estimated cost (${estimated_cost:.4f}) exceeds budget (${request.max_budget_usd:.2f})"
                )
        
        logger.info(f"Starting streaming generation with {quality_tier.value} tier")
        
        # Create pipeline
        pipeline = CourseGenerationPipeline(config=config)
        
        # Stream wrapper for SSE format
        async def event_stream():
            try:
                async for event in pipeline.generate_course_with_streaming(
                    user_request=request.request,
                    user_context=request.user_context
                ):
                    # Event already formatted as SSE by to_sse()
                    yield event.to_sse()
                    
            except Exception as e:
                logger.error(f"Streaming generation failed: {e}")
                # Send error event
                error_event = {
                    "type": "error",
                    "progress": 0,
                    "message": f"Generation failed: {str(e)}"
                }
                yield f"data: {json.dumps(error_event)}\n\n"
        
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"  # Allow CORS for SSE
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start streaming generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
