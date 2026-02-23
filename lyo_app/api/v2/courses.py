"""
API v2 - Course Generation Endpoints

Multi-agent async course generation with job tracking.
Uses A2A Orchestrator for high-quality course creation.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib
import json
import uuid
import asyncio

from lyo_app.auth.dependencies import get_current_user, get_current_user_or_guest
from lyo_app.auth.models import User
from lyo_app.ai_agents.a2a.orchestrator import A2AOrchestrator
from lyo_app.ai_agents.a2a.schemas import A2ACourseRequest, ArtifactType
from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.cache.course_cache import course_cache

router = APIRouter(prefix="/api/v2/courses", tags=["courses-v2"])

# In-memory job tracking (use Redis in production)
job_store: Dict[str, Dict[str, Any]] = {}


# MARK: - Request/Response Models

class CourseGenerationRequest(BaseModel):
    request: str = Field(..., description="Course topic or request")
    quality_tier: str = Field(default="standard", description="basic|standard|premium")
    enable_code_examples: bool = Field(default=False)
    enable_practice_exercises: bool = Field(default=True)
    enable_final_quiz: bool = Field(default=True)
    enable_multimedia_suggestions: bool = Field(default=False)
    qa_strictness: str = Field(default="medium", description="low|medium|high")
    target_language: str = Field(default="English")
    max_budget_usd: Optional[float] = None
    user_context: Optional[Dict[str, str]] = None


class A2AStreamingRequest(BaseModel):
    topic: str = Field(..., description="Course topic", alias="request")
    quality_tier: str = Field(default="standard")
    enable_visual: bool = Field(default=True, alias="enable_visuals")
    enable_voice: bool = Field(default=True, alias="enable_voice")
    enable_qa: bool = Field(default=True, alias="enable_quality_gates")
    user_context: Optional[Dict[str, Any]] = None

    class Config:
        populate_by_name = True


class CourseGenerationJobResponse(BaseModel):
    job_id: str
    status: str
    quality_tier: str
    estimated_cost_usd: float
    message: str
    poll_url: str


class CourseGenerationStatusResponse(BaseModel):
    job_id: str
    status: str  # processing, completed, failed
    progress_percent: int
    current_step: Optional[str] = None
    steps_completed: List[str]
    estimated_time_remaining_seconds: Optional[int] = None
    created_at: str
    updated_at: Optional[str] = None
    error: Optional[str] = None


class CourseOutlineModule(BaseModel):
    id: str
    title: str
    description: str


class CourseOutlineResponse(BaseModel):
    course_id: str
    title: str
    description: str
    modules: List[CourseOutlineModule]
    estimated_duration: int
    difficulty: str
    outline_hash: str
    status: str


class CourseLesson(BaseModel):
    id: str
    title: str
    content: Optional[str] = None
    duration_minutes: int
    order: int


class CourseModule(BaseModel):
    id: str
    title: str
    description: str
    lessons: List[CourseLesson]


class CourseModuleResponse(BaseModel):
    course_id: str
    module: CourseModule
    status: str  # pending | ready


class CourseResult(BaseModel):
    course_id: str
    title: str
    description: str
    modules: List[CourseModule]
    estimated_duration: int
    difficulty: str


# MARK: - Endpoints

@router.post("/generate", response_model=CourseGenerationJobResponse)
async def generate_course(
    request: CourseGenerationRequest,
    current_user = Depends(get_current_user_or_guest)
):
    """
    Submit a course generation job.
    Returns job ID for polling status.
    """
    # Generate job ID with timestamp and random suffix (matching the pattern from logs)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    job_id = f"cg_{timestamp}_{uuid.uuid4().hex[:8]}"

    # Estimate cost (simplified)
    cost_map = {"basic": 0.025, "fast": 0.043, "standard": 0.085, "premium": 0.170}
    estimated_cost = cost_map.get(request.quality_tier, 0.043)

    # ⚡️ Semantic Cache Check
    user_context = request.user_context or {}
    level = user_context.get("level", "beginner")
    
    cached_result = await course_cache.get_cached_course(
        topic=request.request,
        level=level,
        language=request.target_language
    )
    
    if cached_result:
        print(f"⚡️ Cache Hit for '{request.request}' - Skipping AI Generation")
        
        # Inject cached result as a valid job
        job_store[job_id] = {
            "job_id": job_id,
            "status": "completed",
            "progress_percent": 100,
            "current_step": "Retrieved from cache",
            "steps_completed": ["initialized", "cache_hit", "completed"],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "request": request.dict(),
            "user_id": current_user.id,
            "outline": None,
            "module_results": {},
            "result": cached_result, # The full course object
            "error": None
        }
        
        return CourseGenerationJobResponse(
            job_id=job_id,
            status="completed", # Return completed immediately
            quality_tier=request.quality_tier,
            estimated_cost_usd=0.0, # Free!
            message="Course retrieved from cache instantly.",
            poll_url=f"/api/v2/courses/status/{job_id}"
        )

    # Store job
    outline = _build_outline(job_id, request.request, request.user_context)
    job_store[job_id] = {
        "job_id": job_id,
        "status": "accepted",  # Change to match expected status
        "progress_percent": 0,
        "current_step": "Initializing course generation...",
        "steps_completed": [],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "request": request.dict(),
        "user_id": current_user.id,
        "outline": outline,
        "module_results": {},
        "result": None,
        "error": None
    }

    # Start background task
    asyncio.create_task(_generate_course_background(job_id, request, current_user))

    return CourseGenerationJobResponse(
        job_id=job_id,
        status="accepted",  # Match the expected status
        quality_tier=request.quality_tier,
        estimated_cost_usd=estimated_cost,
        message="Course generation started. Poll /status/{job_id} for updates.",
        poll_url=f"/api/v2/courses/status/{job_id}"
    )


@router.post("/outline", response_model=CourseOutlineResponse)
async def generate_course_outline(
    request: CourseGenerationRequest,
    current_user = Depends(get_current_user_or_guest)
):
    """
    Create a course outline immediately and continue full generation in background.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    job_id = f"cg_{timestamp}_{uuid.uuid4().hex[:8]}"

    outline = _build_outline(job_id, request.request, request.user_context)

    job_store[job_id] = {
        "job_id": job_id,
        "status": "outline_ready",
        "progress_percent": 15,
        "current_step": "Outline ready",
        "steps_completed": ["outline"],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "request": request.dict(),
        "user_id": current_user.id,
        "outline": outline,
        "module_results": {},
        "result": None,
        "error": None
    }

    asyncio.create_task(_generate_course_background(job_id, request, current_user))

    return CourseOutlineResponse(**outline, status="outline_ready")


