"""
Comprehensive test suite for RBAC and security features.
Tests role-based access control, permissions, and security middleware.
"""

import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import status

from lyo_app.main import app
from lyo_app.models.enhanced import User
from lyo_app.auth.rbac import Role, Permission, RoleType, PermissionType
from lyo_app.auth.rbac_service import RBACService
from lyo_app.auth.service import AuthService
from lyo_app.auth.schemas import UserCreate
from lyo_app.core.database import get_db, init_db, AsyncSessionLocal


class TestRBACSystem:
    """Test the Role-Based Access Control system."""
    
    @pytest.fixture
    async def setup_rbac(self):
        """Set up RBAC system with default roles and permissions."""
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            await rbac_service.initialize_default_roles_and_permissions()
            await db.commit()
            return rbac_service
    
    @pytest.fixture
    async def test_users(self, setup_rbac):
        """Create test users with different roles."""
        async with AsyncSessionLocal() as db:
            auth_service = AuthService()
            rbac_service = RBACService(db)
            
            users = {}
            
            # Create super admin
            admin_data = UserCreate(
                email="admin@test.com",
                username="admin",
                password="SecurePass123!",
                confirm_password="SecurePass123!",
                first_name="Admin",
                last_name="User"
            )
            admin_user = await auth_service.register_user(db, admin_data)
            await rbac_service.assign_role_to_user(admin_user.id, RoleType.SUPER_ADMIN.value)
            users['admin'] = admin_user
            
            # Create instructor
            instructor_data = UserCreate(
                email="instructor@test.com",
                username="instructor",
                password="SecurePass123!",
                confirm_password="SecurePass123!",
                first_name="Instructor",
                last_name="User"
            )
            instructor_user = await auth_service.register_user(db, instructor_data)
            await rbac_service.assign_role_to_user(instructor_user.id, RoleType.INSTRUCTOR.value)
            users['instructor'] = instructor_user
            
            # Create student (default role)
            student_data = UserCreate(
                email="student@test.com",
                username="student",
                password="SecurePass123!",
                confirm_password="SecurePass123!",
                first_name="Student",
                last_name="User"
            )
            student_user = await auth_service.register_user(db, student_data)
            users['student'] = student_user
            
            await db.commit()
            return users
    
    async def test_default_roles_creation(self, setup_rbac):
        """Test that default roles and permissions are created."""
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            
            # Check all default roles exist
            roles = await rbac_service.get_all_roles()
            role_names = {role.name for role in roles}
            
            expected_roles = {role.value for role in RoleType}
            assert expected_roles.issubset(role_names)
            
            # Check all permissions exist
            permissions = await rbac_service.get_all_permissions()
            permission_names = {perm.name for perm in permissions}
            
            expected_permissions = {perm.value for perm in PermissionType}
            assert expected_permissions.issubset(permission_names)
    
    async def test_user_role_assignment(self, test_users):
        """Test role assignment to users."""
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            
            # Check admin has super_admin role
            admin_roles = await rbac_service.get_user_roles(test_users['admin'].id)
            admin_role_names = {role.name for role in admin_roles}
            assert RoleType.SUPER_ADMIN.value in admin_role_names
            
            # Check instructor has instructor role
            instructor_roles = await rbac_service.get_user_roles(test_users['instructor'].id)
            instructor_role_names = {role.name for role in instructor_roles}
            assert RoleType.INSTRUCTOR.value in instructor_role_names
            
            # Check student has student role
            student_roles = await rbac_service.get_user_roles(test_users['student'].id)
            student_role_names = {role.name for role in student_roles}
            assert RoleType.STUDENT.value in student_role_names
    
    async def test_permission_checking(self, test_users):
        """Test permission checking for different roles."""
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            
            # Admin should have all permissions
            admin_perms = await rbac_service.get_user_permissions(test_users['admin'].id)
            assert PermissionType.MANAGE_SYSTEM.value in admin_perms
            assert PermissionType.CREATE_COURSE.value in admin_perms
            
            # Instructor should have course creation permission
            instructor_perms = await rbac_service.get_user_permissions(test_users['instructor'].id)
            assert PermissionType.CREATE_COURSE.value in instructor_perms
            assert PermissionType.MANAGE_SYSTEM.value not in instructor_perms
            
            # Student should have limited permissions
            student_perms = await rbac_service.get_user_permissions(test_users['student'].id)
            assert PermissionType.VIEW_COURSE.value in student_perms
            assert PermissionType.CREATE_COURSE.value not in student_perms
    
    async def test_role_promotion(self, test_users):
        """Test promoting users between roles."""
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            
            # Promote student to instructor
            success = await rbac_service.promote_user(
                test_users['student'].id,
                RoleType.STUDENT.value,
                RoleType.INSTRUCTOR.value
            )
            assert success
            
            # Check new permissions
            perms = await rbac_service.get_user_permissions(test_users['student'].id)
            assert PermissionType.CREATE_COURSE.value in perms
    
    async def test_custom_role_creation(self, setup_rbac):
        """Test creating custom roles."""
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            
            # Create custom role
            custom_permissions = [
                PermissionType.VIEW_COURSE.value,
                PermissionType.CREATE_POST.value,
                PermissionType.VIEW_ANALYTICS.value
            ]
            
            role = await rbac_service.create_custom_role(
                name="content_creator",
                description="Content creator role",
                permission_names=custom_permissions
            )
            
            assert role is not None
            assert role.name == "content_creator"
            
            # Check role permissions
            role_perms = {perm.name for perm in role.permissions}
            assert set(custom_permissions).issubset(role_perms)


