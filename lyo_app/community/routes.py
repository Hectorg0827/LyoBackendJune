"""
Community API routes for study groups and community events.
Provides RESTful endpoints for collaborative learning features.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.auth.routes import get_current_user
from lyo_app.auth.models import User
from lyo_app.community.service import CommunityService
from lyo_app.community.schemas import (
    StudyGroupCreate, StudyGroupUpdate, StudyGroupRead,
    GroupMembershipCreate, GroupMembershipUpdate, GroupMembershipRead,
    CommunityEventCreate, CommunityEventUpdate, CommunityEventRead,
    EventAttendanceCreate, EventAttendanceUpdate, EventAttendanceRead,
    BeaconBase, CommunityQuestionCreate, CommunityQuestionRead,
    CommunityAnswerCreate, CommunityAnswerRead
)
from lyo_app.community.models import StudyGroupPrivacy, EventType, AttendanceStatus
from lyo_app.stack import crud as stack_crud
from lyo_app.stack.models import StackItemType
import uuid

router = APIRouter()
community_service = CommunityService()


# Study Group Endpoints
@router.post("/study-groups", response_model=StudyGroupRead, status_code=status.HTTP_201_CREATED)
async def create_study_group(
    group_data: StudyGroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new study group."""
    try:
        study_group = await community_service.create_study_group(
            db=db, 
            creator_id=current_user.id, 
            group_data=group_data
        )
        return study_group
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create study group")


@router.get("/study-groups", response_model=List[StudyGroupRead])
async def list_study_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    privacy: Optional[StudyGroupPrivacy] = Query(None),
    course_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List study groups with filtering options."""
    try:
        study_groups = await community_service.get_study_groups(
            db=db,
            skip=skip,
            limit=limit,
            privacy=privacy,
            course_id=course_id,
            user_id=current_user.id
        )
        return study_groups
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch study groups")


@router.get("/study-groups/{group_id}", response_model=StudyGroupRead)
async def get_study_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific study group by ID."""
    try:
        study_group = await community_service.get_study_group_by_id(
            db=db, 
            group_id=group_id, 
            user_id=current_user.id
        )
        if not study_group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study group not found")
        return study_group
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch study group")


