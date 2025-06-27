"""
Admin dashboard routes for managing users, roles, and permissions.
Provides administrative endpoints for RBAC management.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.models import User
from lyo_app.auth.rbac import Role, Permission, RoleType, PermissionType
from lyo_app.auth.rbac_service import RBACService
from lyo_app.auth.service import AuthService
from lyo_app.auth.security import get_current_user
from lyo_app.auth.security_middleware import PermissionChecker
from lyo_app.core.database import get_db
from pydantic import BaseModel


# Pydantic schemas for admin operations
class RoleCreate(BaseModel):
    name: str
    description: str
    permission_names: List[str]


class RoleUpdate(BaseModel):
    description: Optional[str] = None
    permission_names: Optional[List[str]] = None


class UserRoleAssignment(BaseModel):
    user_id: int
    role_names: List[str]


class BulkRoleAssignment(BaseModel):
    user_ids: List[int]
    role_names: List[str]


class UserPromotion(BaseModel):
    user_id: int
    from_role: str
    to_role: str


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    permissions: List[str]
    user_count: int

    class Config:
        from_attributes = True


class PermissionResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]

    class Config:
        from_attributes = True


class UserSummary(BaseModel):
    id: int
    username: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    is_active: bool
    is_verified: bool
    roles: List[str]
    created_at: str

    class Config:
        from_attributes = True


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[],  # We'll add permission checks to individual endpoints
)


# Remove the require_admin_permission function and update all endpoints to use inline permission checks

# Replace all occurrences of `lambda: require_admin_permission(PermissionType.X)` with just `get_current_user`
# and add permission checks inside each function


# Role Management Endpoints
@router.get("/roles", response_model=List[RoleResponse])
async def get_all_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all roles with their permissions and user counts."""
    # Check permission
    if not await PermissionChecker.check_permission(current_user, PermissionType.MANAGE_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {PermissionType.MANAGE_ROLES.value}"
        )
    
    rbac_service = RBACService(db)
    roles = await rbac_service.get_all_roles()
    
    role_responses = []
    for role in roles:
        # Get user count for this role
        role_users = await rbac_service.get_role_users(role.name)
        user_count = len(role_users)
        
        role_response = RoleResponse(
            id=role.id,
            name=role.name,
            description=role.description,
            is_active=role.is_active,
            permissions=[perm.name for perm in role.permissions],
            user_count=user_count
        )
        role_responses.append(role_response)
    
    return role_responses


@router.post("/roles", response_model=RoleResponse)
async def create_role(
    role_data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.MANAGE_ROLES))
):
    """Create a new custom role."""
    rbac_service = RBACService(db)
    
    role = await rbac_service.create_custom_role(
        name=role_data.name,
        description=role_data.description,
        permission_names=role_data.permission_names
    )
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role already exists or invalid permissions"
        )
    
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_active=role.is_active,
        permissions=[perm.name for perm in role.permissions],
        user_count=0
    )


@router.put("/roles/{role_name}")
async def update_role(
    role_name: str,
    role_data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.MANAGE_ROLES))
):
    """Update a role's permissions."""
    rbac_service = RBACService(db)
    
    if role_data.permission_names:
        success = await rbac_service.update_role_permissions(role_name, role_data.permission_names)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )
    
    return {"message": "Role updated successfully"}


@router.delete("/roles/{role_name}")
async def delete_role(
    role_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.MANAGE_ROLES))
):
    """Delete a custom role (cannot delete default roles)."""
    rbac_service = RBACService(db)
    
    success = await rbac_service.delete_role(role_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete default role or role not found"
        )
    
    return {"message": "Role deleted successfully"}


# Permission Management Endpoints
@router.get("/permissions", response_model=List[PermissionResponse])
async def get_all_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.MANAGE_ROLES))
):
    """Get all available permissions."""
    rbac_service = RBACService(db)
    permissions = await rbac_service.get_all_permissions()
    
    return [
        PermissionResponse(
            id=perm.id,
            name=perm.name,
            description=perm.description
        )
        for perm in permissions
    ]


# User Management Endpoints
@router.get("/users", response_model=List[UserSummary])
async def get_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    role_filter: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.VIEW_USER))
):
    """Get all users with pagination and optional role filtering."""
    # This would need to be implemented in AuthService
    # For now, return a simple message
    return {"message": "User listing endpoint - to be implemented"}


