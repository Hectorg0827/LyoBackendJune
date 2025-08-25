"""
Admin module for LyoApp.
Provides administrative functionality including user management, role assignment, and system analytics.
"""

from .routes import router as admin_router

__all__ = ["admin_router"]
