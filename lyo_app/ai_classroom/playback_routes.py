"""
AI Classroom Playback Routes - Interactive Cinema Player API

These routes handle the core "Netflix-like" playback experience:
- Starting a course and getting the current node with assets
- Advancing through the course graph
- Submitting interaction responses
- Getting lookahead nodes for pre-loading
- Remediation requests
- Review queue management
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_async_session
from lyo_app.auth.dependencies import get_current_user
from lyo_app.auth.models import User
from lyo_app.ai_classroom.graph_service import GraphService, get_graph_service
from lyo_app.ai_classroom.models import (
    GraphCourse, LearningNode, CourseProgress, NodeType, 
    MasteryState, ReviewSchedule
)
from lyo_app.ai_classroom.schemas import (
    PlaybackState, PlaybackAdvanceRequest, 
    InteractionSubmitRequest, InteractionSubmitResponse,
    RemediationRequest, RemediationResponse,
    LearningNodeRead, LearningNodeWithAssets,
    ReviewQueueResponse, ReviewItem, ReviewSubmitRequest, ReviewSubmitResponse,
    MasteryDashboard, MasteryStateRead,
    CelebrationTrigger, AdSlot
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/classroom/playback", tags=["AI Classroom Playback"])


# =============================================================================
# DEPENDENCIES
# =============================================================================

async def get_db() -> AsyncSession:
    """Get database session."""
    async for session in get_async_session():
        yield session


# =============================================================================
# COURSE PLAYBACK ROUTES
# =============================================================================

@router.post("/courses/{course_id}/start")
async def start_course(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> PlaybackState:
    """
    Start a course and get the initial playback state.
    
    Returns the entry node with assets pre-loaded and the first
    few upcoming nodes for client-side pre-loading.
    """
    graph_service = get_graph_service(db)
    user_id = str(current_user.id)
    
    # Get or create progress
    progress = await graph_service.get_or_create_progress(user_id, course_id)
    
    # Get the course with its entry node
    course = await graph_service.get_course_with_graph(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    current_node_id = progress.current_node_id or course.entry_node_id
    if not current_node_id:
        raise HTTPException(status_code=400, detail="Course has no entry node")
    
    # Get current node
    current_node = await graph_service.get_node(current_node_id)
    if not current_node:
        raise HTTPException(status_code=404, detail="Entry node not found")
    
    # Get lookahead nodes for pre-loading
    lookahead = await graph_service.get_lookahead_nodes(current_node_id, user_id, count=3)
    
    # Build playback state
    return PlaybackState(
        course_id=course_id,
        current_node_id=current_node_id,
        current_node=_node_to_with_assets(current_node),
        next_nodes=[_node_to_read(n) for n in lookahead],
        completed_nodes=progress.completed_node_ids or [],
        progress_percent=progress.completion_percentage,
        total_time_seconds=progress.total_time_seconds,
        can_go_back=len(progress.completed_node_ids or []) > 0,
        is_at_interaction=current_node.node_type == NodeType.INTERACTION.value
    )


@router.get("/courses/{course_id}/node/current")
async def get_current_node(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> LearningNodeWithAssets:
    """
    Get the current node with all assets resolved.
    
    Use this to refresh the current node if assets weren't ready
    on initial load.
    """
    graph_service = get_graph_service(db)
    user_id = str(current_user.id)
    progress = await graph_service.get_or_create_progress(user_id, course_id)
    
    if not progress.current_node_id:
        raise HTTPException(status_code=400, detail="No current node in progress")
    
    node = await graph_service.get_node(progress.current_node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    return _node_to_with_assets(node)


@router.post("/courses/{course_id}/advance")
async def advance_course(
    course_id: str,
    request: PlaybackAdvanceRequest,
    current_user: User = Depends(get_current_user),
    time_spent_seconds: int = Query(default=0, description="Time spent on current node"),
    db: AsyncSession = Depends(get_db)
) -> PlaybackState:
    """
    Advance to the next node in the course.
    
    For narrative nodes, this simply moves forward.
    For interaction nodes, use /submit instead.
    """
    graph_service = get_graph_service(db)
    user_id = str(current_user.id)
    
    # Get best next node
    next_node = await graph_service.get_best_next_node(
        request.current_node_id, 
        user_id,
        interaction_result=None  # Not an interaction
    )
    
    if not next_node:
        # Course complete
        progress = await graph_service.advance_progress(
            user_id, course_id, request.current_node_id, None, time_spent_seconds
        )
        return PlaybackState(
            course_id=course_id,
            current_node_id=request.current_node_id,
            current_node=_node_to_with_assets(await graph_service.get_node(request.current_node_id)),
            next_nodes=[],
            completed_nodes=progress.completed_node_ids or [],
            progress_percent=100.0,
            total_time_seconds=progress.total_time_seconds,
            can_go_back=True,
            is_at_interaction=False
        )
    
    # Update progress
    progress = await graph_service.advance_progress(
        user_id, course_id, request.current_node_id, next_node.id, time_spent_seconds
    )
    
    # Get lookahead
    lookahead = await graph_service.get_lookahead_nodes(next_node.id, user_id, count=3)
    
    return PlaybackState(
        course_id=course_id,
        current_node_id=next_node.id,
        current_node=_node_to_with_assets(next_node),
        next_nodes=[_node_to_read(n) for n in lookahead],
        completed_nodes=progress.completed_node_ids or [],
        progress_percent=progress.completion_percentage,
        total_time_seconds=progress.total_time_seconds,
        can_go_back=True,
        is_at_interaction=next_node.node_type == NodeType.INTERACTION.value
    )


@router.get("/courses/{course_id}/lookahead")
async def get_lookahead(
    course_id: str,
    current_user: User = Depends(get_current_user),
    count: int = Query(default=3, ge=1, le=10),
    db: AsyncSession = Depends(get_db)
) -> List[LearningNodeRead]:
    """
    Get upcoming nodes for pre-loading assets.
    
    Call this to prefetch images and audio for upcoming nodes
    while the user watches the current one.
    """
    graph_service = get_graph_service(db)
    user_id = str(current_user.id)
    progress = await graph_service.get_or_create_progress(user_id, course_id)
    
    if not progress.current_node_id:
        return []
    
    lookahead = await graph_service.get_lookahead_nodes(
        progress.current_node_id, user_id, count=count
    )
    return [_node_to_read(n) for n in lookahead]


# =============================================================================
# INTERACTION ROUTES
# =============================================================================

@router.post("/interactions/submit")
async def submit_interaction(
    request: InteractionSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> InteractionSubmitResponse:
    """
    Submit a response to an interaction.
    
    Returns whether the answer was correct, the feedback, and
    the next node (could be next in sequence, or remediation).
    """
    graph_service = get_graph_service(db)
    user_id = str(current_user.id)
    
    # Get the node
    node = await graph_service.get_node(request.node_id)
    if not node or node.node_type != NodeType.INTERACTION.value:
        raise HTTPException(status_code=400, detail="Invalid interaction node")
    
    # Evaluate the answer
    content = node.content or {}
    options = content.get("options", [])
    
    is_correct = False
    feedback = "No feedback available"
    detected_misconception = None
    
    for opt in options:
        if opt.get("id") == request.answer_id:
            is_correct = opt.get("is_correct", False)
            feedback = opt.get("feedback", "")
            detected_misconception = opt.get("misconception_tag")
            break
    
    # Record the attempt
    await graph_service.record_interaction_attempt(
        user_id=user_id,
        node_id=request.node_id,
        user_answer=request.answer_id,
        is_correct=is_correct,
        time_taken_seconds=request.time_taken_seconds,
        detected_misconception_id=detected_misconception
    )
    
    # Update mastery if concept is linked
    mastery_change = 0.0
    if node.concept_id:
        old_mastery = await graph_service._get_user_mastery(user_id, node.concept_id)
        mastery = await graph_service.update_mastery(user_id, node.concept_id, is_correct)
        mastery_change = mastery.mastery_score - old_mastery
    
    # Determine next node
    next_node = await graph_service.get_best_next_node(
        request.node_id, user_id, interaction_result=is_correct
    )
    
    next_node_id = next_node.id if next_node else request.node_id
    
    # Check for remediation trigger
    if not is_correct:
        should_remediate, remaining = await graph_service.should_trigger_remediation(
            user_id, request.node_id
        )
        if should_remediate:
            # Try to get a remediation node from edges
            remediation_nodes = await graph_service.get_next_nodes(
                request.node_id, user_id, interaction_result=False
            )
            for rn, _ in remediation_nodes:
                if rn.node_type == NodeType.REMEDIATION.value:
                    next_node_id = rn.id
                    break
    
    # Check celebration trigger
    show_celebration = is_correct and await _should_celebrate(db, user_id)
    celebration_config = None
    if show_celebration:
        celebration_config = await _get_celebration_config(db)
    
    # Check ad trigger
    show_ad, ad_config = await _should_show_ad(db, user_id, request.course_id)
    
    return InteractionSubmitResponse(
        is_correct=is_correct,
        feedback=feedback,
        mastery_update=mastery_change,
        next_node_id=next_node_id,
        show_celebration=show_celebration,
        celebration_config=celebration_config,
        show_ad=show_ad,
        ad_config=ad_config
    )


@router.post("/interactions/{node_id}/feedback")
async def get_detailed_feedback(
    node_id: str,
    answer_id: str = Query(..., description="The submitted answer"),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed feedback for an interaction.
    
    Returns explanation, correct answer, and misconception info.
    """
    graph_service = get_graph_service(db)
    node = await graph_service.get_node(node_id)
    
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    content = node.content or {}
    options = content.get("options", [])
    
    selected_option = None
    correct_option = None
    
    for opt in options:
        if opt.get("id") == answer_id:
            selected_option = opt
        if opt.get("is_correct", False):
            correct_option = opt
    
    return {
        "selected_answer": selected_option,
        "correct_answer": correct_option,
        "explanation": content.get("explanation"),
        "misconception_addressed": selected_option.get("misconception_tag") if selected_option else None
    }