@router.get("/{job_id}/outline", response_model=CourseOutlineResponse)
async def get_course_outline(
    job_id: str,
    current_user = Depends(get_current_user_or_guest)
):
    """
    Retrieve outline for a course generation job.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    outline = job.get("outline")
    if not outline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outline not found")

    return CourseOutlineResponse(**outline, status=job.get("status", "outline_ready"))


@router.get("/{job_id}/modules/{module_id}", response_model=CourseModuleResponse)
async def get_course_module(
    job_id: str,
    module_id: str,
    current_user = Depends(get_current_user_or_guest)
):
    """
    Retrieve a single module. Returns pending if full course is not ready.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    module_results = job.get("module_results", {})
    if module_id in module_results:
        return CourseModuleResponse(
            course_id=job.get("outline", {}).get("course_id", job_id),
            module=CourseModule(**module_results[module_id]),
            status="ready"
        )

    result = job.get("result")
    if result:
        for module in result.get("modules", []):
            if module.get("id") == module_id:
                return CourseModuleResponse(
                    course_id=result.get("course_id", job_id),
                    module=CourseModule(**module),
                    status="ready"
                )

    outline = job.get("outline")
    if outline:
        for mod in outline.get("modules", []):
            if mod.get("id") == module_id:
                placeholder = CourseModule(
                    id=mod.get("id"),
                    title=mod.get("title"),
                    description=mod.get("description"),
                    lessons=[
                        CourseLesson(
                            id=f"{mod.get('id')}_overview",
                            title="Module Overview",
                            content="This module is generating. Check back soon.",
                            duration_minutes=10
                        )
                    ]
                )
                return CourseModuleResponse(
                    course_id=outline.get("course_id", job_id),
                    module=placeholder,
                    status="pending"
                )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")


