"""
Authentication dependencies for FastAPI

Re-exports the proper get_current_user from routes.py which handles:
- JWT token verification
- Firebase ID token verification
- Auto-creation of users from Firebase
"""
from lyo_app.core.database import get_db
from lyo_app.auth.routes import get_current_user

# Re-export for easy imports
__all__ = ["get_current_user", "get_db"]

