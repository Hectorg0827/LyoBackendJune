"""
Setup script for LyoApp RBAC and security features.
Initializes database with RBAC tables and default roles/permissions.
"""

import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import init_db, AsyncSessionLocal
from lyo_app.auth.rbac_service import RBACService
from lyo_app.auth.service import AuthService
from lyo_app.auth.schemas import UserCreate
from lyo_app.auth.rbac import RoleType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def setup_rbac_system():
    """Set up the RBAC system with default roles and permissions."""
    logger.info("🔐 Setting up RBAC system...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("✅ Database tables created/updated")
        
        # Set up RBAC
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            await rbac_service.initialize_default_roles_and_permissions()
            logger.info("✅ RBAC roles and permissions initialized")
        
        logger.info("🎉 RBAC system setup completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Failed to set up RBAC system: {str(e)}")
        raise


async def create_default_admin():
    """Create a default admin user if none exists."""
    logger.info("👤 Creating default admin user...")
    
    try:
        async with AsyncSessionLocal() as db:
            auth_service = AuthService()
            rbac_service = RBACService(db)
            
            # Check if admin already exists
            existing_admin = await auth_service.get_user_by_email(db, "admin@lyo.app")
            if existing_admin:
                logger.info("✅ Admin user already exists")
                return existing_admin
            
            # Create admin user
            admin_data = UserCreate(
                email="admin@lyo.app",
                username="admin",
                password="LyoAdmin123!",  # Change this in production
                confirm_password="LyoAdmin123!",
                first_name="System",
                last_name="Administrator"
            )
            
            admin_user = await auth_service.register_user(db, admin_data)
            
            # Assign super admin role
            await rbac_service.assign_role_to_user(admin_user.id, RoleType.SUPER_ADMIN.value)
            
            logger.info("✅ Default admin user created successfully")
            logger.info("📧 Email: admin@lyo.app")
            logger.info("🔑 Password: LyoAdmin123! (CHANGE IN PRODUCTION)")
            
            return admin_user
            
    except Exception as e:
        logger.error(f"❌ Failed to create admin user: {str(e)}")
        raise


async def verify_rbac_setup():
    """Verify that RBAC system is working correctly."""
    logger.info("🔍 Verifying RBAC setup...")
    
    try:
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            
            # Check roles
            roles = await rbac_service.get_all_roles()
            logger.info(f"✅ Found {len(roles)} roles")
            
            # Check permissions
            permissions = await rbac_service.get_all_permissions()
            logger.info(f"✅ Found {len(permissions)} permissions")
            
            # Check admin user
            admin = await AuthService().get_user_by_email(db, "admin@lyo.app")
            if admin:
                admin_roles = await rbac_service.get_user_roles(admin.id)
                admin_permissions = await rbac_service.get_user_permissions(admin.id)
                logger.info(f"✅ Admin has {len(admin_roles)} roles and {len(admin_permissions)} permissions")
            
            logger.info("🎉 RBAC verification completed successfully!")
            
    except Exception as e:
        logger.error(f"❌ RBAC verification failed: {str(e)}")
        raise


async def main():
    """Main setup function."""
    logger.info("🚀 Starting LyoApp RBAC and Security Setup")
    logger.info("=" * 50)
    
    try:
        # Step 1: Set up RBAC system
        await setup_rbac_system()
        
        # Step 2: Create default admin
        await create_default_admin()
        
        # Step 3: Verify setup
        await verify_rbac_setup()
        
        logger.info("=" * 50)
        logger.info("🎉 LyoApp RBAC and Security Setup Completed Successfully!")
        logger.info("🚀 You can now start the server with: python start_server.py")
        
    except Exception as e:
        logger.error("=" * 50)
        logger.error(f"❌ Setup failed: {str(e)}")
        logger.error("Please check the logs above for details.")
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    if not success:
        exit(1)
