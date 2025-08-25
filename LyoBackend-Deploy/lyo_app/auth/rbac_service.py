"""
RBAC Service for managing roles and permissions.
Handles role assignment, permission checking, and RBAC operations.
"""

from typing import List, Optional, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.auth.models import User
from lyo_app.auth.rbac import (
    Role, Permission, RoleType, PermissionType, 
    DEFAULT_ROLE_PERMISSIONS, user_roles, role_permissions
)
from lyo_app.core.database import get_db_session


class RBACService:
    """Service for Role-Based Access Control operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def initialize_default_roles_and_permissions(self) -> None:
        """Initialize default roles and permissions in the database."""
        # Create all permissions
        permissions = {}
        for perm_type in PermissionType:
            permission = await self._get_or_create_permission(
                name=perm_type.value,
                description=f"Permission to {perm_type.value.replace('_', ' ')}"
            )
            permissions[perm_type.value] = permission
        
        # Create all roles with their permissions
        for role_type, perm_names in DEFAULT_ROLE_PERMISSIONS.items():
            role = await self._get_or_create_role(
                name=role_type.value,
                description=f"Default {role_type.value.replace('_', ' ')} role"
            )
            
            # Assign permissions to role
            role_perms = [permissions[perm_name] for perm_name in perm_names]
            await self._assign_permissions_to_role(role, role_perms)
        
        await self.db.commit()
    
    async def _get_or_create_permission(self, name: str, description: str) -> Permission:
        """Get existing permission or create new one."""
        stmt = select(Permission).where(Permission.name == name)
        result = await self.db.execute(stmt)
        permission = result.scalar_one_or_none()
        
        if not permission:
            permission = Permission(name=name, description=description)
            self.db.add(permission)
            await self.db.flush()
        
        return permission
    
    async def _get_or_create_role(self, name: str, description: str) -> Role:
        """Get existing role or create new one."""
        stmt = select(Role).where(Role.name == name)
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            role = Role(name=name, description=description)
            self.db.add(role)
            await self.db.flush()
        
        return role
    
    async def _assign_permissions_to_role(self, role: Role, permissions: List[Permission]) -> None:
        """Assign permissions to a role."""
        # Clear existing permissions
        role.permissions.clear()
        
        # Add new permissions
        for permission in permissions:
            if permission not in role.permissions:
                role.permissions.append(permission)
    
    async def assign_role_to_user(self, user_id: int, role_name: str) -> bool:
        """Assign a role to a user."""
        # Get user with roles loaded
        stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # Get role
        stmt = select(Role).where(Role.name == role_name)
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            return False
        
        # Check if user already has the role
        if role not in user.roles:
            user.roles.append(role)
            await self.db.commit()
        
        return True
    
    async def remove_role_from_user(self, user_id: int, role_name: str) -> bool:
        """Remove a role from a user."""
        # Get user with roles loaded
        stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # Find and remove role
        for role in user.roles:
            if role.name == role_name:
                user.roles.remove(role)
                await self.db.commit()
                return True
        
        return False
    
    async def assign_default_role_to_user(self, user_id: int, role_type: RoleType = RoleType.STUDENT) -> bool:
        """Assign a default role to a newly registered user."""
        return await self.assign_role_to_user(user_id, role_type.value)
    
    async def get_user_roles(self, user_id: int) -> List[Role]:
        """Get all roles for a user."""
        stmt = (
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .where(User.id == user_id)
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        return user.roles if user else []
    
    async def get_user_permissions(self, user_id: int) -> Set[str]:
        """Get all permissions for a user through their roles."""
        roles = await self.get_user_roles(user_id)
        permissions = set()
        
        for role in roles:
            for permission in role.permissions:
                permissions.add(permission.name)
        
        return permissions
    
    async def user_has_permission(self, user_id: int, permission_name: str) -> bool:
        """Check if a user has a specific permission."""
        permissions = await self.get_user_permissions(user_id)
        return permission_name in permissions
    
    async def user_has_role(self, user_id: int, role_name: str) -> bool:
        """Check if a user has a specific role."""
        roles = await self.get_user_roles(user_id)
        return any(role.name == role_name for role in roles)
    
    async def create_custom_role(self, name: str, description: str, permission_names: List[str]) -> Optional[Role]:
        """Create a custom role with specific permissions."""
        # Check if role already exists
        stmt = select(Role).where(Role.name == name)
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            return None  # Role already exists
        
        # Create role
        role = Role(name=name, description=description)
        self.db.add(role)
        await self.db.flush()
        
        # Get permissions
        stmt = select(Permission).where(Permission.name.in_(permission_names))
        result = await self.db.execute(stmt)
        permissions = result.scalars().all()
        
        # Assign permissions to role
        role.permissions.extend(permissions)
        await self.db.commit()
        
        return role
    
    async def update_role_permissions(self, role_name: str, permission_names: List[str]) -> bool:
        """Update permissions for a role."""
        # Get role
        stmt = select(Role).options(selectinload(Role.permissions)).where(Role.name == role_name)
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            return False
        
        # Get new permissions
        stmt = select(Permission).where(Permission.name.in_(permission_names))
        result = await self.db.execute(stmt)
        permissions = result.scalars().all()
        
        # Update role permissions
        role.permissions.clear()
        role.permissions.extend(permissions)
        await self.db.commit()
        
        return True
    
    async def get_all_roles(self) -> List[Role]:
        """Get all roles."""
        stmt = select(Role).options(selectinload(Role.permissions))
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_all_permissions(self) -> List[Permission]:
        """Get all permissions."""
        stmt = select(Permission)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def delete_role(self, role_name: str) -> bool:
        """Delete a role (except default roles)."""
        # Prevent deletion of default roles
        default_role_names = {role.value for role in RoleType}
        if role_name in default_role_names:
            return False
        
        stmt = select(Role).where(Role.name == role_name)
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if role:
            await self.db.delete(role)
            await self.db.commit()
            return True
        
        return False
    
    async def get_role_users(self, role_name: str) -> List[User]:
        """Get all users with a specific role."""
        stmt = (
            select(User)
            .join(user_roles)
            .join(Role)
            .where(Role.name == role_name)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def bulk_assign_roles(self, user_ids: List[int], role_names: List[str]) -> int:
        """Bulk assign roles to multiple users."""
        success_count = 0
        
        for user_id in user_ids:
            for role_name in role_names:
                if await self.assign_role_to_user(user_id, role_name):
                    success_count += 1
        
        return success_count
    
    async def promote_user(self, user_id: int, from_role: str, to_role: str) -> bool:
        """Promote a user from one role to another."""
        # Remove old role and add new role
        removed = await self.remove_role_from_user(user_id, from_role)
        if removed:
            return await self.assign_role_to_user(user_id, to_role)
        return False
    
    async def get_user_role_hierarchy(self, user_id: int) -> List[str]:
        """Get user roles in hierarchy order (highest to lowest privilege)."""
        roles = await self.get_user_roles(user_id)
        role_names = [role.name for role in roles]
        
        # Define hierarchy order
        hierarchy = [
            RoleType.SUPER_ADMIN.value,
            RoleType.ADMIN.value,
            RoleType.MODERATOR.value,
            RoleType.INSTRUCTOR.value,
            RoleType.STUDENT.value,
            RoleType.GUEST.value,
        ]
        
        # Sort by hierarchy
        sorted_roles = []
        for role in hierarchy:
            if role in role_names:
                sorted_roles.append(role)
        
        # Add any custom roles not in hierarchy
        for role_name in role_names:
            if role_name not in hierarchy:
                sorted_roles.append(role_name)
        
        return sorted_roles
