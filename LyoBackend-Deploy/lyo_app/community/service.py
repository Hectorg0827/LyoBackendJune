"""
Community service implementation.
Handles study groups, community events, and collaborative learning operations.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.community.models import (
    StudyGroup, GroupMembership, CommunityEvent, EventAttendance,
    StudyGroupStatus, StudyGroupPrivacy, MembershipRole,
    EventStatus, AttendanceStatus
)
from lyo_app.community.schemas import (
    StudyGroupCreate, StudyGroupUpdate,
    GroupMembershipCreate, GroupMembershipUpdate,
    CommunityEventCreate, CommunityEventUpdate,
    EventAttendanceCreate, EventAttendanceUpdate
)


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
        page: int = 1, 
        per_page: int = 20
    ) -> Dict[str, Any]:
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
        offset = (page - 1) * per_page
        
        # Build query
        query = select(StudyGroup)
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
            .offset(offset)
            .limit(per_page)
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
            }
            groups_data.append(group_data)
        
        return {
            "groups": groups_data,
            "total": total or 0,
            "page": page,
            "per_page": per_page,
            "has_next": total > page * per_page,
        }

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
        page: int = 1, 
        per_page: int = 20
    ) -> Dict[str, Any]:
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
        offset = (page - 1) * per_page
        
        # Build query
        query = select(CommunityEvent)
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
            .offset(offset)
            .limit(per_page)
        )
        events = result.scalars().all()
        
        # Get total count
        count_query = select(func.count(CommunityEvent.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        count_result = await db.execute(count_query)
        total = count_result.scalar()
        
        # Add attendee count and user context
        events_data = []
        for event in events:
            attendee_count = await self._get_event_attendee_count(db, event.id)
            user_attendance = None
            
            if user_id:
                user_attendance = await self._get_user_attendance(db, event.id, user_id)
            
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
                "attendee_count": attendee_count,
                "user_attendance_status": user_attendance.status if user_attendance else None,
                "is_full": event.max_attendees and attendee_count >= event.max_attendees,
            }
            events_data.append(event_data)
        
        return {
            "events": events_data,
            "total": total or 0,
            "page": page,
            "per_page": per_page,
            "has_next": total > page * per_page,
        }

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
