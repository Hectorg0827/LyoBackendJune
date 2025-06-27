"""
Simple RBAC setup and test.
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


async def simple_setup():
    """Simple RBAC setup."""
    logger.info("🚀 Starting RBAC setup...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("✅ Database initialized")
        
        # Set up RBAC
        async with AsyncSessionLocal() as db:
            rbac_service = RBACService(db)
            await rbac_service.initialize_default_roles_and_permissions()
            logger.info("✅ RBAC roles and permissions initialized")
            
            # Test: Create a test user
            auth_service = AuthService()
            try:
                test_user_data = UserCreate(
                    email="test@lyo.app",
                    username="testuser",
                    password="TestPass123!",
                    confirm_password="TestPass123!",
                    first_name="Test",
                    last_name="User"
                )
                
                test_user = await auth_service.register_user(db, test_user_data)
                logger.info(f"✅ Test user created: {test_user.username}")
                
                # Check user roles
                user_roles = await rbac_service.get_user_roles(test_user.id)
                role_names = [role.name for role in user_roles]
                logger.info(f"✅ User roles: {role_names}")
                
                # Check user permissions
                user_permissions = await rbac_service.get_user_permissions(test_user.id)
                logger.info(f"✅ User has {len(user_permissions)} permissions")
                
            except ValueError as e:
                if "already registered" in str(e) or "already taken" in str(e):
                    logger.info("✅ Test user already exists")
                else:
                    raise
        
        logger.info("🎉 RBAC setup completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(simple_setup())
    if success:
        print("\n🎉 Success! You can now:")
        print("1. Start the server: python3 start_server.py")
        print("2. Run tests: python3 test_authentication.py")
        print("3. Access API docs: http://localhost:8000/docs")
    else:
        print("\n❌ Setup failed. Check the logs above.")
        exit(1)
