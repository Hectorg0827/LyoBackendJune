"""
Unit tests for community service.
Tests study group and community event operations with TDD approach.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.models import User
from lyo_app.learning.models import Course
from lyo_app.community.models import (
    StudyGroup, GroupMembership, CommunityEvent, EventAttendance,
    StudyGroupStatus, StudyGroupPrivacy, MembershipRole,
    EventType, EventStatus, AttendanceStatus
)
from lyo_app.community.schemas import (
    StudyGroupCreate, StudyGroupUpdate,
    GroupMembershipCreate, GroupMembershipUpdate,
    CommunityEventCreate, CommunityEventUpdate,
    EventAttendanceCreate, EventAttendanceUpdate
)
from lyo_app.community.service import CommunityService


class TestCommunityService:
    """Test class for community service operations."""

    @pytest.fixture
    def community_service(self):
        """Community service instance."""
        return CommunityService()

    @pytest.fixture
    async def test_user(self, db_session: AsyncSession) -> User:
        """Create a test user."""
        user = User(
            email="testuser@example.com",
            username="testuser",
            hashed_password="hashedpassword",
            first_name="Test",
            last_name="User",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    @pytest.fixture
    async def test_user2(self, db_session: AsyncSession) -> User:
        """Create a second test user."""
        user = User(
            email="testuser2@example.com",
            username="testuser2",
            hashed_password="hashedpassword",
            first_name="Test",
            last_name="User2",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    @pytest.fixture
    async def test_course(self, db_session: AsyncSession, test_user: User) -> Course:
        """Create a test course."""
        course = Course(
            title="Test Course",
            description="A test course",
            instructor_id=test_user.id,
            is_published=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(course)
        await db_session.commit()
        await db_session.refresh(course)
        return course

    # Study Group Tests
    async def test_create_study_group(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_course: Course):
        """Test creating a new study group."""
        group_data = StudyGroupCreate(
            name="Python Study Group",
            description="A group for learning Python",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=10,
            requires_approval=False,
            course_id=test_course.id
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        assert group is not None
        assert group.name == "Python Study Group"
        assert group.description == "A group for learning Python"
        assert group.privacy == StudyGroupPrivacy.PUBLIC
        assert group.max_members == 10
        assert group.requires_approval is False
        assert group.course_id == test_course.id
        assert group.creator_id == test_user.id
        assert group.status == StudyGroupStatus.ACTIVE
        
        # Verify creator is automatically added as owner
        member_count = await community_service._get_group_member_count(db_session, group.id)
        assert member_count == 1
        
        creator_membership = await community_service._get_user_membership(db_session, group.id, test_user.id)
        assert creator_membership is not None
        assert creator_membership.role == MembershipRole.OWNER

    async def test_create_study_group_minimal(self, community_service: CommunityService, db_session: AsyncSession, test_user: User):
        """Test creating a study group with minimal data."""
        group_data = StudyGroupCreate(
            name="Minimal Group",
            description=None,
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        assert group is not None
        assert group.name == "Minimal Group"
        assert group.description is None
        assert group.max_members is None
        assert group.course_id is None

    async def test_get_study_group_by_id(self, community_service: CommunityService, db_session: AsyncSession, test_user: User):
        """Test retrieving a study group by ID."""
        # Create a group first
        group_data = StudyGroupCreate(
            name="Test Group",
            description="Test description",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=5,
            requires_approval=False,
            course_id=None
        )
        
        created_group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Retrieve the group
        retrieved_group = await community_service.get_study_group_by_id(db_session, created_group.id)
        
        assert retrieved_group is not None
        assert retrieved_group.id == created_group.id
        assert retrieved_group.name == "Test Group"

    async def test_get_study_group_nonexistent(self, community_service: CommunityService, db_session: AsyncSession):
        """Test retrieving a non-existent study group."""
        group = await community_service.get_study_group_by_id(db_session, 99999)
        assert group is None

    async def test_get_private_group_access_control(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test access control for private study groups."""
        # Create a private group
        group_data = StudyGroupCreate(
            name="Private Group",
            description="A private group",
            privacy=StudyGroupPrivacy.PRIVATE,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Creator should be able to access
        retrieved_group = await community_service.get_study_group_by_id(db_session, group.id, test_user.id)
        assert retrieved_group is not None
        
        # Non-member should not be able to access
        retrieved_group = await community_service.get_study_group_by_id(db_session, group.id, test_user2.id)
        assert retrieved_group is None

    async def test_update_study_group(self, community_service: CommunityService, db_session: AsyncSession, test_user: User):
        """Test updating a study group."""
        # Create a group first
        group_data = StudyGroupCreate(
            name="Original Name",
            description="Original description",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=5,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Update the group
        update_data = StudyGroupUpdate(
            name="Updated Name",
            description="Updated description",
            max_members=10,
            requires_approval=True
        )
        
        updated_group = await community_service.update_study_group(db_session, group.id, test_user.id, update_data)
        
        assert updated_group is not None
        assert updated_group.name == "Updated Name"
        assert updated_group.description == "Updated description"
        assert updated_group.max_members == 10
        assert updated_group.requires_approval is True

    async def test_update_study_group_unauthorized(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test updating a study group without permissions."""
        # Create a group
        group_data = StudyGroupCreate(
            name="Test Group",
            description="Test description",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Try to update as non-member
        update_data = StudyGroupUpdate(name="Hacked Name")
        
        with pytest.raises(PermissionError, match="Insufficient permissions"):
            await community_service.update_study_group(db_session, group.id, test_user2.id, update_data)

    async def test_delete_study_group(self, community_service: CommunityService, db_session: AsyncSession, test_user: User):
        """Test deleting a study group."""
        # Create a group first
        group_data = StudyGroupCreate(
            name="Group to Delete",
            description="This will be deleted",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        group_id = group.id
        
        # Delete the group
        success = await community_service.delete_study_group(db_session, group_id, test_user.id)
        assert success is True
        
        # Verify group is deleted
        deleted_group = await community_service.get_study_group_by_id(db_session, group_id)
        assert deleted_group is None

    async def test_delete_study_group_unauthorized(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test deleting a study group without owner permissions."""
        # Create a group
        group_data = StudyGroupCreate(
            name="Protected Group",
            description="Cannot be deleted by non-owner",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Try to delete as non-owner
        with pytest.raises(PermissionError, match="Only group owners can delete"):
            await community_service.delete_study_group(db_session, group.id, test_user2.id)

    async def test_join_study_group(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test joining a study group."""
        # Create a group
        group_data = StudyGroupCreate(
            name="Open Group",
            description="Anyone can join",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Join the group
        membership_data = GroupMembershipCreate(study_group_id=group.id)
        membership = await community_service.join_study_group(db_session, test_user2.id, membership_data)
        
        assert membership is not None
        assert membership.user_id == test_user2.id
        assert membership.study_group_id == group.id
        assert membership.role == MembershipRole.MEMBER
        assert membership.is_approved is True
        
        # Verify member count increased
        member_count = await community_service._get_group_member_count(db_session, group.id)
        assert member_count == 2

    async def test_join_study_group_with_approval(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test joining a study group that requires approval."""
        # Create a group requiring approval
        group_data = StudyGroupCreate(
            name="Approval Required Group",
            description="Membership requires approval",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=True,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Join the group
        membership_data = GroupMembershipCreate(study_group_id=group.id)
        membership = await community_service.join_study_group(db_session, test_user2.id, membership_data)
        
        assert membership is not None
        assert membership.is_approved is False
        assert membership.approved_at is None
        
        # Member count should not increase yet
        member_count = await community_service._get_group_member_count(db_session, group.id)
        assert member_count == 1  # Only the creator

    async def test_join_full_study_group(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test joining a study group that is at capacity."""
        # Create a group with max 1 member (only creator)
        group_data = StudyGroupCreate(
            name="Full Group",
            description="This group is full",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=1,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Try to join (should fail because creator already fills the capacity)
        membership_data = GroupMembershipCreate(study_group_id=group.id)
        
        with pytest.raises(ValueError, match="Study group is full"):
            await community_service.join_study_group(db_session, test_user2.id, membership_data)

    async def test_join_private_study_group(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test joining a private study group (should fail)."""
        # Create a private group
        group_data = StudyGroupCreate(
            name="Private Group",
            description="This group is private",
            privacy=StudyGroupPrivacy.PRIVATE,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Try to join (should fail)
        membership_data = GroupMembershipCreate(study_group_id=group.id)
        
        with pytest.raises(ValueError, match="Cannot join private group"):
            await community_service.join_study_group(db_session, test_user2.id, membership_data)

    async def test_join_study_group_twice(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test joining a study group twice (should fail)."""
        # Create a group
        group_data = StudyGroupCreate(
            name="Test Group",
            description="Test description",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Join the group
        membership_data = GroupMembershipCreate(study_group_id=group.id)
        await community_service.join_study_group(db_session, test_user2.id, membership_data)
        
        # Try to join again (should fail)
        with pytest.raises(ValueError, match="Already a member"):
            await community_service.join_study_group(db_session, test_user2.id, membership_data)

    async def test_leave_study_group(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test leaving a study group."""
        # Create a group and join it
        group_data = StudyGroupCreate(
            name="Test Group",
            description="Test description",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        membership_data = GroupMembershipCreate(study_group_id=group.id)
        await community_service.join_study_group(db_session, test_user2.id, membership_data)
        
        # Leave the group
        success = await community_service.leave_study_group(db_session, test_user2.id, group.id)
        assert success is True
        
        # Verify membership is removed
        user_membership = await community_service._get_user_membership(db_session, group.id, test_user2.id)
        assert user_membership is None
        
        # Member count should decrease
        member_count = await community_service._get_group_member_count(db_session, group.id)
        assert member_count == 1  # Only creator

    async def test_leave_study_group_as_owner(self, community_service: CommunityService, db_session: AsyncSession, test_user: User):
        """Test owner trying to leave study group (should fail)."""
        # Create a group
        group_data = StudyGroupCreate(
            name="Test Group",
            description="Test description",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Try to leave as owner (should fail)
        with pytest.raises(ValueError, match="Group owners cannot leave"):
            await community_service.leave_study_group(db_session, test_user.id, group.id)

    async def test_leave_study_group_not_member(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test leaving a study group when not a member."""
        # Create a group
        group_data = StudyGroupCreate(
            name="Test Group",
            description="Test description",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Try to leave without being a member
        success = await community_service.leave_study_group(db_session, test_user2.id, group.id)
        assert success is False

    async def test_get_study_groups(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_course: Course):
        """Test retrieving study groups with pagination."""
        # Create multiple groups
        for i in range(3):
            group_data = StudyGroupCreate(
                name=f"Group {i+1}",
                description=f"Description for group {i+1}",
                privacy=StudyGroupPrivacy.PUBLIC,
                max_members=None,
                requires_approval=False,
                course_id=test_course.id if i == 0 else None
            )
            await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Get all groups
        result = await community_service.get_study_groups(db_session, page=1, per_page=10)
        
        assert "groups" in result
        assert "total" in result
        assert "page" in result
        assert "per_page" in result
        assert "has_next" in result
        
        assert len(result["groups"]) == 3
        assert result["total"] == 3
        assert result["page"] == 1
        assert result["per_page"] == 10
        assert result["has_next"] is False
        
        # Test filtering by course
        result = await community_service.get_study_groups(db_session, course_id=test_course.id, page=1, per_page=10)
        assert len(result["groups"]) == 1
        assert result["groups"][0]["course_id"] == test_course.id

    # Community Event Tests
    async def test_create_community_event(self, community_service: CommunityService, db_session: AsyncSession, test_user: User):
        """Test creating a community event."""
        start_time = datetime.utcnow() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        event_data = CommunityEventCreate(
            title="Python Workshop",
            description="Learn Python programming",
            event_type=EventType.WORKSHOP,
            location="Online",
            meeting_url="https://meet.example.com/python",
            max_attendees=50,
            start_time=start_time,
            end_time=end_time,
            timezone="UTC",
            study_group_id=None,
            course_id=None,
            lesson_id=None
        )
        
        event = await community_service.create_community_event(db_session, test_user.id, event_data)
        
        assert event is not None
        assert event.title == "Python Workshop"
        assert event.description == "Learn Python programming"
        assert event.event_type == EventType.WORKSHOP
        assert event.location == "Online"
        assert event.meeting_url == "https://meet.example.com/python"
        assert event.max_attendees == 50
        assert event.start_time == start_time
        assert event.end_time == end_time
        assert event.organizer_id == test_user.id
        assert event.status == EventStatus.SCHEDULED

    async def test_create_event_invalid_dates(self, community_service: CommunityService, db_session: AsyncSession, test_user: User):
        """Test creating an event with invalid dates."""
        start_time = datetime.utcnow() + timedelta(days=1)
        end_time = start_time - timedelta(hours=1)  # End before start
        
        event_data = CommunityEventCreate(
            title="Invalid Event",
            description="This should fail",
            event_type=EventType.STUDY_SESSION,
            location=None,
            meeting_url=None,
            max_attendees=None,
            start_time=start_time,
            end_time=end_time,
            timezone="UTC",
            study_group_id=None,
            course_id=None,
            lesson_id=None
        )
        
        with pytest.raises(ValueError, match="End time must be after start time"):
            await community_service.create_community_event(db_session, test_user.id, event_data)

    async def test_create_group_event_with_permissions(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test creating an event for a study group with proper permissions."""
        # Create a group
        group_data = StudyGroupCreate(
            name="Study Group",
            description="Test group",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Create event for the group as owner
        start_time = datetime.utcnow() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        event_data = CommunityEventCreate(
            title="Group Study Session",
            description="Study session for the group",
            event_type=EventType.STUDY_SESSION,
            location=None,
            meeting_url=None,
            max_attendees=None,
            start_time=start_time,
            end_time=end_time,
            timezone="UTC",
            study_group_id=group.id,
            course_id=None,
            lesson_id=None
        )
        
        event = await community_service.create_community_event(db_session, test_user.id, event_data)
        assert event is not None
        assert event.study_group_id == group.id

    async def test_create_group_event_without_permissions(self, community_service: CommunityService, db_session: AsyncSession, test_user: User, test_user2: User):
        """Test creating an event for a study group without permissions."""
        # Create a group
        group_data = StudyGroupCreate(
            name="Study Group",
            description="Test group",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=None,
            requires_approval=False,
            course_id=None
        )
        
        group = await community_service.create_study_group(db_session, test_user.id, group_data)
        
        # Try to create event as non-member
        start_time = datetime.utcnow() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        event_data = CommunityEventCreate(
            title="Unauthorized Event",
            description="This should fail",
            event_type=EventType.STUDY_SESSION,
            location=None,
            meeting_url=None,
            max_attendees=None,
            start_time=start_time,
            end_time=end_time,
            timezone="UTC",
            study_group_id=group.id,
            course_id=None,
            lesson_id=None
        )
        
        with pytest.raises(PermissionError, match="Insufficient permissions"):
            await community_service.create_community_event(db_session, test_user2.id, event_data)