@router.put("/study-groups/{group_id}", response_model=StudyGroupRead)
async def update_study_group(
    group_id: int,
    group_data: StudyGroupUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a study group (creator or admin only)."""
    try:
        study_group = await community_service.update_study_group(
            db=db,
            group_id=group_id,
            group_data=group_data,
            user_id=current_user.id
        )
        if not study_group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study group not found")
        return study_group
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update study group")


@router.delete("/study-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_study_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a study group (creator only)."""
    try:
        success = await community_service.delete_study_group(
            db=db,
            group_id=group_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study group not found or access denied")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete study group")


# Group Membership Endpoints
@router.post("/study-groups/{group_id}/join", response_model=GroupMembershipRead, status_code=status.HTTP_201_CREATED)
async def join_study_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Join a study group."""
    try:
        membership_data = GroupMembershipCreate(study_group_id=group_id)
        membership = await community_service.join_study_group(
            db=db,
            user_id=current_user.id,
            membership_data=membership_data
        )
        return membership
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to join study group")


@router.delete("/study-groups/{group_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_study_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Leave a study group."""
    try:
        success = await community_service.leave_study_group(
            db=db,
            group_id=group_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to leave study group")


@router.get("/study-groups/{group_id}/members", response_model=List[GroupMembershipRead])
async def get_group_members(
    group_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get members of a study group."""
    try:
        members = await community_service.get_group_members(
            db=db,
            group_id=group_id,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        return members
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch group members")


@router.put("/study-groups/{group_id}/members/{member_id}", response_model=GroupMembershipRead)
async def update_group_membership(
    group_id: int,
    member_id: int,
    membership_data: GroupMembershipUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update group membership (admin only)."""
    try:
        membership = await community_service.update_group_membership(
            db=db,
            group_id=group_id,
            member_id=member_id,
            membership_data=membership_data,
            admin_user_id=current_user.id
        )
        if not membership:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
        return membership
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update membership")


@router.delete("/study-groups/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_member(
    group_id: int,
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a member from the study group (admin only)."""
    try:
        success = await community_service.remove_group_member(
            db=db,
            group_id=group_id,
            member_id=member_id,
            admin_user_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove member")


# Community Event Endpoints
@router.post("/events", response_model=CommunityEventRead, status_code=status.HTTP_201_CREATED)
async def create_community_event(
    event_data: CommunityEventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new community event."""
    try:
        event = await community_service.create_community_event(
            db=db,
            organizer_id=current_user.id,
            event_data=event_data
        )
        return event
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create event")


@router.get("/events", response_model=List[CommunityEventRead])
async def list_community_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    event_type: Optional[EventType] = Query(None),
    study_group_id: Optional[int] = Query(None),
    upcoming_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List community events with filtering options."""
    try:
        events = await community_service.get_community_events(
            db=db,
            skip=skip,
            limit=limit,
            event_type=event_type,
            study_group_id=study_group_id,
            upcoming_only=upcoming_only,
            user_id=current_user.id
        )
        return events
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch events")


@router.get("/events/{event_id}", response_model=CommunityEventRead)
async def get_community_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific community event by ID."""
    try:
        event = await community_service.get_community_event_by_id(
            db=db, 
            event_id=event_id, 
            user_id=current_user.id
        )
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return event
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch event")


@router.put("/events/{event_id}", response_model=CommunityEventRead)
async def update_community_event(
    event_id: int,
    event_data: CommunityEventUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a community event (organizer only)."""
    try:
        event = await community_service.update_community_event(
            db=db,
            event_id=event_id,
            event_data=event_data,
            user_id=current_user.id
        )
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return event
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update event")


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_community_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a community event (organizer only)."""
    try:
        success = await community_service.delete_community_event(
            db=db,
            event_id=event_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found or access denied")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete event")


# Event Attendance Endpoints
@router.post("/events/{event_id}/attend", response_model=EventAttendanceRead, status_code=status.HTTP_201_CREATED)
async def register_event_attendance(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Register attendance for an event."""
    try:
        attendance_data = EventAttendanceCreate(community_event_id=event_id)
        attendance = await community_service.register_event_attendance(
            db=db,
            user_id=current_user.id,
            attendance_data=attendance_data
        )
        return attendance
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to register attendance")


@router.put("/events/{event_id}/attendance", response_model=EventAttendanceRead)
async def update_event_attendance(
    event_id: int,
    attendance_status: AttendanceStatus,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update attendance status for an event."""
    try:
        attendance_data = EventAttendanceUpdate(status=attendance_status)
        attendance = await community_service.update_event_attendance(
            db=db,
            event_id=event_id,
            user_id=current_user.id,
            attendance_data=attendance_data
        )
        if not attendance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")
        return attendance
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update attendance")


@router.delete("/events/{event_id}/attend", status_code=status.HTTP_204_NO_CONTENT)
async def leave_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel attendance for an event."""
    success = await community_service.leave_event(
        db=db,
        event_id=event_id,
        user_id=current_user.id
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance not found")


# --- Phase 3: Campus Map & Beacons ---

@router.get("/beacons", response_model=List[BeaconBase])
async def get_beacons(
    lat: float,
    lng: float,
    radius_km: float = 10.0,
    limit: int = Query(100, ge=1, le=500),
    include_events: bool = True,
    include_users: bool = True,
    include_questions: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get map beacons (events, questions, users) near a location."""
    beacons: List[BeaconBase] = []

    # Distribute limit across types roughly equally if multiple are selected
    # This is a simple heuristic; in a real app we might want more sophisticated paging
    types_count = sum([include_events, include_users, include_questions])
    if types_count == 0:
        return []
    
    per_type_limit = limit  # Or limit // types_count if we wanted strict total limit

    if include_events:
        event_beacons = await community_service.get_event_beacons(db, lat, lng, radius_km, limit=per_type_limit)
        beacons.extend(event_beacons)

    if include_users:
        user_beacons = await community_service.get_user_activity_beacons(db, lat, lng, radius_km, current_user)
        beacons.extend(user_beacons)

    if include_questions:
        question_beacons = await community_service.get_question_beacons(db, lat, lng, radius_km, limit=per_type_limit)
        beacons.extend(question_beacons)

    return beacons


@router.post("/questions", response_model=CommunityQuestionRead)
async def create_question(
    payload: CommunityQuestionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Drop a question card at a location."""
    question = await community_service.create_question(
        db,
        user_id=current_user.id,
        data=payload,
    )
    
    # Create StackItem for this question
    await stack_crud.create_stack_item(
        db,
        user_id=current_user.id,
        type=StackItemType.QUESTION,
        ref_id=str(question.id),
        context_data={
            "location_name": question.location_name,
            "latitude": question.latitude,
            "longitude": question.longitude,
            "text": question.text
        },
    )
    return question


@router.post("/questions/{question_id}/answers", response_model=CommunityAnswerRead)
async def answer_question(
    question_id: uuid.UUID,
    payload: CommunityAnswerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Answer a community question."""
    question = await community_service.get_question(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    answer = await community_service.create_answer(
        db,
        question_id=question_id,
        user_id=current_user.id,
        data=payload,
    )
    return answer


@router.post("/events/{event_id}/save")
async def save_event_to_stack(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save an event to the user's stack."""
    event = await community_service.get_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    stack_item = await stack_crud.create_stack_item(
        db,
        user_id=current_user.id,
        type=StackItemType.EVENT,
        ref_id=str(event_id),
        context_data={
            "title": event.title,
            "location_name": event.location,
            "start_time": event.start_time.isoformat() if event.start_time else None,
            "latitude": event.latitude,
            "longitude": event.longitude
        },
    )
    return stack_item


# User-specific endpoints
@router.get("/my-groups", response_model=List[StudyGroupRead])
async def get_my_study_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get study groups the current user is a member of."""
    try:
        groups = await community_service.get_user_study_groups(
            db=db,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        return groups
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch user groups")


@router.get("/my-events", response_model=List[CommunityEventRead])
async def get_my_community_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    upcoming_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get events the current user is attending or organizing."""
    try:
        events = await community_service.get_user_community_events(
            db=db,
            user_id=current_user.id,
            upcoming_only=upcoming_only,
            skip=skip,
            limit=limit
        )
        return events
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch user events")


@router.get("/stats", response_model=dict)
async def get_community_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get community statistics for the current user."""
    try:
        stats = await community_service.get_user_community_stats(
            db=db,
            user_id=current_user.id
        )
        return stats
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch community stats")