@router.post("/{job_id}/modules/{module_id}/generate", response_model=CourseModuleResponse)
async def generate_course_module(
    job_id: str,
    module_id: str,
    current_user = Depends(get_current_user_or_guest)
):
    """
    Generate a single module on demand using the outline as contract.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    module_results = job.get("module_results", {})
    if module_id in module_results:
        return CourseModuleResponse(
            course_id=job.get("outline", {}).get("course_id", job_id),
            module=CourseModule(**module_results[module_id]),
            status="ready"
        )

    outline = job.get("outline")
    if not outline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outline not found")

    module_outline = next((m for m in outline.get("modules", []) if m.get("id") == module_id), None)
    if not module_outline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")

    module = await _generate_module_content(
        topic=outline.get("title", ""),
        outline=outline,
        module_outline=module_outline
    )

    job.setdefault("module_results", {})[module_id] = module
    job["updated_at"] = datetime.utcnow().isoformat()

    return CourseModuleResponse(
        course_id=outline.get("course_id", job_id),
        module=CourseModule(**module),
        status="ready"
    )


@router.get("/status/{job_id}", response_model=CourseGenerationStatusResponse)
async def get_course_status(
    job_id: str,
    current_user = Depends(get_current_user_or_guest)
):
    """
    Poll for course generation status.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    # Security: ensure user owns this job
    if job["user_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return CourseGenerationStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress_percent=job["progress_percent"],
        current_step=job.get("current_step"),
        steps_completed=job.get("steps_completed", []),
        estimated_time_remaining_seconds=None,
        created_at=job["created_at"],
        updated_at=job.get("updated_at"),
        error=job.get("error")
    )


@router.post("/{job_id}/force-complete")
async def force_complete_job(
    job_id: str,
    current_user = Depends(get_current_user_or_guest)
):
    """
    Force a stalled job to complete with fallback content.
    Called by iOS client when stall is detected.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    if job["user_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # If already completed, just return success
    if job["status"] == "completed":
        return {"status": "already_completed", "job_id": job_id}
    
    # Generate emergency fallback content
    request_data = job.get("request", {})
    topic = request_data.get("request", "Course")
    user_context = request_data.get("user_context", {})
    
    fallback_course = _build_fallback_course(job_id, topic, user_context)
    
    # Mark as completed with fallback
    job["status"] = "completed"
    job["progress_percent"] = 100
    job["current_step"] = "Course ready (force-completed)"
    job["result"] = fallback_course
    job["steps_completed"].append("force_completed")
    job["updated_at"] = datetime.utcnow().isoformat()
    job["warning"] = "Force-completed with fallback content due to timeout"
    
    print(f"🆘 Force-completed job {job_id} with fallback content")
    
    return {"status": "force_completed", "job_id": job_id}


@router.get("/{job_id}/result", response_model=CourseResult)
async def get_course_result(
    job_id: str,
    current_user = Depends(get_current_user_or_guest)
):
    """
    Retrieve completed course.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    # Security
    if job["user_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    if job["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job not completed (status: {job['status']})"
        )
    
    result = job.get("result")
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Course result not found"
        )
    
    return CourseResult(**result)


@router.post("/stream-a2a")
async def stream_a2a_generation(
    request: A2AStreamingRequest,
    current_user = Depends(get_current_user_or_guest)
):
    """
    A2A Protocol Streaming Endpoint.
    Yields SSE events from the multi-agent pipeline.
    """
    orchestrator = A2AOrchestrator()
    
    # Map to A2A request internal format
    user_ctx = request.user_context or {}
    a2a_request = A2ACourseRequest(
        topic=request.topic,
        difficulty=user_ctx.get("difficulty", "intermediate"),
        teaching_style=user_ctx.get("teaching_style", "cinematic"),
        quality_tier=request.quality_tier,
        user_id=str(current_user.id),
        user_context=user_ctx
    )
    
    async def event_generator():
        try:
            async for event in orchestrator.generate_course_streaming(a2a_request):
                yield event.to_sse_data()
        except Exception as e:
            # Error event is already yielded by orchestrator in most cases, 
            # but this is a safety net for connection issues.
            import json
            error_data = json.dumps({
                "type": "error",
                "message": str(e),
                "pipeline_id": "error"
            })
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering for Nginx
        }
    )


# ============================================================================
# TIMEOUT CONFIGURATION - Prevent Infinite Hangs
# ============================================================================

TIMEOUT_ORCHESTRATOR = 120  # 2 min max for full orchestrator
TIMEOUT_MODULE_GENERATION = 45  # 45s per module
TIMEOUT_TOTAL_JOB = 300  # 5 min absolute max


# MARK: - Background Task