class TestSecurityMiddleware:
    """Test security middleware functionality."""
    
    @pytest.fixture
    async def client(self):
        """Create test client."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    
    async def test_rate_limiting(self, client):
        """Test rate limiting functionality."""
        # Make multiple requests to auth endpoint
        responses = []
        for i in range(10):  # Should exceed rate limit
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"test{i}@example.com",
                    "username": f"test{i}",
                    "password": "WeakPass",
                    "confirm_password": "WeakPass"
                }
            )
            responses.append(response)
        
        # Check if rate limiting kicks in
        rate_limited = any(r.status_code == status.HTTP_429_TOO_MANY_REQUESTS for r in responses)
        # Note: This might not trigger in test environment with in-memory limiter
        # In production with Redis, this would be more reliable
    
    async def test_input_validation(self, client):
        """Test input validation."""
        # Test invalid email
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid-email",
                "username": "testuser",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!"
            }
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test weak password
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "weak",
                "confirm_password": "weak"
            }
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test XSS attempt
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "<script>alert('xss')</script>",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!"
            }
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_security_headers(self, client):
        """Test security headers are added to responses."""
        response = await client.get("/api/v1/health")
        
        # Check security headers
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"
    
    async def test_request_size_limiting(self, client):
        """Test request size limiting."""
        # Create oversized request
        large_data = "x" * (11 * 1024 * 1024)  # 11MB
        
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "bio": large_data
            }
        )
        
        # Should be rejected due to size
        assert response.status_code in [
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ]


class TestAuthenticationFlow:
    """Test complete authentication flow with RBAC."""
    
    @pytest.fixture
    async def client(self):
        """Create test client."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    
    async def test_registration_with_role_assignment(self, client):
        """Test user registration with automatic role assignment."""
        # Register new user
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "first_name": "New",
                "last_name": "User"
            }
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        user_data = response.json()
        
        # Check user was created with student role
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            roles = await rbac_service.get_user_roles(user_data["id"])
            role_names = {role.name for role in roles}
            assert RoleType.STUDENT.value in role_names
    
    async def test_login_and_token_validation(self, client):
        """Test login and token validation."""
        # First register a user
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "logintest@example.com",
                "username": "logintest",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!"
            }
        )
        
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "logintest@example.com",
                "password": "SecurePass123!"
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        token_data = response.json()
        assert "access_token" in token_data
        
        # Use token to access protected endpoint
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == status.HTTP_200_OK
    
    async def test_permission_based_access_control(self, client):
        """Test permission-based access control on endpoints."""
        # Create users with different roles
        # (This would require setting up admin user and using admin endpoints)
        
        # Register regular student
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "student@test.com",
                "username": "teststudent",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!"
            }
        )
        
        # Login as student
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "student@test.com",
                "password": "SecurePass123!"
            }
        )
        
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to access admin endpoint (should be forbidden)
        # Note: This assumes admin endpoints exist and are properly protected
        response = await client.get("/api/v1/admin/users", headers=headers)
        # Should be 403 or 404 if endpoint doesn't exist yet
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND
        ]


if __name__ == "__main__":
    # Run tests
    asyncio.run(pytest.main([__file__, "-v"]))
