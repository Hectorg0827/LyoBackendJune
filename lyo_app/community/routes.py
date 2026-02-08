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
from lyo_app.models.enhanced import User
from lyo_app.community.service import CommunityService
from lyo_app.community.schemas import (
    StudyGroupCreate, StudyGroupUpdate, StudyGroupRead,
    GroupMembershipCreate, GroupMembershipUpdate, GroupMembershipRead,
    CommunityEventCreate, CommunityEventUpdate, CommunityEventRead,
    EventAttendanceCreate, EventAttendanceUpdate, EventAttendanceRead,
    BeaconBase, CommunityQuestionCreate, CommunityQuestionRead,
    CommunityAnswerCreate, CommunityAnswerRead,
    MarketplaceItemCreate, MarketplaceItemUpdate, MarketplaceItemRead
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
    include_marketplace: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get map beacons (events, questions, users) near a location."""
    beacons: List[BeaconBase] = []

    # Distribute limit across types roughly equally if multiple are selected
    # This is a simple heuristic; in a real app we might want more sophisticated paging
    types_count = sum([include_events, include_users, include_questions, include_marketplace])
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

    if include_marketplace:
        marketplace_beacons = await community_service.get_marketplace_beacons(db, lat, lng, radius_km, limit=per_type_limit)
        beacons.extend(marketplace_beacons)

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


@router.get("/marketplace", response_model=List[MarketplaceItemRead])
async def list_marketplace_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List marketplace items."""
    try:
        items = await community_service.get_marketplace_items(
            db=db,
            skip=skip,
            limit=limit
        )
        return items
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch marketplace items")


@router.post("/marketplace", response_model=MarketplaceItemRead, status_code=status.HTTP_201_CREATED)
async def create_marketplace_item(
    item_data: MarketplaceItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new marketplace listing."""
    try:
        item = await community_service.create_marketplace_item(
            db=db,
            seller_id=current_user.id,
            item_data=item_data
        )
        return item
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create marketplace item")


@router.get("/marketplace/{item_id}", response_model=MarketplaceItemRead)
async def get_marketplace_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific marketplace item."""
    item = await community_service.get_marketplace_item_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.put("/marketplace/{item_id}", response_model=MarketplaceItemRead)
async def update_marketplace_item(
    item_id: int,
    item_data: MarketplaceItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a marketplace listing."""
    item = await community_service.update_marketplace_item(
        db, 
        item_id=item_id, 
        seller_id=current_user.id, 
        item_data=item_data
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found or unauthorized")
    return item


@router.delete("/marketplace/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_marketplace_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a marketplace listing."""
    success = await community_service.delete_marketplace_item(db, item_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found or unauthorized")
    return None


# =============================================================================
# SOCIAL FEED ENDPOINTS (Posts, Comments, Likes, Reports, Blocks)
# =============================================================================

from lyo_app.community.schemas import (
    PostCreate, PostUpdate, PostRead, PaginatedPostsResponse,
    CommentCreate, CommentRead, PaginatedCommentsResponse,
    ReportCreate, ReportRead, BlockUserCreate, BlockedUserRead
)
from lyo_app.community.models import PostType, PostVisibility


# Posts CRUD
@router.post("/posts", response_model=PostRead, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_data: PostCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new community post."""
    try:
        post = await community_service.create_post(
            db=db,
            author_id=current_user.id,
            post_data=post_data
        )
        return post
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create post")


@router.get("/posts", response_model=PaginatedPostsResponse)
async def list_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    post_type: Optional[PostType] = Query(None),
    sort_by: str = Query("recent", pattern="^(recent|popular|trending)$"),
    tag: Optional[str] = Query(None),
    author_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List posts with filtering, pagination, and sorting."""
    try:
        result = await community_service.get_posts(
            db=db,
            user_id=current_user.id,
            page=page,
            limit=limit,
            post_type=post_type,
            sort_by=sort_by,
            tag=tag,
            author_id=author_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch posts")


@router.get("/posts/{post_id}", response_model=PostRead)
async def get_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific post by ID."""
    try:
        post = await community_service.get_post_by_id(
            db=db,
            post_id=post_id,
            user_id=current_user.id
        )
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        return post
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch post")


@router.put("/posts/{post_id}", response_model=PostRead)
async def update_post(
    post_id: uuid.UUID,
    post_data: PostUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a post (author only)."""
    try:
        post = await community_service.update_post(
            db=db,
            post_id=post_id,
            author_id=current_user.id,
            post_data=post_data
        )
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found or access denied")
        return post
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update post")


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a post (author only)."""
    try:
        success = await community_service.delete_post(
            db=db,
            post_id=post_id,
            author_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found or access denied")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete post")


# Likes & Bookmarks
@router.post("/posts/{post_id}/like", status_code=status.HTTP_200_OK)
async def like_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Toggle like on a post."""
    try:
        result = await community_service.toggle_post_like(
            db=db,
            post_id=post_id,
            user_id=current_user.id
        )
        return {"liked": result["liked"], "like_count": result["like_count"]}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to toggle like")


@router.post("/posts/{post_id}/bookmark", status_code=status.HTTP_200_OK)
async def bookmark_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Toggle bookmark on a post."""
    try:
        result = await community_service.toggle_post_bookmark(
            db=db,
            post_id=post_id,
            user_id=current_user.id
        )
        return {"bookmarked": result["bookmarked"]}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to toggle bookmark")


# Comments
@router.get("/posts/{post_id}/comments", response_model=PaginatedCommentsResponse)
async def list_comments(
    post_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    parent_id: Optional[uuid.UUID] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List comments for a post with optional reply threading."""
    try:
        result = await community_service.get_comments(
            db=db,
            post_id=post_id,
            user_id=current_user.id,
            page=page,
            limit=limit,
            parent_id=parent_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch comments")


@router.post("/posts/{post_id}/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    post_id: uuid.UUID,
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a comment on a post."""
    try:
        comment = await community_service.create_comment(
            db=db,
            post_id=post_id,
            author_id=current_user.id,
            comment_data=comment_data
        )
        return comment
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create comment")


@router.delete("/posts/{post_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    post_id: uuid.UUID,
    comment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a comment (author only)."""
    try:
        success = await community_service.delete_comment(
            db=db,
            post_id=post_id,
            comment_id=comment_id,
            author_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found or access denied")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete comment")


@router.post("/posts/{post_id}/comments/{comment_id}/like", status_code=status.HTTP_200_OK)
async def like_comment(
    post_id: uuid.UUID,
    comment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Toggle like on a comment."""
    try:
        result = await community_service.toggle_comment_like(
            db=db,
            comment_id=comment_id,
            user_id=current_user.id
        )
        return {"liked": result["liked"], "like_count": result["like_count"]}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to toggle comment like")


# Moderation: Reports & Blocks
@router.post("/reports", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def report_content(
    report_data: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Report inappropriate content."""
    try:
        report = await community_service.create_report(
            db=db,
            reporter_id=current_user.id,
            report_data=report_data
        )
        return report
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create report")


@router.get("/blocks", response_model=List[BlockedUserRead])
async def list_blocked_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users blocked by current user."""
    try:
        blocks = await community_service.get_blocked_users(
            db=db,
            blocker_id=current_user.id
        )
        return blocks
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch blocked users")


@router.post("/blocks", response_model=BlockedUserRead, status_code=status.HTTP_201_CREATED)
async def block_user(
    block_data: BlockUserCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Block a user."""
    try:
        if block_data.user_id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot block yourself")
        
        block = await community_service.block_user(
            db=db,
            blocker_id=current_user.id,
            block_data=block_data
        )
        return block
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to block user")


@router.delete("/blocks/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unblock a user."""
    try:
        success = await community_service.unblock_user(
            db=db,
            blocker_id=current_user.id,
            blocked_id=user_id
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to unblock user")


# ── Stub endpoints expected by the iOS client ────────────────────────────
# These return empty arrays until full implementation is available.

@router.get("/courses/discover")
async def discover_courses(
    filters: Optional[str] = Query(None, description="Optional filter string"),
):
    """Discover shared community courses (stub)."""
    return []


@router.get("/institutions")
async def get_institutions(
    filters: Optional[str] = Query(None),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
):
    """List educational institutions (stub)."""
    return []


@router.get("/institutions/{institution_id}")
async def get_institution(institution_id: str):
    """Get institution details (stub)."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")


@router.get("/institutions/search")
async def search_institutions(
    query: str = Query("", description="Search query"),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
):
    """Search institutions (stub)."""
    return []