@router.post("/users/{user_id}/roles")
async def assign_roles_to_user(
    user_id: int,
    assignment: UserRoleAssignment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.MANAGE_ROLES))
):
    """Assign roles to a user."""
    rbac_service = RBACService(db)
    
    success_count = 0
    for role_name in assignment.role_names:
        if await rbac_service.assign_role_to_user(assignment.user_id, role_name):
            success_count += 1
    
    return {
        "message": f"Assigned {success_count} roles to user",
        "user_id": assignment.user_id,
        "assigned_roles": assignment.role_names[:success_count]
    }


@router.delete("/users/{user_id}/roles/{role_name}")
async def remove_role_from_user(
    user_id: int,
    role_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.MANAGE_ROLES))
):
    """Remove a role from a user."""
    rbac_service = RBACService(db)
    
    success = await rbac_service.remove_role_from_user(user_id, role_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or role not assigned"
        )
    
    return {"message": f"Role {role_name} removed from user {user_id}"}


@router.post("/users/bulk-assign-roles")
async def bulk_assign_roles(
    assignment: BulkRoleAssignment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.MANAGE_ROLES))
):
    """Bulk assign roles to multiple users."""
    rbac_service = RBACService(db)
    
    success_count = await rbac_service.bulk_assign_roles(
        assignment.user_ids,
        assignment.role_names
    )
    
    return {
        "message": f"Bulk assignment completed",
        "successful_assignments": success_count,
        "total_requested": len(assignment.user_ids) * len(assignment.role_names)
    }


@router.post("/users/promote")
async def promote_user(
    promotion: UserPromotion,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.MANAGE_ROLES))
):
    """Promote a user from one role to another."""
    rbac_service = RBACService(db)
    
    success = await rbac_service.promote_user(
        promotion.user_id,
        promotion.from_role,
        promotion.to_role
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User promotion failed"
        )
    
    return {
        "message": f"User {promotion.user_id} promoted from {promotion.from_role} to {promotion.to_role}"
    }


@router.get("/users/{user_id}/roles")
async def get_user_roles(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.VIEW_USER))
):
    """Get all roles for a specific user."""
    rbac_service = RBACService(db)
    
    roles = await rbac_service.get_user_roles(user_id)
    permissions = await rbac_service.get_user_permissions(user_id)
    
    return {
        "user_id": user_id,
        "roles": [
            {
                "name": role.name,
                "description": role.description,
                "is_active": role.is_active
            }
            for role in roles
        ],
        "permissions": list(permissions)
    }


@router.get("/roles/{role_name}/users")
async def get_role_users(
    role_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.VIEW_USER))
):
    """Get all users with a specific role."""
    rbac_service = RBACService(db)
    
    users = await rbac_service.get_role_users(role_name)
    
    return {
        "role_name": role_name,
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active
            }
            for user in users
        ]
    }


# System Analytics Endpoints
@router.get("/analytics/roles")
async def get_role_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.VIEW_ANALYTICS))
):
    """Get analytics about role distribution."""
    rbac_service = RBACService(db)
    
    roles = await rbac_service.get_all_roles()
    
    role_stats = []
    total_users = 0
    
    for role in roles:
        users = await rbac_service.get_role_users(role.name)
        user_count = len(users)
        total_users += user_count
        
        role_stats.append({
            "role_name": role.name,
            "user_count": user_count,
            "permission_count": len(role.permissions),
            "is_default": role.name in [r.value for r in RoleType]
        })
    
    return {
        "total_roles": len(roles),
        "total_users": total_users,
        "role_distribution": role_stats,
        "default_roles": len([r for r in role_stats if r["is_default"]]),
        "custom_roles": len([r for r in role_stats if not r["is_default"]])
    }


@router.get("/analytics/permissions")
async def get_permission_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(lambda: require_admin_permission(PermissionType.VIEW_ANALYTICS))
):
    """Get analytics about permission usage."""
    rbac_service = RBACService(db)
    
    permissions = await rbac_service.get_all_permissions()
    roles = await rbac_service.get_all_roles()
    
    permission_usage = {}
    for permission in permissions:
        usage_count = sum(1 for role in roles if permission in role.permissions)
        permission_usage[permission.name] = usage_count
    
    return {
        "total_permissions": len(permissions),
        "permission_usage": permission_usage,
        "most_used_permissions": sorted(
            permission_usage.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10],
        "unused_permissions": [name for name, count in permission_usage.items() if count == 0]
    }