async def _generate_course_background(
    job_id: str,
    request: CourseGenerationRequest,
    user: User
):
    """
    Background task: generate course using A2A Orchestrator.
    
    BULLETPROOF GUARANTEES:
    1. NEVER hangs - hard timeouts on every phase
    2. ALWAYS returns content - fallback chain ensures delivery
    3. Progress updates - user always knows what's happening
    """
    job_start_time = datetime.utcnow()
    
    try:
        job = job_store[job_id]

        # Step 1: Initialize
        job["status"] = "processing"
        job["progress_percent"] = 10
        job["current_step"] = "Analyzing request..."
        job["steps_completed"].append("initialized")
        job["updated_at"] = datetime.utcnow().isoformat()

        # Add small delay for realism
        await asyncio.sleep(0.5)

        # Step 2: Call A2A Orchestrator (with HARD TIMEOUT)
        course_result = None
        try:
            orchestrator = A2AOrchestrator()

            job["progress_percent"] = 30
            job["current_step"] = "Coordinating AI agents..."
            job["steps_completed"].append("orchestrator_started")
            job["updated_at"] = datetime.utcnow().isoformat()

            # Get user context
            user_context = request.user_context or {}
            level = user_context.get("level", "beginner")
            outcomes = user_context.get("outcomes", "").split(",") if user_context.get("outcomes") else []

            a2a_request = A2ACourseRequest(
                topic=request.request,
                level=level,
                learning_outcomes=[outcome.strip() for outcome in outcomes if outcome.strip()],
                teaching_style=user_context.get("style", "interactive")
            )

            # ⏱️ HARD TIMEOUT - Never wait more than 2 minutes
            a2a_response = await asyncio.wait_for(
                orchestrator.generate_course(a2a_request),
                timeout=TIMEOUT_ORCHESTRATOR
            )

            job["progress_percent"] = 80
            job["current_step"] = "Building course structure..."
            job["steps_completed"].append("agents_completed")
            job["updated_at"] = datetime.utcnow().isoformat()

            # Step 3: Convert artifacts to course structure
            course_result = _build_course_from_artifacts(
                job_id,
                request.request,
                a2a_response.output_artifacts
            )
            print(f"✅ A2A Orchestrator succeeded for job {job_id}")

        except asyncio.TimeoutError:
            print(f"⏱️ A2A Orchestrator TIMEOUT for job {job_id} - using fallback")
            job["steps_completed"].append("orchestrator_timeout")
            
        except Exception as orchestrator_error:
            print(f"⚠️ A2A Orchestrator failed for job {job_id}: {orchestrator_error}")
            job["steps_completed"].append("orchestrator_error")

        # Step 3b: Fallback if orchestrator failed
        if course_result is None:
            job["progress_percent"] = 50
            job["current_step"] = "Generating modules from outline..."
            job["updated_at"] = datetime.utcnow().isoformat()

            outline = job.get("outline") or _build_outline(job_id, request.request, request.user_context)
            job["outline"] = outline

            try:
                course_result = await asyncio.wait_for(
                    _build_course_from_outline_modules_resilient(
                        job_id=job_id,
                        topic=request.request,
                        outline=outline,
                        job=job,
                        user_context=request.user_context
                    ),
                    timeout=TIMEOUT_ORCHESTRATOR
                )
            except asyncio.TimeoutError:
                print(f"⏱️ Module generation TIMEOUT for job {job_id} - using emergency fallback")
                course_result = _build_fallback_course(job_id, request.request, request.user_context)
            except Exception as e:
                print(f"❌ Module generation failed for job {job_id}: {e}")
                course_result = _build_fallback_course(job_id, request.request, request.user_context)

        # Step 4: Complete (ALWAYS reached)
        job["status"] = "completed"
        job["progress_percent"] = 100
        job["current_step"] = "Course ready!"
        job["steps_completed"].append("completed")
        job["updated_at"] = datetime.utcnow().isoformat()
        job["result"] = course_result

        elapsed = (datetime.utcnow() - job_start_time).total_seconds()
        print(f"✅ Course generation completed for job {job_id} in {elapsed:.1f}s")
        
        # 💾 Cache the successful result
        user_context = request.user_context or {}
        await course_cache.cache_course(
            topic=request.request,
            level=user_context.get("level", "beginner"),
            course_data=course_result,
            language=request.target_language
        )

    except Exception as e:
        print(f"❌ Critical error in job {job_id}: {e}")
        job = job_store.get(job_id)
        if job:
            # EMERGENCY FALLBACK: Even on critical error, return something usable
            emergency_course = _build_fallback_course(job_id, request.request, request.user_context)
            job["status"] = "completed"  # Mark as completed, not failed
            job["progress_percent"] = 100
            job["current_step"] = "Course ready (simplified)"
            job["result"] = emergency_course
            job["warning"] = f"Generated with fallback due to: {str(e)}"
            job["updated_at"] = datetime.utcnow().isoformat()
            print(f"🆘 Emergency fallback used for job {job_id}")