# =============================================================================
# REMEDIATION ROUTES
# =============================================================================

@router.post("/remediation/request")
async def request_remediation(
    request: RemediationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> RemediationResponse:
    """
    Request on-demand remediation for a concept.
    
    If budget allows, generates a new analogy to explain the concept.
    Otherwise, returns the gold-standard fallback.
    """
    from lyo_app.ai_classroom.remediation_service import get_remediation_service
    
    graph_service = get_graph_service(db)
    user_id = str(current_user.id)
    remediation_service = get_remediation_service(db)
    
    # Check budget
    should_remediate, remaining = await graph_service.should_trigger_remediation(
        user_id, request.node_id
    )
    
    if not should_remediate:
        # Return fallback
        fallback = await graph_service.get_fallback_node(request.node_id)
        if not fallback:
            raise HTTPException(
                status_code=400, 
                detail="Remediation budget exhausted and no fallback available"
            )
        return RemediationResponse(
            remediation_node=_node_to_with_assets(fallback),
            remaining_budget=0,
            original_node_id=request.node_id
        )
    
    # Generate new remediation
    node = await graph_service.get_node(request.node_id)
    remediation_node = await remediation_service.generate_remediation(
        original_node=node,
        user_id=user_id,
        misconception_tag=request.misconception_tag,
        user_complaint=request.user_complaint
    )
    
    return RemediationResponse(
        remediation_node=_node_to_with_assets(remediation_node),
        remaining_budget=remaining - 1,
        original_node_id=request.node_id
    )


# =============================================================================
# REVIEW / SPACED REPETITION ROUTES
# =============================================================================

@router.get("/review/today")
async def get_review_queue(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
) -> ReviewQueueResponse:
    """
    Get today's review queue based on spaced repetition.
    
    Returns items due for review, prioritized by urgency.
    """
    from sqlalchemy import select, and_
    from sqlalchemy.orm import selectinload
    
    user_id = str(current_user.id)
    now = datetime.utcnow()
    
    result = await db.execute(
        select(ReviewSchedule)
        .where(
            and_(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.is_active == True,
                ReviewSchedule.next_review_at <= now
            )
        )
        .order_by(ReviewSchedule.next_review_at)
        .limit(limit)
    )
    schedules = result.scalars().all()
    
    items = []
    total_seconds = 0
    
    for sched in schedules:
        # Calculate priority (overdue = higher priority)
        days_overdue = (now - sched.next_review_at).days
        priority = 1.0 + (days_overdue * 0.1)
        
        items.append(ReviewItem(
            node_id=sched.node_id or "",
            concept_name=sched.concept_id or "Unknown",  # Would look up in production
            last_reviewed_at=sched.last_reviewed_at,
            interval_days=sched.interval_days,
            streak=sched.streak,
            priority=priority
        ))
        total_seconds += 30  # Estimate 30 seconds per review
    
    return ReviewQueueResponse(
        user_id=user_id,
        total_items=len(items),
        estimated_minutes=max(1, total_seconds // 60),
        items=items
    )


@router.post("/review/submit")
async def submit_review(
    request: ReviewSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ReviewSubmitResponse:
    """
    Submit a review response and update the spaced repetition schedule.
    
    Uses SM-2 algorithm to calculate next review date.
    """
    from sqlalchemy import select, and_
    
    user_id = str(current_user.id)
    
    # Find the review schedule
    result = await db.execute(
        select(ReviewSchedule)
        .where(
            and_(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.node_id == request.node_id
            )
        )
    )
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Review schedule not found")
    
    # SM-2 algorithm
    q = request.quality
    ef = schedule.easiness_factor
    
    # Update easiness factor
    new_ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    new_ef = max(1.3, new_ef)  # Minimum EF
    
    # Calculate new interval
    if q < 3:
        # Failed recall - reset
        new_interval = 1
        new_rep = 0
        new_streak = 0
    else:
        new_streak = schedule.streak + 1
        new_rep = schedule.repetition_number + 1
        
        if new_rep == 1:
            new_interval = 1
        elif new_rep == 2:
            new_interval = 6
        else:
            new_interval = int(schedule.interval_days * new_ef)
    
    # Update schedule
    from datetime import timedelta
    schedule.easiness_factor = new_ef
    schedule.interval_days = new_interval
    schedule.repetition_number = new_rep
    schedule.last_reviewed_at = datetime.utcnow()
    schedule.next_review_at = datetime.utcnow() + timedelta(days=new_interval)
    schedule.last_quality = q
    schedule.streak = new_streak
    
    await db.commit()
    
    # Check for celebration
    show_celebration = q >= 4 and new_streak >= 3
    
    return ReviewSubmitResponse(
        next_review_date=schedule.next_review_at,
        new_interval_days=new_interval,
        streak=new_streak,
        show_celebration=show_celebration
    )


# =============================================================================
# MASTERY ROUTES
# =============================================================================

@router.get("/mastery/dashboard")
async def get_mastery_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> MasteryDashboard:
    """
    Get the user's mastery dashboard.
    
    Shows overall progress, strong/weak areas, and review stats.
    """
    from sqlalchemy import select, func, and_
    
    user_id = str(current_user.id)
    
    # Get all mastery states
    result = await db.execute(
        select(MasteryState)
        .where(MasteryState.user_id == user_id)
    )
    masteries = result.scalars().all()
    
    if not masteries:
        return MasteryDashboard(
            user_id=user_id,
            overall_mastery=0.0,
            concepts=[],
            weak_areas=[],
            strong_areas=[],
            next_review_count=0,
            streak_days=0
        )
    
    # Calculate overall mastery
    scores = [m.mastery_score for m in masteries]
    overall = sum(scores) / len(scores)
    
    # Find weak/strong areas
    weak = [m.concept_id for m in masteries if m.mastery_score < 0.5]
    strong = [m.concept_id for m in masteries if m.mastery_score >= 0.8]
    
    # Count upcoming reviews
    now = datetime.utcnow()
    review_result = await db.execute(
        select(func.count(ReviewSchedule.id))
        .where(
            and_(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.next_review_at <= now,
                ReviewSchedule.is_active == True
            )
        )
    )
    review_count = review_result.scalar() or 0
    
    return MasteryDashboard(
        user_id=user_id,
        overall_mastery=overall,
        concepts=[_mastery_to_read(m) for m in masteries],
        weak_areas=weak[:5],  # Top 5
        strong_areas=strong[:5],
        next_review_count=review_count,
        streak_days=0  # Would calculate from activity logs
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _node_to_read(node: LearningNode) -> LearningNodeRead:
    """Convert SQLAlchemy model to Pydantic read schema."""
    return LearningNodeRead(
        id=node.id,
        course_id=node.course_id,
        node_type=node.node_type,
        content=node.content or {},
        objective_id=node.objective_id,
        concept_id=node.concept_id,
        estimated_seconds=node.estimated_seconds,
        asset_tier=node.asset_tier,
        sequence_order=node.sequence_order,
        generated_asset_url=node.generated_asset_url,
        generated_audio_url=node.generated_audio_url,
        created_at=node.created_at
    )


def _node_to_with_assets(node: LearningNode) -> LearningNodeWithAssets:
    """Convert node to schema with resolved assets."""
    content = node.content or {}
    
    return LearningNodeWithAssets(
        id=node.id,
        course_id=node.course_id,
        node_type=node.node_type,
        content=content,
        objective_id=node.objective_id,
        concept_id=node.concept_id,
        estimated_seconds=node.estimated_seconds,
        asset_tier=node.asset_tier,
        sequence_order=node.sequence_order,
        generated_asset_url=node.generated_asset_url,
        generated_audio_url=node.generated_audio_url,
        created_at=node.created_at,
        image_url=node.generated_asset_url or content.get("visual_prompt"),
        audio_url=node.generated_audio_url,
        is_asset_ready=bool(node.generated_asset_url and node.generated_audio_url)
    )


def _mastery_to_read(mastery: MasteryState) -> MasteryStateRead:
    """Convert SQLAlchemy model to Pydantic read schema."""
    return MasteryStateRead(
        concept_id=mastery.concept_id,
        objective_id=mastery.objective_id,
        mastery_score=mastery.mastery_score,
        confidence=mastery.confidence,
        attempts=mastery.attempts,
        correct_count=mastery.correct_count,
        trend=mastery.trend,
        last_seen=mastery.last_seen
    )


async def _should_celebrate(db: AsyncSession, user_id: str) -> bool:
    """Check if celebration should be triggered."""
    # Simple logic: celebrate on correct answers
    # In production, check streak, milestones, A/B tests
    return True


async def _get_celebration_config(db: AsyncSession) -> Dict[str, Any]:
    """Get celebration configuration."""
    # Would query CelebrationConfig table with A/B test weights
    return {
        "animation_type": "confetti",
        "message": "Great job! 🎉",
        "avatar_url": "/assets/avatars/mascot_happy.png",
        "sound_effect": "success_chime"
    }


async def _should_show_ad(
    db: AsyncSession, 
    user_id: str, 
    course_id: str
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """Check if ad should be shown based on configuration."""
    # Would check:
    # - Is user premium?
    # - Cooldown since last ad
    # - Session frequency limits
    # - Latency context
    return False, None
