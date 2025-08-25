"""
Collaborative Learning API Routes for Phase 2
Advanced peer-to-peer learning and study group management
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timedelta

from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user
from lyo_app.auth.models import User
from lyo_app.collaboration.service import CollaborativeLearningEngine
from lyo_app.collaboration.schemas import (
    StudyGroupCreate,
    StudyGroupResponse,
    StudyGroupUpdate,
    StudyGroupMemberResponse,
    PeerInteractionCreate,
    PeerInteractionResponse,
    CollaborativeLearningSessionCreate,
    CollaborativeLearningSessionResponse,
    PeerMentorshipCreate,
    PeerMentorshipResponse,
    GroupMatchingRequest,
    GroupRecommendationResponse,
    CollaborationAnalyticsResponse,
    PeerAssessmentCreate,
    PeerAssessmentResponse
)

router = APIRouter(
    prefix="/api/v1/collaboration",
    tags=["collaborative-learning"],
    responses={404: {"description": "Not found"}}
)

# Initialize collaborative learning engine
collab_engine = CollaborativeLearningEngine()

# ========================================
# STUDY GROUP MANAGEMENT
# ========================================

@router.post("/groups", response_model=StudyGroupResponse)
async def create_study_group(
    group_data: StudyGroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new study group"""
    return await collab_engine.create_study_group(
        group_data=group_data,
        creator_id=current_user.id,
        db=db
    )

