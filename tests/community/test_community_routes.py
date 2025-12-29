"""
Integration tests for community API routes.
Tests the full HTTP API endpoints for study groups and community events.
"""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.community.models import StudyGroupPrivacy, EventType, AttendanceStatus
from lyo_app.models.enhanced import User


class TestStudyGroupRoutes:
    """Test study group API endpoints."""
    
    async def test_create_study_group(self, client: AsyncClient, auth_headers: dict):
        """Test creating a new study group."""
        group_data = {
            "name": "Python Study Group",
            "description": "Learning Python together",
            "privacy": "public",
            "max_members": 10,
            "requires_approval": False
        }
        
        response = await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == group_data["name"]
        assert data["description"] == group_data["description"]
        assert data["privacy"] == group_data["privacy"]
        assert data["max_members"] == group_data["max_members"]
        assert data["requires_approval"] == group_data["requires_approval"]
        assert data["status"] == "active"
        assert "id" in data
        assert "creator_id" in data
        assert "created_at" in data
    
    async def test_create_study_group_validation_error(self, client: AsyncClient, auth_headers: dict):
        """Test study group creation with invalid data."""
        group_data = {
            "name": "",  # Invalid: empty name
            "privacy": "public"
        }
        
        response = await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422
    
    async def test_list_study_groups(self, client: AsyncClient, auth_headers: dict):
        """Test listing study groups."""
        # Create a study group first
        group_data = {
            "name": "Test Study Group",
            "privacy": "public"
        }
        await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        
        response = await client.get(
            "/api/v1/community/study-groups",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["name"] == group_data["name"]
    
    async def test_list_study_groups_with_filters(self, client: AsyncClient, auth_headers: dict):
        """Test listing study groups with filters."""
        response = await client.get(
            "/api/v1/community/study-groups?privacy=public&limit=5",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5
    
    async def test_get_study_group(self, client: AsyncClient, auth_headers: dict):
        """Test getting a specific study group."""
        # Create a study group first
        group_data = {
            "name": "Get Test Group",
            "description": "Test description",
            "privacy": "public"
        }
        create_response = await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        group_id = create_response.json()["id"]
        
        response = await client.get(
            f"/api/v1/community/study-groups/{group_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == group_id
        assert data["name"] == group_data["name"]
        assert data["description"] == group_data["description"]
    
    async def test_get_nonexistent_study_group(self, client: AsyncClient, auth_headers: dict):
        """Test getting a non-existent study group."""
        response = await client.get(
            "/api/v1/community/study-groups/99999",
            headers=auth_headers
        )
        
        assert response.status_code == 404
    
    async def test_update_study_group(self, client: AsyncClient, auth_headers: dict):
        """Test updating a study group."""
        # Create a study group first
        group_data = {
            "name": "Original Name",
            "privacy": "public"
        }
        create_response = await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        group_id = create_response.json()["id"]
        
        # Update the group
        update_data = {
            "name": "Updated Name",
            "description": "Updated description"
        }
        response = await client.put(
            f"/api/v1/community/study-groups/{group_id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["description"] == update_data["description"]
    
    async def test_delete_study_group(self, client: AsyncClient, auth_headers: dict):
        """Test deleting a study group."""
        # Create a study group first
        group_data = {
            "name": "Delete Test Group",
            "privacy": "public"
        }
        create_response = await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        group_id = create_response.json()["id"]
        
        # Delete the group
        response = await client.delete(
            f"/api/v1/community/study-groups/{group_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 204
        
        # Verify it's deleted
        get_response = await client.get(
            f"/api/v1/community/study-groups/{group_id}",
            headers=auth_headers
        )
        assert get_response.status_code == 404


class TestGroupMembershipRoutes:
    """Test group membership API endpoints."""
    
    async def test_join_study_group(self, client: AsyncClient, auth_headers: dict):
        """Test joining a study group."""
        # Create a study group first
        group_data = {
            "name": "Join Test Group",
            "privacy": "public"
        }
        create_response = await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        group_id = create_response.json()["id"]
        
        # Join the group
        response = await client.post(
            f"/api/v1/community/study-groups/{group_id}/join",
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["study_group_id"] == group_id
        assert data["role"] == "member"
        assert data["is_approved"] is True
    
    async def test_leave_study_group(self, client: AsyncClient, auth_headers: dict):
        """Test leaving a study group."""
        # Create and join a study group first
        group_data = {
            "name": "Leave Test Group",
            "privacy": "public"
        }
        create_response = await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        group_id = create_response.json()["id"]
        
        await client.post(
            f"/api/v1/community/study-groups/{group_id}/join",
            headers=auth_headers
        )
        
        # Leave the group
        response = await client.delete(
            f"/api/v1/community/study-groups/{group_id}/leave",
            headers=auth_headers
        )
        
        assert response.status_code == 204
    
    async def test_get_group_members(self, client: AsyncClient, auth_headers: dict):
        """Test getting group members."""
        # Create and join a study group first
        group_data = {
            "name": "Members Test Group",
            "privacy": "public"
        }
        create_response = await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        group_id = create_response.json()["id"]
        
        await client.post(
            f"/api/v1/community/study-groups/{group_id}/join",
            headers=auth_headers
        )
        
        # Get group members
        response = await client.get(
            f"/api/v1/community/study-groups/{group_id}/members",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


class TestCommunityEventRoutes:
    """Test community event API endpoints."""
    
    async def test_create_community_event(self, client: AsyncClient, auth_headers: dict):
        """Test creating a new community event."""
        event_data = {
            "title": "Python Workshop",
            "description": "Learn Python basics",
            "event_type": "workshop",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat(),
            "location": "Online",
            "max_attendees": 20
        }
        
        response = await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == event_data["title"]
        assert data["description"] == event_data["description"]
        assert data["event_type"] == event_data["event_type"]
        assert data["location"] == event_data["location"]
        assert data["max_attendees"] == event_data["max_attendees"]
        assert "id" in data
        assert "organizer_id" in data
    
    async def test_create_event_validation_error(self, client: AsyncClient, auth_headers: dict):
        """Test event creation with invalid data."""
        event_data = {
            "title": "",  # Invalid: empty title
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat()
        }
        
        response = await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422
    
    async def test_list_community_events(self, client: AsyncClient, auth_headers: dict):
        """Test listing community events."""
        # Create an event first
        event_data = {
            "title": "List Test Event",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat()
        }
        await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        
        response = await client.get(
            "/api/v1/community/events",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
    
    async def test_get_community_event(self, client: AsyncClient, auth_headers: dict):
        """Test getting a specific community event."""
        # Create an event first
        event_data = {
            "title": "Get Test Event",
            "description": "Test description",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat()
        }
        create_response = await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        event_id = create_response.json()["id"]
        
        response = await client.get(
            f"/api/v1/community/events/{event_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == event_id
        assert data["title"] == event_data["title"]
        assert data["description"] == event_data["description"]
    
    async def test_update_community_event(self, client: AsyncClient, auth_headers: dict):
        """Test updating a community event."""
        # Create an event first
        event_data = {
            "title": "Original Event",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat()
        }
        create_response = await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        event_id = create_response.json()["id"]
        
        # Update the event
        update_data = {
            "title": "Updated Event",
            "description": "Updated description"
        }
        response = await client.put(
            f"/api/v1/community/events/{event_id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == update_data["title"]
        assert data["description"] == update_data["description"]
    
    async def test_delete_community_event(self, client: AsyncClient, auth_headers: dict):
        """Test deleting a community event."""
        # Create an event first
        event_data = {
            "title": "Delete Test Event",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat()
        }
        create_response = await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        event_id = create_response.json()["id"]
        
        # Delete the event
        response = await client.delete(
            f"/api/v1/community/events/{event_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 204


class TestEventAttendanceRoutes:
    """Test event attendance API endpoints."""
    
    async def test_register_event_attendance(self, client: AsyncClient, auth_headers: dict):
        """Test registering for an event."""
        # Create an event first
        event_data = {
            "title": "Attendance Test Event",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat()
        }
        create_response = await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        event_id = create_response.json()["id"]
        
        # Register attendance
        response = await client.post(
            f"/api/v1/community/events/{event_id}/attend",
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["community_event_id"] == event_id
        assert data["status"] == "registered"
    
    async def test_update_event_attendance(self, client: AsyncClient, auth_headers: dict):
        """Test updating attendance status."""
        # Create an event and register first
        event_data = {
            "title": "Update Attendance Test",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat()
        }
        create_response = await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        event_id = create_response.json()["id"]
        
        await client.post(
            f"/api/v1/community/events/{event_id}/attend",
            headers=auth_headers
        )
        
        # Update attendance status
        response = await client.put(
            f"/api/v1/community/events/{event_id}/attendance?attendance_status=attended",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "attended"
    
    async def test_cancel_event_attendance(self, client: AsyncClient, auth_headers: dict):
        """Test cancelling event attendance."""
        # Create an event and register first
        event_data = {
            "title": "Cancel Attendance Test",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat()
        }
        create_response = await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        event_id = create_response.json()["id"]
        
        await client.post(
            f"/api/v1/community/events/{event_id}/attend",
            headers=auth_headers
        )
        
        # Cancel attendance
        response = await client.delete(
            f"/api/v1/community/events/{event_id}/attend",
            headers=auth_headers
        )
        
        assert response.status_code == 204


class TestUserSpecificRoutes:
    """Test user-specific community endpoints."""
    
    async def test_get_my_study_groups(self, client: AsyncClient, auth_headers: dict):
        """Test getting user's study groups."""
        # Create and join a study group first
        group_data = {
            "name": "My Groups Test",
            "privacy": "public"
        }
        create_response = await client.post(
            "/api/v1/community/study-groups",
            json=group_data,
            headers=auth_headers
        )
        group_id = create_response.json()["id"]
        
        await client.post(
            f"/api/v1/community/study-groups/{group_id}/join",
            headers=auth_headers
        )
        
        # Get user's groups
        response = await client.get(
            "/api/v1/community/my-groups",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
    
    async def test_get_my_community_events(self, client: AsyncClient, auth_headers: dict):
        """Test getting user's community events."""
        # Create and register for an event first
        event_data = {
            "title": "My Events Test",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat()
        }
        create_response = await client.post(
            "/api/v1/community/events",
            json=event_data,
            headers=auth_headers
        )
        event_id = create_response.json()["id"]
        
        await client.post(
            f"/api/v1/community/events/{event_id}/attend",
            headers=auth_headers
        )
        
        # Get user's events
        response = await client.get(
            "/api/v1/community/my-events",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
    
    async def test_get_community_stats(self, client: AsyncClient, auth_headers: dict):
        """Test getting user's community statistics."""
        response = await client.get(
            "/api/v1/community/stats",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Stats structure will depend on CommunityService implementation
        assert "groups_created" in data or "groups_joined" in data


class TestAuthenticationAndAuthorization:
    """Test authentication and authorization for community endpoints."""
    
    async def test_unauthorized_access(self, client: AsyncClient):
        """Test accessing endpoints without authentication."""
        response = await client.get("/api/v1/community/study-groups")
        assert response.status_code == 401
        
        response = await client.post(
            "/api/v1/community/study-groups",
            json={"name": "Test Group", "privacy": "public"}
        )
        assert response.status_code == 401
    
    async def test_create_study_group_with_invalid_token(self, client: AsyncClient):
        """Test creating study group with invalid token."""
        response = await client.post(
            "/api/v1/community/study-groups",
            json={"name": "Test Group", "privacy": "public"},
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401
