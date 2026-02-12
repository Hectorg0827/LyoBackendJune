"""
Community service implementation.
Handles study groups, community events, and collaborative learning operations.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.community.models import (
    StudyGroup, GroupMembership, CommunityEvent, EventAttendance,
    StudyGroupStatus, StudyGroupPrivacy, MembershipRole,
    EventStatus, AttendanceStatus, CommunityQuestion, CommunityAnswer,
    MarketplaceItem, PrivateLesson, Booking, Review, BookingStatus
)
from lyo_app.community.schemas import (
    StudyGroupCreate, StudyGroupUpdate,
    GroupMembershipCreate, GroupMembershipUpdate,
    CommunityEventCreate, CommunityEventUpdate,
    EventAttendanceCreate, EventAttendanceUpdate,
    CommunityQuestionCreate, CommunityAnswerCreate,
    EventBeacon, QuestionBeacon, UserActivityBeacon, MarketplaceBeacon,
    MarketplaceItemCreate, MarketplaceItemUpdate,
    BookingCreate, ReviewCreate, BookingSlotRead,
    PrivateLessonCreate
)
from lyo_app.models.enhanced import User
from lyo_app.stack.models import StackItem, StackItemType, StackItemStatus
import uuid

class CommunityService:
    """Service class for community features - study groups and events."""

    # Study Group Operations
    async def create_study_group(
        self, 
        db: AsyncSession, 
        creator_id: int, 
        group_data: StudyGroupCreate
    ) -> StudyGroup:
        """
        Create a new study group.
        
        Args:
            db: Database session
            creator_id: ID of the user creating the group
            group_data: Study group creation data
            
        Returns:
            Created study group instance
        """
        db_group = StudyGroup(
            name=group_data.name,
            description=group_data.description,
            privacy=group_data.privacy,
            max_members=group_data.max_members,
            requires_approval=group_data.requires_approval,
            course_id=group_data.course_id,
            creator_id=creator_id,
            status=StudyGroupStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        db.add(db_group)
        await db.commit()
        await db.refresh(db_group)
        
        # Automatically add creator as owner
        creator_membership = GroupMembership(
            user_id=creator_id,
            study_group_id=db_group.id,
            role=MembershipRole.OWNER,
            is_approved=True,
            joined_at=datetime.utcnow(),
            approved_at=datetime.utcnow(),
            approved_by_id=creator_id,
        )
        
        db.add(creator_membership)
        await db.commit()
        
        return db_group

    async def get_study_group_by_id(
        self, 
        db: AsyncSession, 
        group_id: int, 
        user_id: Optional[int] = None
    ) -> Optional[StudyGroup]:
        """
        Get study group by ID with optional user context.
        
        Args:
            db: Database session
            group_id: Study group ID
            user_id: Optional user ID for permission checks
            
        Returns:
            Study group instance or None if not found
        """
        result = await db.execute(
            select(StudyGroup).where(StudyGroup.id == group_id)
        )
        group = result.scalar_one_or_none()
        
        if not group:
            return None
        
        # Check privacy permissions
        if group.privacy == StudyGroupPrivacy.PRIVATE and user_id:
            # Check if user is a member
            membership_result = await db.execute(
                select(GroupMembership).where(
                    and_(
                        GroupMembership.study_group_id == group_id,
                        GroupMembership.user_id == user_id,
                        GroupMembership.is_approved == True
                    )
                )
            )
            if not membership_result.scalar_one_or_none():
                return None
        
        return group

    async def _has_group_permission(
        self, 
        db: AsyncSession, 
        group_id: int, 
        user_id: int, 
        required_roles: List[MembershipRole]
    ) -> bool:
        """Check if user has one of the required roles in the group."""
        result = await db.execute(
            select(GroupMembership).where(
                and_(
                    GroupMembership.study_group_id == group_id,
                    GroupMembership.user_id == user_id,
                    GroupMembership.is_approved == True,
                    GroupMembership.role.in_(required_roles)
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def update_study_group(
        self, 
        db: AsyncSession, 
        group_id: int, 
        user_id: int, 
        group_data: StudyGroupUpdate
    ) -> Optional[StudyGroup]:
        """
        Update a study group.
        
        Args:
            db: Database session
            group_id: Study group ID to update
            user_id: ID of the user attempting to update
            group_data: Updated group data
            
        Returns:
            Updated study group instance or None if not found
            
        Raises:
            PermissionError: If user doesn't have update permissions
        """
        # Get the group
        group = await self.get_study_group_by_id(db, group_id)
        if not group:
            return None
        
        # Check permissions (owner or admin)
        if not await self._has_group_permission(db, group_id, user_id, [MembershipRole.OWNER, MembershipRole.ADMIN]):
            raise PermissionError("Insufficient permissions to update this group")
        
        # Update fields
        if group_data.name is not None:
            group.name = group_data.name
        if group_data.description is not None:
            group.description = group_data.description
        if group_data.privacy is not None:
            group.privacy = group_data.privacy
        if group_data.max_members is not None:
            group.max_members = group_data.max_members
        if group_data.requires_approval is not None:
            group.requires_approval = group_data.requires_approval
        if group_data.status is not None:
            group.status = group_data.status
        
        group.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(group)
        
        return group

    async def delete_study_group(
        self, 
        db: AsyncSession, 
        group_id: int, 
        user_id: int
    ) -> bool:
        """
        Delete a study group.
        
        Args:
            db: Database session
            group_id: Study group ID to delete
            user_id: ID of the user attempting to delete
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            PermissionError: If user is not the owner
        """
        # Get the group
        group = await self.get_study_group_by_id(db, group_id)
        if not group:
            return False
        
        # Check permissions (only owner can delete)
        if not await self._has_group_permission(db, group_id, user_id, [MembershipRole.OWNER]):
            raise PermissionError("Only group owners can delete groups")
        
        await db.delete(group)
        await db.commit()
        
        return True

    async def join_study_group(
        self, 
        db: AsyncSession, 
        user_id: int, 
        membership_data: GroupMembershipCreate
    ) -> GroupMembership:
        """
        Join a study group.
        
        Args:
            db: Database session
            user_id: User ID attempting to join
            membership_data: Membership data
            
        Returns:
            Created membership instance
            
        Raises:
            ValueError: If group doesn't exist, user already member, or group is full
        """
        group_id = membership_data.study_group_id
        
        # Verify group exists and is active
        group = await self.get_study_group_by_id(db, group_id)
        if not group or group.status != StudyGroupStatus.ACTIVE:
            raise ValueError("Study group not found or inactive")
        
        # Check if user is already a member
        existing_membership = await db.execute(
            select(GroupMembership).where(
                and_(
                    GroupMembership.user_id == user_id,
                    GroupMembership.study_group_id == group_id
                )
            )
        )
        if existing_membership.scalar_one_or_none():
            raise ValueError("Already a member of this group")
        
        # Check group capacity
        if group.max_members:
            member_count = await self._get_group_member_count(db, group_id)
            if member_count >= group.max_members:
                raise ValueError("Study group is full")
        
        # Check privacy restrictions
        if group.privacy == StudyGroupPrivacy.PRIVATE:
            raise ValueError("Cannot join private group without invitation")
        
        # Determine approval status
        is_approved = not group.requires_approval
        approved_at = datetime.utcnow() if is_approved else None
        
        db_membership = GroupMembership(
            user_id=user_id,
            study_group_id=group_id,
            role=MembershipRole.MEMBER,
            is_approved=is_approved,
            joined_at=datetime.utcnow(),
            approved_at=approved_at,
            approved_by_id=group.creator_id if is_approved else None,
        )
        
        db.add(db_membership)
        await db.commit()
        await db.refresh(db_membership)
        
        return db_membership

    async def leave_study_group(
        self, 
        db: AsyncSession, 
        user_id: int, 
        group_id: int
    ) -> bool:
        """
        Leave a study group.
        
        Args:
            db: Database session
            user_id: User ID attempting to leave
            group_id: Study group ID to leave
            
        Returns:
            True if left successfully, False if not a member
            
        Raises:
            ValueError: If user is the group owner
        """
        # Get membership
        membership_result = await db.execute(
            select(GroupMembership).where(
                and_(
                    GroupMembership.user_id == user_id,
                    GroupMembership.study_group_id == group_id
                )
            )
        )
        membership = membership_result.scalar_one_or_none()
        
        if not membership:
            return False
        
        # Prevent owner from leaving (must transfer ownership first)
        if membership.role == MembershipRole.OWNER:
            raise ValueError("Group owners cannot leave. Transfer ownership first.")
        
        await db.delete(membership)
        await db.commit()
        
        return True

    async def get_study_groups(
        self, 
        db: AsyncSession, 
        user_id: Optional[int] = None,
        course_id: Optional[int] = None,
        privacy: Optional[StudyGroupPrivacy] = None,
        status: Optional[StudyGroupStatus] = StudyGroupStatus.ACTIVE,
        skip: int = 0, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get study groups with filtering and pagination.
        
        Args:
            db: Database session
            user_id: Optional user ID for personalized results
            course_id: Filter by course ID
            privacy: Filter by privacy level
            status: Filter by status
            page: Page number (1-based)
            per_page: Items per page
            
        Returns:
            Paginated groups response
        """
        # Build query
        query = select(StudyGroup).options(selectinload(StudyGroup.creator))
        conditions = []
        
        if status:
            conditions.append(StudyGroup.status == status)
        if course_id:
            conditions.append(StudyGroup.course_id == course_id)
        if privacy:
            conditions.append(StudyGroup.privacy == privacy)
        else:
            # Only show public groups by default unless user is specified
            if not user_id:
                conditions.append(StudyGroup.privacy == StudyGroupPrivacy.PUBLIC)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # Get groups
        result = await db.execute(
            query.order_by(desc(StudyGroup.created_at))
            .offset(skip)
            .limit(limit)
        )
        groups = result.scalars().all()
        
        # Get total count
        count_query = select(func.count(StudyGroup.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        count_result = await db.execute(count_query)
        total = count_result.scalar()
        
        # Add member count and user context
        groups_data = []
        for group in groups:
            member_count = await self._get_group_member_count(db, group.id)
            user_membership = None
            
            if user_id:
                user_membership = await self._get_user_membership(db, group.id, user_id)
            
            group_data = {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "privacy": group.privacy,
                "status": group.status,
                "max_members": group.max_members,
                "requires_approval": group.requires_approval,
                "course_id": group.course_id,
                "creator_id": group.creator_id,
                "created_at": group.created_at,
                "updated_at": group.updated_at,
                "member_count": member_count,
                "is_member": user_membership is not None,
                "user_role": user_membership.role if user_membership else None,
                "host": {
                    "id": group.creator.id,
                    "name": f"{group.creator.first_name or ''} {group.creator.last_name or group.creator.username}".strip(),
                    "avatar": group.creator.avatar_url
                } if group.creator else None
            }
            groups_data.append(group_data)
        
        return groups_data

    # Community Event Operations
    async def create_community_event(
        self, 
        db: AsyncSession, 
        organizer_id: int, 
        event_data: CommunityEventCreate
    ) -> CommunityEvent:
        """
        Create a new community event.
        
        Args:
            db: Database session
            organizer_id: ID of the user organizing the event
            event_data: Event creation data
            
        Returns:
            Created event instance
            
        Raises:
            ValueError: If validation fails or permissions insufficient
        """
        # Validate dates
        if event_data.end_time <= event_data.start_time:
            raise ValueError("End time must be after start time")
        
        # If associated with study group, check permissions
        if event_data.study_group_id:
            if not await self._has_group_permission(
                db, event_data.study_group_id, organizer_id, 
                [MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.MODERATOR]
            ):
                raise PermissionError("Insufficient permissions to create events for this group")
        
        db_event = CommunityEvent(
            title=event_data.title,
            description=event_data.description,
            event_type=event_data.event_type,
            location=event_data.location,
            meeting_url=event_data.meeting_url,
            max_attendees=event_data.max_attendees,
            start_time=event_data.start_time,
            end_time=event_data.end_time,
            timezone=event_data.timezone,
            organizer_id=organizer_id,
            study_group_id=event_data.study_group_id,
            course_id=event_data.course_id,
            lesson_id=event_data.lesson_id,
            status=EventStatus.SCHEDULED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        db.add(db_event)
        await db.commit()
        await db.refresh(db_event)
        
        # Automatically register organizer
        organizer_attendance = EventAttendance(
            user_id=organizer_id,
            event_id=db_event.id,
            status=AttendanceStatus.GOING,
            registered_at=datetime.utcnow(),
        )
        
        db.add(organizer_attendance)
        await db.commit()
        
        return db_event

    async def get_community_event_by_id(
        self, 
        db: AsyncSession, 
        event_id: int
    ) -> Optional[CommunityEvent]:
        """
        Get community event by ID.
        
        Args:
            db: Database session
            event_id: Event ID
            
        Returns:
            Event instance or None if not found
        """
        result = await db.execute(
            select(CommunityEvent).where(CommunityEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def update_community_event(
        self, 
        db: AsyncSession, 
        event_id: int, 
        user_id: int, 
        event_data: CommunityEventUpdate
    ) -> Optional[CommunityEvent]:
        """
        Update a community event.
        
        Args:
            db: Database session
            event_id: Event ID to update
            user_id: ID of the user attempting to update
            event_data: Updated event data
            
        Returns:
            Updated event instance or None if not found
            
        Raises:
            PermissionError: If user doesn't have update permissions
        """
        # Get the event
        event = await self.get_community_event_by_id(db, event_id)
        if not event:
            return None
        
        # Check permissions (organizer or group admin)
        has_permission = event.organizer_id == user_id
        if not has_permission and event.study_group_id:
            has_permission = await self._has_group_permission(
                db, event.study_group_id, user_id, 
                [MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.MODERATOR]
            )
        
        if not has_permission:
            raise PermissionError("Insufficient permissions to update this event")
        
        # Validate dates if both are being updated
        start_time = event_data.start_time or event.start_time
        end_time = event_data.end_time or event.end_time
        
        if end_time <= start_time:
            raise ValueError("End time must be after start time")
        
        # Update fields
        if event_data.title is not None:
            event.title = event_data.title
        if event_data.description is not None:
            event.description = event_data.description
        if event_data.event_type is not None:
            event.event_type = event_data.event_type
        if event_data.location is not None:
            event.location = event_data.location
        if event_data.meeting_url is not None:
            event.meeting_url = event_data.meeting_url
        if event_data.max_attendees is not None:
            event.max_attendees = event_data.max_attendees
        if event_data.start_time is not None:
            event.start_time = event_data.start_time
        if event_data.end_time is not None:
            event.end_time = event_data.end_time
        if event_data.timezone is not None:
            event.timezone = event_data.timezone
        if event_data.status is not None:
            event.status = event_data.status
        
        event.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(event)
        
        return event

    async def delete_community_event(
        self, 
        db: AsyncSession, 
        event_id: int, 
        user_id: int
    ) -> bool:
        """
        Delete a community event.
        
        Args:
            db: Database session
            event_id: Event ID to delete
            user_id: ID of the user attempting to delete
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            PermissionError: If user doesn't have delete permissions
        """
        # Get the event
        event = await self.get_community_event_by_id(db, event_id)
        if not event:
            return False
        
        # Check permissions (organizer or group owner)
        has_permission = event.organizer_id == user_id
        if not has_permission and event.study_group_id:
            has_permission = await self._has_group_permission(
                db, event.study_group_id, user_id, [MembershipRole.OWNER]
            )
        
        if not has_permission:
            raise PermissionError("Insufficient permissions to delete this event")
        
        await db.delete(event)
        await db.commit()
        
        return True

    async def register_for_event(
        self, 
        db: AsyncSession, 
        user_id: int, 
        attendance_data: EventAttendanceCreate
    ) -> EventAttendance:
        """
        Register for a community event.
        
        Args:
            db: Database session
            user_id: User ID attempting to register
            attendance_data: Attendance data
            
        Returns:
            Created attendance instance
            
        Raises:
            ValueError: If event doesn't exist, user already registered, or event is full
        """
        event_id = attendance_data.event_id
        
        # Verify event exists and is scheduled
        event = await self.get_community_event_by_id(db, event_id)
        if not event or event.status != EventStatus.SCHEDULED:
            raise ValueError("Event not found or not available for registration")
        
        # Check if user is already registered
        existing_attendance = await db.execute(
            select(EventAttendance).where(
                and_(
                    EventAttendance.user_id == user_id,
                    EventAttendance.event_id == event_id
                )
            )
        )
        if existing_attendance.scalar_one_or_none():
            raise ValueError("Already registered for this event")
        
        # Check event capacity
        if event.max_attendees:
            attendee_count = await self._get_event_attendee_count(db, event_id)
            if attendee_count >= event.max_attendees:
                raise ValueError("Event is full")
        
        db_attendance = EventAttendance(
            user_id=user_id,
            event_id=event_id,
            status=attendance_data.status,
            registered_at=datetime.utcnow(),
        )
        
        db.add(db_attendance)
        await db.commit()
        await db.refresh(db_attendance)
        
        return db_attendance

    async def update_event_attendance(
        self, 
        db: AsyncSession, 
        attendance_id: int, 
        user_id: int, 
        attendance_data: EventAttendanceUpdate
    ) -> Optional[EventAttendance]:
        """
        Update event attendance.
        
        Args:
            db: Database session
            attendance_id: Attendance ID to update
            user_id: ID of the user updating attendance
            attendance_data: Updated attendance data
            
        Returns:
            Updated attendance instance or None if not found
            
        Raises:
            PermissionError: If user doesn't own the attendance record
        """
        # Get the attendance record
        result = await db.execute(
            select(EventAttendance).where(EventAttendance.id == attendance_id)
        )
        attendance = result.scalar_one_or_none()
        
        if not attendance:
            return None
        
        # Check ownership
        if attendance.user_id != user_id:
            raise PermissionError("Can only update your own attendance")
        
        # Update fields
        if attendance_data.status is not None:
            attendance.status = attendance_data.status
            if attendance_data.status == AttendanceStatus.ATTENDED:
                attendance.attended_at = datetime.utcnow()
        
        if attendance_data.rating is not None:
            attendance.rating = attendance_data.rating
            attendance.feedback_at = datetime.utcnow()
        
        if attendance_data.feedback is not None:
            attendance.feedback = attendance_data.feedback
            attendance.feedback_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(attendance)
        
        return attendance

    async def cancel_event_registration(
        self, 
        db: AsyncSession, 
        user_id: int, 
        event_id: int
    ) -> bool:
        """
        Cancel event registration.
        
        Args:
            db: Database session
            user_id: User ID canceling registration
            event_id: Event ID to cancel registration for
            
        Returns:
            True if canceled, False if not registered
        """
        # Get attendance record
        result = await db.execute(
            select(EventAttendance).where(
                and_(
                    EventAttendance.user_id == user_id,
                    EventAttendance.event_id == event_id
                )
            )
        )
        attendance = result.scalar_one_or_none()
        
        if not attendance:
            return False
        
        await db.delete(attendance)
        await db.commit()
        
        return True

    async def get_community_events(
        self, 
        db: AsyncSession, 
        user_id: Optional[int] = None,
        study_group_id: Optional[int] = None,
        course_id: Optional[int] = None,
        event_type: Optional[str] = None,
        status: Optional[EventStatus] = None,
        upcoming_only: bool = False,
        skip: int = 0, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get community events with filtering and pagination.
        
        Args:
            db: Database session
            user_id: Optional user ID for personalized results
            study_group_id: Filter by study group ID
            course_id: Filter by course ID
            event_type: Filter by event type
            status: Filter by status
            upcoming_only: Only show future events
            page: Page number (1-based)
            per_page: Items per page
            
        Returns:
            Paginated events response
        """
        # Build query
        query = select(CommunityEvent).options(selectinload(CommunityEvent.organizer))
        conditions = []
        
        if status:
            conditions.append(CommunityEvent.status == status)
        if study_group_id:
            conditions.append(CommunityEvent.study_group_id == study_group_id)
        if course_id:
            conditions.append(CommunityEvent.course_id == course_id)
        if event_type:
            conditions.append(CommunityEvent.event_type == event_type)
        if upcoming_only:
            conditions.append(CommunityEvent.start_time > datetime.utcnow())
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # Get events
        result = await db.execute(
            query.order_by(asc(CommunityEvent.start_time))
            .offset(skip)
            .limit(limit)
        )
        events = result.scalars().all()
        
        # Add attendee count and user context
        events_data = []
        for event in events:
            try:
                # Defensive check for potential None event
                if not event:
                    continue

                attendee_count = await self._get_event_attendee_count(db, event.id)
                user_attendance = None
                
                if user_id:
                    user_attendance = await self._get_user_attendance(db, event.id, user_id)
                
                # Parse organizer name safely
                organizer_data = None
                if event.organizer:
                    organizer_name = f"{event.organizer.first_name or ''} {event.organizer.last_name or event.organizer.username}".strip()
                    if not organizer_name:
                        organizer_name = "Unknown Organizer"
                        
                    organizer_data = {
                        "id": event.organizer.id,
                        "name": organizer_name,
                        "avatar": event.organizer.avatar_url
                    }

                event_data = {
                    "id": event.id,
                    "title": event.title,
                    "description": event.description,
                    "event_type": event.event_type,
                    "status": event.status,
                    "location": event.location,
                    "meeting_url": event.meeting_url,
                    "max_attendees": event.max_attendees,
                    "start_time": event.start_time,
                    "end_time": event.end_time,
                    "timezone": event.timezone,
                    "organizer_id": event.organizer_id,
                    "study_group_id": event.study_group_id,
                    "course_id": event.course_id,
                    "lesson_id": event.lesson_id,
                    "created_at": event.created_at,
                    "updated_at": event.updated_at,
                    "latitude": event.latitude,
                    "longitude": event.longitude,
                    "room_id": event.room_id,
                    "image_url": event.image_url,
                    "attendee_count": attendee_count,
                    "user_attendance_status": user_attendance.status if user_attendance else None,
                    "is_full": bool(event.max_attendees and attendee_count >= event.max_attendees),
                    "organizer_profile": organizer_data
                }
                events_data.append(event_data)
            except Exception as e:
                logger.error(f"Error processing community event {getattr(event, 'id', 'unknown')}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue
        
        return events_data

    async def get_community_events_count(
        self,
        db: AsyncSession,
        user_id: Optional[int] = None,
        study_group_id: Optional[int] = None,
        course_id: Optional[int] = None,
        event_type: Optional[str] = None,
        status: Optional[EventStatus] = None,
        upcoming_only: bool = False
    ) -> int:
        """
        Get total count of community events matching filters.
        """
        query = select(func.count(CommunityEvent.id))
        conditions = []
        
        if status:
            conditions.append(CommunityEvent.status == status)
        if study_group_id:
            conditions.append(CommunityEvent.study_group_id == study_group_id)
        if course_id:
            conditions.append(CommunityEvent.course_id == course_id)
        if event_type:
            conditions.append(CommunityEvent.event_type == event_type)
        if upcoming_only:
            conditions.append(CommunityEvent.start_time > datetime.utcnow())
        
        if conditions:
            query = query.where(and_(*conditions))
            
        result = await db.execute(query)
        return result.scalar() or 0

    async def get_community_stats(self, db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """
        Get community statistics for a user.
        
        Args:
            db: Database session
            user_id: User ID to get stats for
            
        Returns:
            Community statistics
        """
        # Total groups
        total_groups_result = await db.execute(
            select(func.count(StudyGroup.id)).where(StudyGroup.status == StudyGroupStatus.ACTIVE)
        )
        total_groups = total_groups_result.scalar() or 0
        
        # Active groups (same as total for now)
        active_groups = total_groups
        
        # Total events
        total_events_result = await db.execute(
            select(func.count(CommunityEvent.id))
        )
        total_events = total_events_result.scalar() or 0
        
        # Upcoming events
        upcoming_events_result = await db.execute(
            select(func.count(CommunityEvent.id)).where(
                and_(
                    CommunityEvent.start_time > datetime.utcnow(),
                    CommunityEvent.status == EventStatus.SCHEDULED
                )
            )
        )
        upcoming_events = upcoming_events_result.scalar() or 0
        
        # Total memberships
        total_memberships_result = await db.execute(
            select(func.count(GroupMembership.id)).where(GroupMembership.is_approved == True)
        )
        total_memberships = total_memberships_result.scalar() or 0
        
        # User's groups
        user_groups_result = await db.execute(
            select(func.count(GroupMembership.id)).where(
                and_(
                    GroupMembership.user_id == user_id,
                    GroupMembership.is_approved == True
                )
            )
        )
        user_groups_count = user_groups_result.scalar() or 0
        
        # User's events
        user_events_result = await db.execute(
            select(func.count(EventAttendance.id)).where(
                and_(
                    EventAttendance.user_id == user_id,
                    EventAttendance.status.in_([AttendanceStatus.GOING, AttendanceStatus.MAYBE])
                )
            )
        )
        user_events_count = user_events_result.scalar() or 0
        
        return {
            "total_groups": total_groups,
            "active_groups": active_groups,
            "total_events": total_events,
            "upcoming_events": upcoming_events,
            "total_memberships": total_memberships,
            "user_groups_count": user_groups_count,
            "user_events_count": user_events_count,
        }

    async def _get_group_member_count(self, db: AsyncSession, group_id: int) -> int:
        """Get count of active members in a group."""
        result = await db.execute(
            select(func.count(GroupMembership.id)).where(
                and_(
                    GroupMembership.study_group_id == group_id,
                    GroupMembership.is_approved == True
                )
            )
        )
        return result.scalar() or 0

    async def _get_user_membership(self, db: AsyncSession, group_id: int, user_id: int) -> Optional[GroupMembership]:
        """Get user's membership for a group."""
        result = await db.execute(
            select(GroupMembership).where(
                and_(
                    GroupMembership.study_group_id == group_id,
                    GroupMembership.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()

    # Phase 3: Campus Map & Beacons
    
    async def get_event_beacons(
        self, 
        db: AsyncSession, 
        lat: float, 
        lng: float, 
        radius_km: float,
        limit: int = 100
    ) -> List[EventBeacon]:
        """
        Get event beacons within a radius.
        """
        # Naive bounding box: 1 degree ~ 111km
        delta = radius_km / 111.0
        
        query = (
            select(CommunityEvent)
            .where(CommunityEvent.latitude.is_not(None))
            .where(CommunityEvent.longitude.is_not(None))
            .where(CommunityEvent.latitude.between(lat - delta, lat + delta))
            .where(CommunityEvent.longitude.between(lng - delta, lng + delta))
            .where(CommunityEvent.status.in_([EventStatus.SCHEDULED, EventStatus.ONGOING]))
            .limit(limit)
        )
        
        result = await db.execute(query)
        events = result.scalars().all()
        
        return [
            EventBeacon(
                id=e.id,
                title=e.title,
                latitude=e.latitude,
                longitude=e.longitude,
                location_name=e.location,
                start_time=e.start_time,
                end_time=e.end_time,
            )
            for e in events
        ]

    async def get_question_beacons(
        self, 
        db: AsyncSession, 
        lat: float, 
        lng: float, 
        radius_km: float,
        limit: int = 100
    ) -> List[QuestionBeacon]:
        """
        Get question beacons within a radius.
        """
        delta = radius_km / 111.0
        
        query = (
            select(CommunityQuestion)
            .where(CommunityQuestion.latitude.is_not(None))
            .where(CommunityQuestion.longitude.is_not(None))
            .where(CommunityQuestion.latitude.between(lat - delta, lat + delta))
            .where(CommunityQuestion.longitude.between(lng - delta, lng + delta))
            .where(CommunityQuestion.is_resolved == False)
            .limit(limit)
        )
        
        result = await db.execute(query)
        questions = result.scalars().all()
        
        return [
            QuestionBeacon(
                id=q.id,
                text=q.text,
                latitude=q.latitude,
                longitude=q.longitude,
                location_name=q.location_name,
                is_resolved=q.is_resolved,
            )
            for q in questions
        ]

    async def get_user_activity_beacons(
        self, 
        db: AsyncSession, 
        lat: float, 
        lng: float, 
        radius_km: float,
        current_user: User
    ) -> List[UserActivityBeacon]:
        """
        Get user activity beacons. Finds users who have recently interacted or posted
        near the specified map area.
        """
        delta = radius_km / 111.0
        
        # Find recent questions by any users in this area
        question_query = (
            select(CommunityQuestion)
            .where(CommunityQuestion.latitude.between(lat - delta, lat + delta))
            .where(CommunityQuestion.longitude.between(lng - delta, lng + delta))
            .order_by(desc(CommunityQuestion.created_at))
            .limit(50)
        )
        q_result = await db.execute(question_query)
        questions = q_result.scalars().all()
        
        active_user_ids = {q.user_id for q in questions}
        
        # Find upcoming events organized in this area
        event_query = (
            select(CommunityEvent)
            .where(CommunityEvent.latitude.between(lat - delta, lat + delta))
            .where(CommunityEvent.longitude.between(lng - delta, lng + delta))
            .order_by(desc(CommunityEvent.created_at))
            .limit(50)
        )
        e_result = await db.execute(event_query)
        events = e_result.scalars().all()
        active_user_ids.update({e.organizer_id for e in events})
        
        if not active_user_ids:
            return []
            
        # Get user details and their gamification profiles
        user_query = (
            select(User)
            .options(selectinload(User.gamification_profile))
            .where(User.id.in_(list(active_user_ids)))
        )
        u_result = await db.execute(user_query)
        users = u_result.scalars().all()
        
        beacons = []
        for u in users:
            # Skip current user unless specified
            if u.id == current_user.id:
                continue
                
            # Find a representative location for this user in this area
            # (Use their most recent question or event in the area)
            user_lat, user_lng = None, None
            for q in questions:
                if q.user_id == u.id:
                    user_lat, user_lng = q.latitude, q.longitude
                    break
            if not user_lat:
                for e in events:
                    if e.organizer_id == u.id:
                        user_lat, user_lng = e.latitude, e.longitude
                        break
            
            beacons.append(
                UserActivityBeacon(
                    user_id=u.id,
                    display_name=f"{u.first_name or ''} {u.last_name or u.username}".strip(),
                    latitude=user_lat,
                    longitude=user_lng,
                    level=u.gamification_profile.level if u.gamification_profile else 1,
                    xp=u.gamification_profile.total_xp if u.gamification_profile else 0,
                    recent_topics=[] # Could be populated from their recent posts/courses
                )
            )
            
        return beacons

    async def create_question(
        self, 
        db: AsyncSession, 
        user_id: int, 
        data: CommunityQuestionCreate
    ) -> CommunityQuestion:
        """
        Create a new location-based question.
        """
        db_question = CommunityQuestion(
            user_id=user_id,
            text=data.text,
            latitude=data.latitude,
            longitude=data.longitude,
            location_name=data.location_name,
            created_at=datetime.utcnow(),
        )
        
        db.add(db_question)
        await db.commit()
        await db.refresh(db_question)
        
        return db_question

    async def get_question(self, db: AsyncSession, question_id: uuid.UUID) -> Optional[CommunityQuestion]:
        result = await db.execute(select(CommunityQuestion).where(CommunityQuestion.id == question_id))
        return result.scalar_one_or_none()

    async def create_answer(
        self, 
        db: AsyncSession, 
        question_id: uuid.UUID, 
        user_id: int, 
        data: CommunityAnswerCreate
    ) -> CommunityAnswer:
        """
        Answer a community question.
        """
        db_answer = CommunityAnswer(
            question_id=question_id,
            user_id=user_id,
            text=data.text,
            created_at=datetime.utcnow(),
        )
        
        db.add(db_answer)
        await db.commit()
        await db.refresh(db_answer)
        
        return db_answer

    async def get_event(self, db: AsyncSession, event_id: int) -> Optional[CommunityEvent]:
        result = await db.execute(select(CommunityEvent).where(CommunityEvent.id == event_id))
        return result.scalar_one_or_none()

    # Marketplace Operations

    async def create_marketplace_item(
        self, 
        db: AsyncSession, 
        seller_id: int, 
        item_data: MarketplaceItemCreate
    ) -> MarketplaceItem:
        """Create a new marketplace listing."""
        db_item = MarketplaceItem(
            title=item_data.title,
            description=item_data.description,
            price=item_data.price,
            currency=item_data.currency,
            latitude=item_data.latitude,
            longitude=item_data.longitude,
            location_name=item_data.location_name,
            image_urls=item_data.image_urls,
            seller_id=seller_id,
            is_active=True,
            is_sold=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        db.add(db_item)
        await db.commit()
        await db.refresh(db_item)
        return db_item

    async def get_marketplace_item_by_id(self, db: AsyncSession, item_id: int) -> Optional[MarketplaceItem]:
        result = await db.execute(select(MarketplaceItem).where(MarketplaceItem.id == item_id))
        return result.scalar_one_or_none()

    async def get_marketplace_items(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 20,
        is_active: bool = True,
        is_sold: bool = False
    ) -> List[MarketplaceItem]:
        query = select(MarketplaceItem).options(selectinload(MarketplaceItem.seller)).where(
            and_(
                MarketplaceItem.is_active == is_active,
                MarketplaceItem.is_sold == is_sold
            )
        ).offset(skip).limit(limit).order_by(desc(MarketplaceItem.created_at))
        
        result = await db.execute(query)
        items = result.scalars().all()
        
        # Populate seller_avatar in the model instance for the schema to pick up
        for item in items:
            if item.seller:
                item.seller_avatar = item.seller.avatar_url
        
        return items

    async def update_marketplace_item(
        self, 
        db: AsyncSession, 
        item_id: int, 
        seller_id: int, 
        item_data: MarketplaceItemUpdate
    ) -> Optional[MarketplaceItem]:
        item = await self.get_marketplace_item_by_id(db, item_id)
        if not item or item.seller_id != seller_id:
            return None
            
        if item_data.title is not None:
            item.title = item_data.title
        if item_data.description is not None:
            item.description = item_data.description
        if item_data.price is not None:
            item.price = item_data.price
        if item_data.currency is not None:
            item.currency = item_data.currency
        if item_data.is_active is not None:
            item.is_active = item_data.is_active
        if item_data.is_sold is not None:
            item.is_sold = item_data.is_sold
            
        item.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(item)
        return item

    async def delete_marketplace_item(self, db: AsyncSession, item_id: int, seller_id: int) -> bool:
        item = await self.get_marketplace_item_by_id(db, item_id)
        if not item or item.seller_id != seller_id:
            return False
            
        await db.delete(item)
        await db.commit()
        return True

    async def get_marketplace_beacons(
        self, 
        db: AsyncSession, 
        lat: float, 
        lng: float, 
        radius_km: float,
        limit: int = 100
    ) -> List[MarketplaceBeacon]:
        delta = radius_km / 111.0
        query = (
            select(MarketplaceItem)
            .where(MarketplaceItem.latitude.is_not(None))
            .where(MarketplaceItem.longitude.is_not(None))
            .where(MarketplaceItem.latitude.between(lat - delta, lat + delta))
            .where(MarketplaceItem.longitude.between(lng - delta, lng + delta))
            .where(MarketplaceItem.is_active == True)
            .where(MarketplaceItem.is_sold == False)
            .limit(limit)
        )
        result = await db.execute(query)
        items = result.scalars().all()
        
        return [
            MarketplaceBeacon(
                id=i.id,
                title=i.title,
                latitude=i.latitude,
                longitude=i.longitude,
                price=i.price,
                currency=i.currency
            )
            for i in items
        ]

    # Helper Methods
    async def _has_group_permission(
        self, 
        db: AsyncSession, 
        group_id: int, 
        user_id: int, 
        required_roles: List[MembershipRole]
    ) -> bool:
        """Check if user has required permissions in a group."""
        membership_result = await db.execute(
            select(GroupMembership).where(
                and_(
                    GroupMembership.study_group_id == group_id,
                    GroupMembership.user_id == user_id,
                    GroupMembership.is_approved == True,
                    GroupMembership.role.in_(required_roles)
                )
            )
        )
        return membership_result.scalar_one_or_none() is not None

    async def _get_group_member_count(self, db: AsyncSession, group_id: int) -> int:
        """Get the number of approved members in a group."""
        result = await db.execute(
            select(func.count(GroupMembership.id)).where(
                and_(
                    GroupMembership.study_group_id == group_id,
                    GroupMembership.is_approved == True
                )
            )
        )
        return result.scalar() or 0

    async def _get_user_membership(
        self, 
        db: AsyncSession, 
        group_id: int, 
        user_id: int
    ) -> Optional[GroupMembership]:
        """Get user's membership in a group."""
        result = await db.execute(
            select(GroupMembership).where(
                and_(
                    GroupMembership.study_group_id == group_id,
                    GroupMembership.user_id == user_id,
                    GroupMembership.is_approved == True
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_event_attendee_count(self, db: AsyncSession, event_id: int) -> int:
        """Get the number of attendees for an event."""
        result = await db.execute(
            select(func.count(EventAttendance.id)).where(
                and_(
                    EventAttendance.event_id == event_id,
                    EventAttendance.status.in_([
                        AttendanceStatus.GOING, 
                        AttendanceStatus.MAYBE, 
                        AttendanceStatus.ATTENDED
                    ])
                )
            )
        )
        return result.scalar() or 0

    async def _get_user_attendance(
        self, 
        db: AsyncSession, 
        event_id: int, 
        user_id: int
    ) -> Optional[EventAttendance]:
        """Get user's attendance record for an event."""
        result = await db.execute(
            select(EventAttendance).where(
                and_(
                    EventAttendance.event_id == event_id,
                    EventAttendance.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()

    # =============================================================================
    # SOCIAL FEED OPERATIONS (Posts, Comments, Likes, Reports, Blocks)
    # =============================================================================

    from lyo_app.community.models import (
        CommunityPost, PostComment, PostLike, PostBookmark,
        ContentReport, UserBlock, PostType, PostVisibility,
        ReportTargetType, ReportReason, ReportStatus
    )
    from lyo_app.community.schemas import (
        PostCreate, PostUpdate, CommentCreate,
        ReportCreate, BlockUserCreate
    )

    async def create_post(
        self,
        db: AsyncSession,
        author_id: int,
        post_data: "PostCreate"
    ) -> Dict[str, Any]:
        """Create a new community post."""
        from lyo_app.community.models import CommunityPost
        
        # Get author info
        user = await db.get(User, author_id)
        if not user:
            raise ValueError("User not found")
        
        db_post = CommunityPost(
            author_id=author_id,
            author_name=user.display_name or user.username or f"User {author_id}",
            author_avatar=user.avatar_url,
            author_level=getattr(user, 'level', 1) or 1,
            content=post_data.content,
            media_urls=post_data.media_urls or [],
            tags=post_data.tags or [],
            post_type=post_data.post_type,
            visibility=post_data.visibility,
            linked_course_id=post_data.linked_course_id,
            linked_group_id=post_data.linked_group_id,
        )
        
        db.add(db_post)
        await db.commit()
        await db.refresh(db_post)
        
        return self._post_to_dict(db_post, has_liked=False, has_bookmarked=False)

    async def get_posts(
        self,
        db: AsyncSession,
        user_id: int,
        page: int = 1,
        limit: int = 20,
        post_type: Optional[Any] = None,
        sort_by: str = "recent",
        tag: Optional[str] = None,
        author_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get posts with filtering and pagination."""
        from lyo_app.community.models import CommunityPost, PostLike, PostBookmark, UserBlock
        
        # Get blocked user IDs
        blocked_result = await db.execute(
            select(UserBlock.blocked_id).where(UserBlock.blocker_id == user_id)
        )
        blocked_ids = [r[0] for r in blocked_result.fetchall()]
        
        # Build query
        query = select(CommunityPost).where(
            CommunityPost.is_deleted == False,
            CommunityPost.visibility == PostVisibility.PUBLIC
        )
        
        # Exclude blocked users
        if blocked_ids:
            query = query.where(~CommunityPost.author_id.in_(blocked_ids))
        
        # Apply filters
        if post_type:
            query = query.where(CommunityPost.post_type == post_type)
        
        if tag:
            query = query.where(CommunityPost.tags.contains([tag]))
        
        if author_id:
            query = query.where(CommunityPost.author_id == author_id)
        
        # Apply sorting
        if sort_by == "popular":
            query = query.order_by(desc(CommunityPost.like_count))
        elif sort_by == "trending":
            # Trending = recent + popular
            query = query.order_by(
                desc(CommunityPost.like_count + CommunityPost.comment_count),
                desc(CommunityPost.created_at)
            )
        else:  # recent
            query = query.order_by(desc(CommunityPost.created_at))
        
        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total_count = total_result.scalar() or 0
        
        # Paginate
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        posts = result.scalars().all()
        
        # Get user's likes and bookmarks for these posts
        post_ids = [p.id for p in posts]
        
        liked_result = await db.execute(
            select(PostLike.post_id).where(
                PostLike.post_id.in_(post_ids),
                PostLike.user_id == user_id
            )
        )
        liked_ids = {r[0] for r in liked_result.fetchall()}
        
        bookmarked_result = await db.execute(
            select(PostBookmark.post_id).where(
                PostBookmark.post_id.in_(post_ids),
                PostBookmark.user_id == user_id
            )
        )
        bookmarked_ids = {r[0] for r in bookmarked_result.fetchall()}
        
        items = [
            self._post_to_dict(p, p.id in liked_ids, p.id in bookmarked_ids)
            for p in posts
        ]
        
        return {
            "items": items,
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "total_pages": (total_count + limit - 1) // limit
        }

    async def get_post_by_id(
        self,
        db: AsyncSession,
        post_id: uuid.UUID,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a single post by ID."""
        from lyo_app.community.models import CommunityPost, PostLike, PostBookmark
        
        result = await db.execute(
            select(CommunityPost).where(
                CommunityPost.id == post_id,
                CommunityPost.is_deleted == False
            )
        )
        post = result.scalar_one_or_none()
        
        if not post:
            return None
        
        # Check like/bookmark status
        like_result = await db.execute(
            select(PostLike).where(
                PostLike.post_id == post_id,
                PostLike.user_id == user_id
            )
        )
        has_liked = like_result.scalar_one_or_none() is not None
        
        bookmark_result = await db.execute(
            select(PostBookmark).where(
                PostBookmark.post_id == post_id,
                PostBookmark.user_id == user_id
            )
        )
        has_bookmarked = bookmark_result.scalar_one_or_none() is not None
        
        return self._post_to_dict(post, has_liked, has_bookmarked)

    async def update_post(
        self,
        db: AsyncSession,
        post_id: uuid.UUID,
        author_id: int,
        post_data: "PostUpdate"
    ) -> Optional[Dict[str, Any]]:
        """Update a post (author only)."""
        from lyo_app.community.models import CommunityPost
        
        result = await db.execute(
            select(CommunityPost).where(
                CommunityPost.id == post_id,
                CommunityPost.is_deleted == False
            )
        )
        post = result.scalar_one_or_none()
        
        if not post:
            return None
        
        if post.author_id != author_id:
            raise ValueError("Not authorized to update this post")
        
        if post_data.content is not None:
            post.content = post_data.content
        if post_data.tags is not None:
            post.tags = post_data.tags
        if post_data.visibility is not None:
            post.visibility = post_data.visibility
        
        post.is_edited = True
        post.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(post)
        
        return self._post_to_dict(post, False, False)

    async def delete_post(
        self,
        db: AsyncSession,
        post_id: uuid.UUID,
        author_id: int
    ) -> bool:
        """Soft delete a post (author only)."""
        from lyo_app.community.models import CommunityPost
        
        result = await db.execute(
            select(CommunityPost).where(
                CommunityPost.id == post_id,
                CommunityPost.is_deleted == False
            )
        )
        post = result.scalar_one_or_none()
        
        if not post:
            return False
        
        if post.author_id != author_id:
            raise ValueError("Not authorized to delete this post")
        
        post.is_deleted = True
        post.updated_at = datetime.utcnow()
        
        await db.commit()
        return True

    async def toggle_post_like(
        self,
        db: AsyncSession,
        post_id: uuid.UUID,
        user_id: int
    ) -> Dict[str, Any]:
        """Toggle like on a post."""
        from lyo_app.community.models import CommunityPost, PostLike
        
        # Check post exists
        post_result = await db.execute(
            select(CommunityPost).where(
                CommunityPost.id == post_id,
                CommunityPost.is_deleted == False
            )
        )
        post = post_result.scalar_one_or_none()
        
        if not post:
            raise ValueError("Post not found")
        
        # Check existing like
        like_result = await db.execute(
            select(PostLike).where(
                PostLike.post_id == post_id,
                PostLike.user_id == user_id
            )
        )
        existing_like = like_result.scalar_one_or_none()
        
        if existing_like:
            # Unlike
            await db.delete(existing_like)
            post.like_count = max(0, post.like_count - 1)
            liked = False
        else:
            # Like
            new_like = PostLike(post_id=post_id, user_id=user_id)
            db.add(new_like)
            post.like_count += 1
            liked = True
        
        await db.commit()
        
        return {"liked": liked, "like_count": post.like_count}

    async def toggle_post_bookmark(
        self,
        db: AsyncSession,
        post_id: uuid.UUID,
        user_id: int
    ) -> Dict[str, Any]:
        """Toggle bookmark on a post."""
        from lyo_app.community.models import CommunityPost, PostBookmark
        
        # Check post exists
        post_result = await db.execute(
            select(CommunityPost).where(
                CommunityPost.id == post_id,
                CommunityPost.is_deleted == False
            )
        )
        post = post_result.scalar_one_or_none()
        
        if not post:
            raise ValueError("Post not found")
        
        # Check existing bookmark
        bookmark_result = await db.execute(
            select(PostBookmark).where(
                PostBookmark.post_id == post_id,
                PostBookmark.user_id == user_id
            )
        )
        existing_bookmark = bookmark_result.scalar_one_or_none()
        
        if existing_bookmark:
            await db.delete(existing_bookmark)
            bookmarked = False
        else:
            new_bookmark = PostBookmark(post_id=post_id, user_id=user_id)
            db.add(new_bookmark)
            bookmarked = True
        
        await db.commit()
        
        return {"bookmarked": bookmarked}

    async def get_comments(
        self,
        db: AsyncSession,
        post_id: uuid.UUID,
        user_id: int,
        page: int = 1,
        limit: int = 20,
        parent_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """Get comments for a post with pagination."""
        from lyo_app.community.models import PostComment, UserBlock
        
        # Get blocked user IDs
        blocked_result = await db.execute(
            select(UserBlock.blocked_id).where(UserBlock.blocker_id == user_id)
        )
        blocked_ids = [r[0] for r in blocked_result.fetchall()]
        
        query = select(PostComment).where(
            PostComment.post_id == post_id,
            PostComment.is_deleted == False
        )
        
        if parent_id:
            query = query.where(PostComment.parent_id == parent_id)
        else:
            query = query.where(PostComment.parent_id.is_(None))
        
        if blocked_ids:
            query = query.where(~PostComment.author_id.in_(blocked_ids))
        
        query = query.order_by(asc(PostComment.created_at))
        
        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total_count = total_result.scalar() or 0
        
        # Paginate
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        comments = result.scalars().all()
        
        items = [self._comment_to_dict(c, False) for c in comments]
        
        return {
            "items": items,
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "total_pages": (total_count + limit - 1) // limit
        }

    async def create_comment(
        self,
        db: AsyncSession,
        post_id: uuid.UUID,
        author_id: int,
        comment_data: "CommentCreate"
    ) -> Dict[str, Any]:
        """Create a comment on a post."""
        from lyo_app.community.models import CommunityPost, PostComment
        
        # Check post exists
        post_result = await db.execute(
            select(CommunityPost).where(
                CommunityPost.id == post_id,
                CommunityPost.is_deleted == False
            )
        )
        post = post_result.scalar_one_or_none()
        
        if not post:
            raise ValueError("Post not found")
        
        # Get author info
        user = await db.get(User, author_id)
        if not user:
            raise ValueError("User not found")
        
        db_comment = PostComment(
            post_id=post_id,
            author_id=author_id,
            author_name=user.display_name or user.username or f"User {author_id}",
            author_avatar=user.avatar_url,
            content=comment_data.content,
            parent_id=comment_data.parent_id,
        )
        
        db.add(db_comment)
        
        # Update post comment count
        post.comment_count += 1
        
        # Update parent reply count if this is a reply
        if comment_data.parent_id:
            parent_result = await db.execute(
                select(PostComment).where(PostComment.id == comment_data.parent_id)
            )
            parent = parent_result.scalar_one_or_none()
            if parent:
                parent.reply_count += 1
        
        await db.commit()
        await db.refresh(db_comment)
        
        return self._comment_to_dict(db_comment, False)

    async def delete_comment(
        self,
        db: AsyncSession,
        post_id: uuid.UUID,
        comment_id: uuid.UUID,
        author_id: int
    ) -> bool:
        """Soft delete a comment (author only)."""
        from lyo_app.community.models import CommunityPost, PostComment
        
        result = await db.execute(
            select(PostComment).where(
                PostComment.id == comment_id,
                PostComment.post_id == post_id,
                PostComment.is_deleted == False
            )
        )
        comment = result.scalar_one_or_none()
        
        if not comment:
            return False
        
        if comment.author_id != author_id:
            raise ValueError("Not authorized to delete this comment")
        
        comment.is_deleted = True
        
        # Update post comment count
        post_result = await db.execute(
            select(CommunityPost).where(CommunityPost.id == post_id)
        )
        post = post_result.scalar_one_or_none()
        if post:
            post.comment_count = max(0, post.comment_count - 1)
        
        await db.commit()
        return True

    async def toggle_comment_like(
        self,
        db: AsyncSession,
        comment_id: uuid.UUID,
        user_id: int
    ) -> Dict[str, Any]:
        """Toggle like on a comment."""
        from lyo_app.community.models import PostComment
        
        # Note: For simplicity, we're just tracking like_count on the comment
        # A full implementation would have a CommentLike junction table
        result = await db.execute(
            select(PostComment).where(
                PostComment.id == comment_id,
                PostComment.is_deleted == False
            )
        )
        comment = result.scalar_one_or_none()
        
        if not comment:
            raise ValueError("Comment not found")
        
        # Simple toggle (in production, use a junction table)
        # For now, just increment/decrement
        comment.like_count += 1
        
        await db.commit()
        
        return {"liked": True, "like_count": comment.like_count}

    async def create_report(
        self,
        db: AsyncSession,
        reporter_id: int,
        report_data: "ReportCreate"
    ) -> Dict[str, Any]:
        """Create a content report."""
        from lyo_app.community.models import ContentReport, ReportStatus
        
        db_report = ContentReport(
            reporter_id=reporter_id,
            target_type=report_data.target_type,
            target_id=report_data.target_id,
            reason=report_data.reason,
            description=report_data.description,
        )
        
        db.add(db_report)
        await db.commit()
        await db.refresh(db_report)
        
        return {
            "id": str(db_report.id),
            "status": db_report.status.value,
            "message": "Report submitted successfully"
        }

    async def get_blocked_users(
        self,
        db: AsyncSession,
        blocker_id: int
    ) -> List[Dict[str, Any]]:
        """Get list of users blocked by current user."""
        from lyo_app.community.models import UserBlock
        
        result = await db.execute(
            select(UserBlock).where(UserBlock.blocker_id == blocker_id)
        )
        blocks = result.scalars().all()
        
        blocked_list = []
        for block in blocks:
            user = await db.get(User, block.blocked_id)
            if user:
                blocked_list.append({
                    "id": block.id,
                    "user_id": block.blocked_id,
                    "user_name": user.display_name or user.username or f"User {block.blocked_id}",
                    "user_avatar": user.avatar_url,
                    "blocked_at": block.created_at
                })
        
        return blocked_list

    async def block_user(
        self,
        db: AsyncSession,
        blocker_id: int,
        block_data: "BlockUserCreate"
    ) -> Dict[str, Any]:
        """Block a user."""
        from lyo_app.community.models import UserBlock
        
        # Check if already blocked
        existing = await db.execute(
            select(UserBlock).where(
                UserBlock.blocker_id == blocker_id,
                UserBlock.blocked_id == block_data.user_id
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("User already blocked")
        
        db_block = UserBlock(
            blocker_id=blocker_id,
            blocked_id=block_data.user_id,
            reason=block_data.reason
        )
        
        db.add(db_block)
        await db.commit()
        await db.refresh(db_block)
        
        user = await db.get(User, block_data.user_id)
        
        return {
            "id": db_block.id,
            "user_id": block_data.user_id,
            "user_name": user.display_name if user else f"User {block_data.user_id}",
            "user_avatar": user.avatar_url if user else None,
            "blocked_at": db_block.created_at
        }

    async def unblock_user(
        self,
        db: AsyncSession,
        blocker_id: int,
        blocked_id: int
    ) -> bool:
        """Unblock a user."""
        from lyo_app.community.models import UserBlock
        
        result = await db.execute(
            select(UserBlock).where(
                UserBlock.blocker_id == blocker_id,
                UserBlock.blocked_id == blocked_id
            )
        )
        block = result.scalar_one_or_none()
        
        if not block:
            return False
        
        await db.delete(block)
        await db.commit()
        return True

    def _post_to_dict(self, post: Any, has_liked: bool, has_bookmarked: bool) -> Dict[str, Any]:
        """Convert post model to dictionary."""
        return {
            "id": str(post.id),
            "author_id": post.author_id,
            "author_name": post.author_name,
            "author_avatar": post.author_avatar,
            "author_level": post.author_level,
            "content": post.content,
            "media_urls": post.media_urls or [],
            "tags": post.tags or [],
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "has_liked": has_liked,
            "has_bookmarked": has_bookmarked,
            "post_type": post.post_type.value,
            "linked_course_id": post.linked_course_id,
            "linked_group_id": post.linked_group_id,
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat(),
            "is_edited": post.is_edited,
            "is_pinned": post.is_pinned,
            "visibility": post.visibility.value
        }

    def _comment_to_dict(self, comment: Any, has_liked: bool) -> Dict[str, Any]:
        """Convert comment model to dictionary."""
        return {
            "id": str(comment.id),
            "post_id": str(comment.post_id),
            "author_id": comment.author_id,
            "author_name": comment.author_name,
            "author_avatar": comment.author_avatar,
            "content": comment.content,
            "like_count": comment.like_count,
            "has_liked": has_liked,
            "parent_id": str(comment.parent_id) if comment.parent_id else None,
            "reply_count": comment.reply_count,
            "created_at": comment.created_at.isoformat(),
            "is_edited": comment.is_edited
        }

    # =========================================================================
    # PRIVATE LESSONS & BOOKINGS
    # =========================================================================

    async def create_private_lesson(
        self,
        db: AsyncSession,
        instructor_id: int,
        lesson_data: PrivateLessonCreate
    ) -> PrivateLesson:
        """Create a new private lesson offering."""
        lesson = PrivateLesson(
            title=lesson_data.title,
            description=lesson_data.description,
            subject=lesson_data.subject,
            price_per_hour=lesson_data.price_per_hour,
            currency=lesson_data.currency,
            duration_minutes=lesson_data.duration_minutes,
            location=lesson_data.location,
            latitude=lesson_data.latitude,
            longitude=lesson_data.longitude,
            instructor_id=instructor_id,
        )
        db.add(lesson)
        await db.commit()
        await db.refresh(lesson)
        return lesson

    async def get_private_lesson(
        self,
        db: AsyncSession,
        lesson_id: int
    ) -> Optional[PrivateLesson]:
        """Fetch a single private lesson by ID."""
        result = await db.execute(
            select(PrivateLesson).where(PrivateLesson.id == lesson_id)
        )
        return result.scalar_one_or_none()

    async def get_available_slots(
        self,
        db: AsyncSession,
        lesson_id: int,
        date: datetime
    ) -> List[BookingSlotRead]:
        """
        Generate 1-hour time slots for a lesson on a given date.
        Marks slots as unavailable if an existing booking overlaps.
        """
        # Fetch existing bookings for this lesson on this date
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        result = await db.execute(
            select(Booking).where(
                and_(
                    Booking.lesson_id == lesson_id,
                    Booking.slot_start >= day_start,
                    Booking.slot_start < day_end,
                    Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED])
                )
            )
        )
        existing_bookings = result.scalars().all()
        booked_hours = {b.slot_start.hour for b in existing_bookings}

        slots: List[BookingSlotRead] = []
        for hour in range(9, 18):  # 9am – 5pm (last slot starts at 5pm, ends 6pm)
            if hour == 12:  # Skip lunch
                continue
            slot_start = day_start.replace(hour=hour)
            slot_end = day_start.replace(hour=hour + 1)
            is_available = hour not in booked_hours

            slots.append(BookingSlotRead(
                id=f"{lesson_id}-{date.strftime('%Y%m%d')}-{hour:02d}00",
                start_time=slot_start,
                end_time=slot_end,
                is_available=is_available
            ))

        return slots

    async def create_booking(
        self,
        db: AsyncSession,
        student_id: int,
        booking_data: BookingCreate
    ) -> Booking:
        """
        Create a booking. Parses the slot_id to get the hour,
        then checks for conflicts before inserting.
        """
        lesson = await self.get_private_lesson(db, booking_data.lesson_id)
        if not lesson:
            raise ValueError("Lesson not found")

        # Parse slot_id format: "{lessonId}-{YYYYMMDD}-{HHMM}"
        parts = booking_data.slot_id.split("-")
        if len(parts) < 3:
            raise ValueError("Invalid slot ID format")

        date_str = parts[1]  # YYYYMMDD
        time_str = parts[2]  # HHMM
        slot_start = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M")
        slot_end = slot_start + timedelta(hours=1)

        # Check for conflicts
        conflict = await db.execute(
            select(Booking).where(
                and_(
                    Booking.lesson_id == booking_data.lesson_id,
                    Booking.slot_start == slot_start,
                    Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED])
                )
            )
        )
        if conflict.scalar_one_or_none():
            raise ValueError("This time slot is already booked")

        booking = Booking(
            lesson_id=booking_data.lesson_id,
            student_id=student_id,
            slot_start=slot_start,
            slot_end=slot_end,
            notes=booking_data.notes,
            status=BookingStatus.PENDING,
        )
        db.add(booking)
        await db.commit()
        await db.refresh(booking)
        return booking

    async def get_user_bookings(
        self,
        db: AsyncSession,
        user_id: int
    ) -> List[Booking]:
        """Get all bookings for a user, newest first."""
        result = await db.execute(
            select(Booking)
            .where(Booking.student_id == user_id)
            .order_by(desc(Booking.created_at))
        )
        return list(result.scalars().all())

    async def cancel_booking(
        self,
        db: AsyncSession,
        user_id: int,
        booking_id: int
    ) -> Booking:
        """Cancel a booking. Only the student who made it can cancel."""
        result = await db.execute(
            select(Booking).where(Booking.id == booking_id)
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise ValueError("Booking not found")
        if booking.student_id != user_id:
            raise PermissionError("You can only cancel your own bookings")
        if booking.status == BookingStatus.CANCELLED:
            raise ValueError("Booking is already cancelled")

        booking.status = BookingStatus.CANCELLED
        booking.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(booking)
        return booking

    async def _get_event_attendee_count(self, db: AsyncSession, event_id: int) -> int:
        """Get count of attendees for an event."""
        result = await db.execute(
            select(func.count(EventAttendance.id)).where(
                and_(
                    EventAttendance.event_id == event_id,
                    EventAttendance.status.in_([AttendanceStatus.GOING, AttendanceStatus.MAYBE])
                )
            )
        )
        return result.scalar() or 0

    async def _get_user_attendance(self, db: AsyncSession, event_id: int, user_id: int) -> Optional[EventAttendance]:
        """Get user's attendance record for an event."""
        result = await db.execute(
            select(EventAttendance).where(
                and_(
                    EventAttendance.event_id == event_id,
                    EventAttendance.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()

    # =========================================================================
    # REVIEWS
    # =========================================================================

    async def get_reviews(
        self,
        db: AsyncSession,
        target_type: str,
        target_id: str
    ) -> List[Review]:
        """Get all reviews for a specific target (lesson or institution)."""
        result = await db.execute(
            select(Review)
            .where(
                and_(
                    Review.target_type == target_type,
                    Review.target_id == target_id
                )
            )
            .order_by(desc(Review.created_at))
        )
        return list(result.scalars().all())

    async def submit_review(
        self,
        db: AsyncSession,
        author_id: int,
        review_data: ReviewCreate
    ) -> Review:
        """Submit a review. One review per user per target."""
        # Check for existing review by this user on this target
        existing = await db.execute(
            select(Review).where(
                and_(
                    Review.author_id == author_id,
                    Review.target_type == review_data.target_type,
                    Review.target_id == review_data.target_id
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("You have already reviewed this item")

        review = Review(
            author_id=author_id,
            target_type=review_data.target_type,
            target_id=review_data.target_id,
            rating=review_data.rating,
            text=review_data.text,
        )
        db.add(review)
        await db.commit()
        await db.refresh(review)
        return review

    async def get_review_stats(
        self,
        db: AsyncSession,
        target_type: str,
        target_id: str
    ) -> Dict[str, Any]:
        """Compute average rating, total count, and rating distribution."""
        result = await db.execute(
            select(
                func.avg(Review.rating).label("avg"),
                func.count(Review.id).label("cnt")
            ).where(
                and_(
                    Review.target_type == target_type,
                    Review.target_id == target_id
                )
            )
        )
        row = result.one()
        avg_rating = float(row.avg) if row.avg else 0.0
        total = int(row.cnt)

        # Rating distribution
        dist_result = await db.execute(
            select(
                Review.rating,
                func.count(Review.id).label("cnt")
            ).where(
                and_(
                    Review.target_type == target_type,
                    Review.target_id == target_id
                )
            ).group_by(Review.rating)
        )
        distribution = {str(i): 0 for i in range(1, 6)}
        for r_row in dist_result.all():
            distribution[str(r_row.rating)] = int(r_row.cnt)

        return {
            "average_rating": round(avg_rating, 1),
            "review_count": total,
            "rating_distribution": distribution
        }