async def _build_course_from_outline_modules_resilient(
    job_id: str,
    topic: str,
    outline: Dict[str, Any],
    job: Dict[str, Any],
    user_context: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Build full course content by generating modules from an outline.
    Each module has its own timeout to prevent stalls.
    """
    modules = []
    outline_modules = outline.get("modules", [])
    total = max(len(outline_modules), 1)

    for idx, module_outline in enumerate(outline_modules):
        job["current_step"] = f"Generating module {idx + 1} of {total}"
        job["progress_percent"] = 50 + int(((idx + 1) / total) * 40)
        job["updated_at"] = datetime.utcnow().isoformat()

        try:
            # ⏱️ Per-module timeout
            module = await asyncio.wait_for(
                _generate_module_content(
                    topic=topic,
                    outline=outline,
                    module_outline=module_outline
                ),
                timeout=TIMEOUT_MODULE_GENERATION
            )
        except asyncio.TimeoutError:
            print(f"⏱️ Module {idx + 1} timeout - using fallback")
            module = _build_fallback_module(module_outline, topic, user_context)
        except Exception as e:
            print(f"⚠️ Module {idx + 1} error: {e} - using fallback")
            module = _build_fallback_module(module_outline, topic, user_context)
        
        # 🌊 Incremental Update: Allow client to fetch finished modules immediately
        job.setdefault("module_results", {})[module.get("id")] = module
        modules.append(module)

    return {
        "course_id": job_id,
        "title": outline.get("title", f"Introduction to {topic}"),
        "description": outline.get("description", ""),
        "modules": modules,
        "estimated_duration": outline.get("estimated_duration", 60),
        "difficulty": outline.get("difficulty", "beginner")
    }


def _build_fallback_module(module_outline: Dict[str, Any], topic: str, user_context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Build a fallback module with REAL usable content when AI generation fails.
    """
    module_id = module_outline.get("id", f"mod_{hash(str(module_outline)) % 10000}")
    module_title = module_outline.get("title", "Module")
    
    level = user_context.get("level", "beginner") if user_context else "beginner"
    
    return {
        "id": module_id,
        "title": module_title,
        "description": module_outline.get("description", f"Learn about {module_title}"),
        "lessons": [
            {
                "id": f"{module_id}_les_1",
                "title": f"Introduction to {module_title}",
                "content": f"""## {module_title}

Welcome to this section on **{module_title}**. This is an essential part of your {topic} journey.

### What You'll Learn

Understanding {module_title} is crucial because it forms the foundation for more advanced concepts.

### Key Points

1. **Foundation**: Every journey in {topic} starts with understanding the basics. {module_title} provides the groundwork you need.

2. **Application**: Theory becomes powerful when applied. We'll explore how {module_title} works in real-world situations.

3. **Connection**: No concept exists in isolation. See how {module_title} connects to the broader landscape of {topic}.

### Summary

{module_title} is a crucial stepping stone in your {topic} journey. Take time to absorb these concepts before moving forward.
""",
                "duration_minutes": 15,
                "order": 1
            },
            {
                "id": f"{module_id}_les_2",
                "title": f"Applying {module_title}",
                "content": f"""## Practical Application of {module_title}

Now that you understand the basics, let's see how to apply {module_title} in practice.

### Real-World Examples

Consider how {module_title} impacts everyday situations:

- **Example 1**: Understanding how this concept works in professional settings
- **Example 2**: Seeing the patterns and principles in action
- **Example 3**: Recognizing opportunities to apply your knowledge

### Practice Exercise

Try to identify examples of {module_title} in your own experience. This will help reinforce your learning and make the concepts more memorable.

### Next Steps

Once you're comfortable with these basics, you'll be ready to explore more advanced topics in {topic}.
""",
                "duration_minutes": 20,
                "order": 2
            }
        ]
    }


def _build_fallback_course(job_id: str, topic: str, user_context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Build a fallback course when A2A orchestrator fails.
    """
    level = user_context.get("level", "beginner") if user_context else "beginner"
    outcomes = user_context.get("outcomes", "").split(",") if user_context else []

    return {
        "course_id": job_id,
        "title": f"Introduction to {topic}",
        "description": f"A comprehensive {level}-level course on {topic}. Learn the fundamentals and build practical skills.",
        "modules": [
            {
                "id": "mod_1",
                "title": "Getting Started",
                "description": f"Introduction to {topic} concepts",
                "lessons": [
                    {
                        "id": "les_1_1",
                        "title": f"What is {topic}?",
                        "content": f"Learn the fundamentals of {topic}, its applications, and why it's important to master.",
                        "duration_minutes": 15
                    },
                    {
                        "id": "les_1_2",
                        "title": "Key Concepts",
                        "content": f"Explore the essential concepts and terminology you need to understand {topic}.",
                        "duration_minutes": 20
                    }
                ]
            },
            {
                "id": "mod_2",
                "title": "Core Principles",
                "description": f"Deep dive into {topic} principles",
                "lessons": [
                    {
                        "id": "les_2_1",
                        "title": "Fundamental Principles",
                        "content": f"Master the core principles that govern {topic} and how to apply them effectively.",
                        "duration_minutes": 25
                    },
                    {
                        "id": "les_2_2",
                        "title": "Practical Applications",
                        "content": f"See how {topic} is applied in real-world scenarios and practice with examples.",
                        "duration_minutes": 30
                    }
                ]
            },
            {
                "id": "mod_3",
                "title": "Advanced Topics",
                "description": f"Advanced {topic} techniques",
                "lessons": [
                    {
                        "id": "les_3_1",
                        "title": "Advanced Techniques",
                        "content": f"Learn advanced techniques and best practices in {topic}.",
                        "duration_minutes": 35
                    },
                    {
                        "id": "les_3_2",
                        "title": "Mastery & Next Steps",
                        "content": f"Consolidate your {topic} knowledge and plan your continued learning journey.",
                        "duration_minutes": 20
                    }
                ]
            }
        ],
        "estimated_duration": 145,
        "difficulty": level,
        "learning_outcomes": [outcome.strip() for outcome in outcomes if outcome.strip()] or [
            f"Understand the fundamentals of {topic}",
            f"Apply {topic} concepts in practice",
            f"Build confidence with {topic} skills"
        ]
    }


def _build_course_from_artifacts(job_id: str, topic: str, artifacts: List) -> Dict[str, Any]:
    """
    Convert A2A artifacts to course structure.
    """
    # Extract curriculum artifact
    curriculum_artifact = None
    for artifact in artifacts:
        if artifact.type == ArtifactType.CURRICULUM_STRUCTURE:
            curriculum_artifact = artifact
            break
    
    if not curriculum_artifact or not curriculum_artifact.data:
        # Fallback: create basic course structure
        return {
            "course_id": job_id,
            "title": f"Introduction to {topic}",
            "description": f"A comprehensive course on {topic}",
            "modules": [
                {
                    "id": "mod_1",
                    "title": "Getting Started",
                    "description": "Foundation concepts",
                    "lessons": [
                        {
                            "id": "les_1_1",
                            "title": f"What is {topic}?",
                            "content": f"Learn the basics of {topic} and why it matters.",
                            "duration_minutes": 10
                        }
                    ]
                }
            ],
            "estimated_duration": 60,
            "difficulty": "beginner"
        }
    
    # Parse curriculum data
    curriculum_data = curriculum_artifact.data
    modules = []
    
    for idx, module_data in enumerate(curriculum_data.get("modules", [])):
        lessons = []
        for lesson_idx, lesson_data in enumerate(module_data.get("lessons", [])):
            lessons.append({
                "id": f"les_{idx + 1}_{lesson_idx + 1}",
                "title": lesson_data.get("title", f"Lesson {lesson_idx + 1}"),
                "content": lesson_data.get("content", ""),
                "duration_minutes": lesson_data.get("duration_minutes", 10)
            })
        
        modules.append({
            "id": f"mod_{idx + 1}",
            "title": module_data.get("title", f"Module {idx + 1}"),
            "description": module_data.get("description", ""),
            "lessons": lessons
        })
    
    return {
        "course_id": job_id,
        "title": curriculum_data.get("title", f"Course on {topic}"),
        "description": curriculum_data.get("description", ""),
        "modules": modules,
        "estimated_duration": curriculum_data.get("estimated_duration", 60),
        "difficulty": curriculum_data.get("difficulty", "beginner")
    }


def _build_outline(job_id: str, topic: str, user_context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Build a lightweight outline for immediate rendering and sharing.
    """
    level = user_context.get("level", "beginner") if user_context else "beginner"
    outcomes = user_context.get("outcomes", "").split(",") if user_context else []
    objectives = [o.strip() for o in outcomes if o.strip()]

    module_titles = [
        "Foundations",
        "Core Concepts",
        "Applied Practice",
        "Mastery & Next Steps"
    ]

    modules = []
    for idx, title in enumerate(module_titles, start=1):
        modules.append({
            "id": f"mod_{idx}",
            "title": f"{title} of {topic}",
            "description": f"Key ideas and skills for {title.lower()} in {topic}."
        })

    outline = {
        "course_id": job_id,
        "title": f"Introduction to {topic}",
        "description": f"A {level}-level course on {topic}.",
        "modules": modules,
        "estimated_duration": 120,
        "difficulty": level
    }

    outline_hash = hashlib.sha256(json.dumps(outline, sort_keys=True).encode("utf-8")).hexdigest()
    outline["outline_hash"] = outline_hash
    return outline


async def _build_course_from_outline_modules(
    job_id: str,
    topic: str,
    outline: Dict[str, Any],
    job: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build full course content by generating modules from an outline.
    """
    modules = []
    outline_modules = outline.get("modules", [])
    total = max(len(outline_modules), 1)

    for idx, module_outline in enumerate(outline_modules):
        job["current_step"] = f"Generating module {idx + 1} of {total}"
        job["progress_percent"] = 60 + int(((idx + 1) / total) * 30)
        job["updated_at"] = datetime.utcnow().isoformat()

        module = await _generate_module_content(
            topic=topic,
            outline=outline,
            module_outline=module_outline
        )
        
        # 🌊 Incremental Update: Allow client to fetch finished modules immediately
        job.setdefault("module_results", {})[module.get("id")] = module
        
        modules.append(module)

    return {
        "course_id": job_id,
        "title": outline.get("title", f"Introduction to {topic}"),
        "description": outline.get("description", ""),
        "modules": modules,
        "estimated_duration": outline.get("estimated_duration", 60),
        "difficulty": outline.get("difficulty", "beginner")
    }


async def _generate_module_content(
    topic: str,
    outline: Dict[str, Any],
    module_outline: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate a single module with lessons based on the outline contract.
    """
    if not ai_resilience_manager.session:
        await ai_resilience_manager.initialize()

    outline_hash = outline.get("outline_hash", "")
    module_id = module_outline.get("id")
    module_title = module_outline.get("title")
    module_description = module_outline.get("description")

    system_prompt = (
        "You are a course module writer. Use the outline as a strict contract. "
        "Return ONLY valid JSON with this schema:\n"
        "{\"id\": string, \"title\": string, \"description\": string, \"lessons\": ["
        "{\"id\": string, \"title\": string, \"content\": string, \"duration_minutes\": int}]}\n"
        "Rules: Keep lesson count between 3 and 6. Keep lesson content concise but useful. "
        "Do NOT invent new modules. Use the provided module id and title."
    )

    user_prompt = (
        f"Topic: {topic}\n"
        f"Outline hash: {outline_hash}\n"
        f"Course outline: {json.dumps(outline, ensure_ascii=False)}\n"
        f"Module to write: {json.dumps(module_outline, ensure_ascii=False)}"
    )

    ai_response = await ai_resilience_manager.chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=1200,
        provider_order=["gemini-2.0-flash", "gpt-4o-mini"],
    )

    raw = ai_response.get("content", "")
    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(raw[start : end + 1])
        except Exception:
            parsed = None

    if not parsed:
        return {
            "id": module_id,
            "title": module_title,
            "description": module_description,
            "lessons": [
                {
                    "id": f"{module_id}_les_1",
                    "title": "Overview",
                    "content": f"This module covers the essentials of {module_title}.",
                    "duration_minutes": 15,
                }
            ],
        }

    parsed.setdefault("id", module_id)
    parsed.setdefault("title", module_title)
    parsed.setdefault("description", module_description)
    return parsed