@router.get("/groups", response_model=List[StudyGroupResponse])
async def list_study_groups(
    subject_area: Optional[str] = Query(None),
    skill_level: Optional[str] = Query(None),
    is_public: bool = Query(True),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List available study groups with filtering"""
    return await collab_engine.list_study_groups(
        subject_area=subject_area,
        skill_level=skill_level,
        is_public=is_public,
        limit=limit,
        offset=offset,
        db=db
    )

@router.get("/groups/{group_id}", response_model=StudyGroupResponse)
async def get_study_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific study group details"""
    group = await collab_engine.get_study_group(group_id, db)
    if not group:
        raise HTTPException(status_code=404, detail="Study group not found")
    return group

@router.put("/groups/{group_id}", response_model=StudyGroupResponse)
async def update_study_group(
    group_id: int,
    group_data: StudyGroupUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update study group (admin/creator only)"""
    return await collab_engine.update_study_group(
        group_id=group_id,
        group_data=group_data,
        user_id=current_user.id,
        db=db
    )

@router.post("/groups/{group_id}/join")
async def join_study_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Join a study group"""
    return await collab_engine.join_study_group(
        group_id=group_id,
        user_id=current_user.id,
        db=db
    )

@router.post("/groups/{group_id}/leave")
async def leave_study_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Leave a study group"""
    return await collab_engine.leave_study_group(
        group_id=group_id,
        user_id=current_user.id,
        db=db
    )

@router.get("/groups/{group_id}/members", response_model=List[StudyGroupMemberResponse])
async def get_group_members(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get study group member list"""
    return await collab_engine.get_group_members(group_id, db)

# ========================================
# GROUP MATCHING & RECOMMENDATIONS
# ========================================

@router.post("/matching/recommendations", response_model=List[GroupRecommendationResponse])
async def get_group_recommendations(
    matching_request: GroupMatchingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get AI-powered study group recommendations"""
    return await collab_engine.get_group_recommendations(
        user_id=current_user.id,
        matching_criteria=matching_request,
        db=db
    )

@router.post("/matching/create-optimal")
async def create_optimal_group(
    matching_request: GroupMatchingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create an optimally matched study group using AI"""
    return await collab_engine.create_optimal_group(
        creator_id=current_user.id,
        matching_criteria=matching_request,
        db=db
    )

# ========================================
# PEER INTERACTIONS
# ========================================

@router.post("/interactions", response_model=PeerInteractionResponse)
async def create_peer_interaction(
    interaction_data: PeerInteractionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new peer interaction (question, help request, knowledge sharing)"""
    return await collab_engine.create_peer_interaction(
        interaction_data=interaction_data,
        initiator_id=current_user.id,
        db=db
    )

@router.get("/interactions", response_model=List[PeerInteractionResponse])
async def get_peer_interactions(
    group_id: Optional[int] = Query(None),
    interaction_type: Optional[str] = Query(None),
    skill_id: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get peer interactions with filtering"""
    return await collab_engine.get_peer_interactions(
        user_id=current_user.id,
        group_id=group_id,
        interaction_type=interaction_type,
        skill_id=skill_id,
        limit=limit,
        offset=offset,
        db=db
    )

@router.post("/interactions/{interaction_id}/respond")
async def respond_to_interaction(
    interaction_id: int,
    response_content: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Respond to a peer interaction"""
    return await collab_engine.respond_to_interaction(
        interaction_id=interaction_id,
        response_content=response_content,
        responder_id=current_user.id,
        db=db
    )

@router.post("/interactions/{interaction_id}/rate")
async def rate_interaction(
    interaction_id: int,
    helpfulness_rating: float = Query(..., ge=0.0, le=5.0),
    accuracy_rating: float = Query(..., ge=0.0, le=5.0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Rate the helpfulness and accuracy of a peer interaction"""
    return await collab_engine.rate_interaction(
        interaction_id=interaction_id,
        helpfulness_rating=helpfulness_rating,
        accuracy_rating=accuracy_rating,
        rater_id=current_user.id,
        db=db
    )

# ========================================
# COLLABORATIVE LEARNING SESSIONS
# ========================================

@router.post("/sessions", response_model=CollaborativeLearningSessionResponse)
async def create_learning_session(
    session_data: CollaborativeLearningSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a collaborative learning session"""
    return await collab_engine.create_learning_session(
        session_data=session_data,
        facilitator_id=current_user.id,
        db=db
    )

@router.get("/sessions", response_model=List[CollaborativeLearningSessionResponse])
async def list_learning_sessions(
    group_id: Optional[int] = Query(None),
    session_type: Optional[str] = Query(None),
    upcoming_only: bool = Query(True),
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List collaborative learning sessions"""
    return await collab_engine.list_learning_sessions(
        group_id=group_id,
        session_type=session_type,
        upcoming_only=upcoming_only,
        limit=limit,
        db=db
    )

@router.post("/sessions/{session_id}/join")
async def join_learning_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Join a collaborative learning session"""
    return await collab_engine.join_learning_session(
        session_id=session_id,
        user_id=current_user.id,
        db=db
    )

@router.post("/sessions/{session_id}/start")
async def start_learning_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a collaborative learning session (facilitator only)"""
    return await collab_engine.start_learning_session(
        session_id=session_id,
        facilitator_id=current_user.id,
        db=db
    )

@router.post("/sessions/{session_id}/end")
async def end_learning_session(
    session_id: int,
    completion_notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """End a collaborative learning session"""
    return await collab_engine.end_learning_session(
        session_id=session_id,
        facilitator_id=current_user.id,
        completion_notes=completion_notes,
        db=db
    )

# ========================================
# PEER MENTORSHIP
# ========================================

@router.post("/mentorship", response_model=PeerMentorshipResponse)
async def create_mentorship(
    mentorship_data: PeerMentorshipCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a peer mentorship relationship"""
    return await collab_engine.create_mentorship(
        mentorship_data=mentorship_data,
        requestor_id=current_user.id,
        db=db
    )

@router.get("/mentorship/as-mentor", response_model=List[PeerMentorshipResponse])
async def get_mentorships_as_mentor(
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get mentorships where current user is mentor"""
    return await collab_engine.get_mentorships_as_mentor(
        mentor_id=current_user.id,
        status=status,
        db=db
    )

@router.get("/mentorship/as-mentee", response_model=List[PeerMentorshipResponse])
async def get_mentorships_as_mentee(
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get mentorships where current user is mentee"""
    return await collab_engine.get_mentorships_as_mentee(
        mentee_id=current_user.id,
        status=status,
        db=db
    )

@router.post("/mentorship/{mentorship_id}/accept")
async def accept_mentorship(
    mentorship_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Accept a mentorship request (mentor only)"""
    return await collab_engine.accept_mentorship(
        mentorship_id=mentorship_id,
        mentor_id=current_user.id,
        db=db
    )

@router.post("/mentorship/{mentorship_id}/complete")
async def complete_mentorship(
    mentorship_id: int,
    completion_notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Complete a mentorship relationship"""
    return await collab_engine.complete_mentorship(
        mentorship_id=mentorship_id,
        user_id=current_user.id,
        completion_notes=completion_notes,
        db=db
    )

# ========================================
# PEER ASSESSMENT
# ========================================

@router.post("/assessment", response_model=PeerAssessmentResponse)
async def create_peer_assessment(
    assessment_data: PeerAssessmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a peer assessment"""
    return await collab_engine.create_peer_assessment(
        assessment_data=assessment_data,
        assessor_id=current_user.id,
        db=db
    )

@router.get("/assessment/received", response_model=List[PeerAssessmentResponse])
async def get_received_assessments(
    skill_id: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get assessments received by current user"""
    return await collab_engine.get_received_assessments(
        assessee_id=current_user.id,
        skill_id=skill_id,
        limit=limit,
        db=db
    )

@router.get("/assessment/given", response_model=List[PeerAssessmentResponse])
async def get_given_assessments(
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get assessments given by current user"""
    return await collab_engine.get_given_assessments(
        assessor_id=current_user.id,
        limit=limit,
        db=db
    )

# ========================================
# ANALYTICS & INSIGHTS
# ========================================

@router.get("/analytics/personal", response_model=CollaborationAnalyticsResponse)
async def get_personal_collaboration_analytics(
    timeframe_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get personal collaboration analytics and insights"""
    return await collab_engine.get_personal_collaboration_analytics(
        user_id=current_user.id,
        timeframe_days=timeframe_days,
        db=db
    )

@router.get("/analytics/group/{group_id}")
async def get_group_analytics(
    group_id: int,
    timeframe_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get study group analytics (members only)"""
    return await collab_engine.get_group_analytics(
        group_id=group_id,
        user_id=current_user.id,
        timeframe_days=timeframe_days,
        db=db
    )

@router.get("/leaderboard/contributors")
async def get_contribution_leaderboard(
    skill_area: Optional[str] = Query(None),
    timeframe_days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get leaderboard of top contributors"""
    return await collab_engine.get_contribution_leaderboard(
        skill_area=skill_area,
        timeframe_days=timeframe_days,
        limit=limit,
        db=db
    )

@router.get("/insights/learning-network")
async def get_learning_network_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get insights about user's learning network and connections"""
    return await collab_engine.get_learning_network_insights(
        user_id=current_user.id,
        db=db
    )
